"""
Compaction strategies for message history compression.

Uses Strategy pattern to separate different compression approaches:
- SummarizeWithHeaderCompaction: Conservative, keeps first user-assistant pair as header (CLI/TUI mode)
- SlidingWindowCompaction: Aggressive sliding-window, drops oldest turns first (IM/chat mode)
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from agents.models.chatcmpl_converter import Converter
from siada.agent_hub.coder.prompt.compact_prompt import (
    _auto_compact_response,
    get_compact_system_prompt,
)
from siada.agent_hub.context_filter.utils import (
    calculate_tokens,
    estimate_tokens,
    _convert_tools_to_openai_params,
)
from siada.provider.client_factory import get_client
from siada.foundation.context import agent_name_scope
from siada.foundation.logging import logger

# Event-type marker used in the X-Siada-Event-Type header for compaction LLM calls.
# Overrides AGENT_NAME for the duration of call_llm_to_compact() so server-side
# analytics can distinguish compaction traffic from normal agent traffic.
COMPACTION_AGENT_NAME = "context_compaction"

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.models.model_run_config import ModelRunConfig


class CompactionError(Exception):
    """Raised when message compaction/truncation fails."""
    pass


@dataclass
class CompactionResult:
    """Result of a single `CompactionStrategy.compact()` pass.

    Callers must key off `compacted` to decide whether anything actually
    changed — not identity comparisons against the input list. `messages`
    is always safe to use as "the current message list" either way:
      - compacted=False → `messages` is the exact `real_api_messages`
        object the caller originally passed in.
      - compacted=True  → `messages` is a brand-new list.
    """

    messages: List
    summary: Optional[str] = None       # generated summary (for persistence / cascading)
    compacted: bool = False             # whether compaction actually happened


class CompactionStrategy(ABC):
    """
    Abstract base class for message compaction strategies.

    Provides shared helper methods for message type detection, index calculation,
    boundary case handling, LLM summarization, and compressed history assembly.
    Subclasses only need to implement the core compaction logic via `compact()`.
    """

    @property
    @abstractmethod
    def token_threshold_ratio(self) -> float:
        """Ratio of context window that triggers compaction."""
        ...

    @property
    @abstractmethod
    def preserve_ratio(self) -> float:
        """Fraction of recent messages to preserve after compaction."""
        ...

    @property
    @abstractmethod
    def summary_budget_ratio(self) -> float:
        """Max portion of context window for the LLM summarization call."""
        ...

    def should_compact(self, tokens_count: int, model_config: "ModelRunConfig") -> bool:
        """Check if compaction is needed based on token count and threshold."""
        threshold = model_config.context_window * self.token_threshold_ratio
        return tokens_count >= threshold

    async def compact(
        self,
        model_run_config: "ModelRunConfig",
        real_api_messages: List,
        *,
        fixed_overhead_tokens: int = 0,
    ) -> CompactionResult:
        """
        Execute the compaction strategy.

        This is a template method: it hands ``_compact_impl()`` a private
        shallow copy of ``real_api_messages`` and normalizes the result so
        every caller can rely on a single, enforced contract regardless of
        which concrete strategy ran — expressed explicitly via
        ``CompactionResult.compacted``, never via list-identity comparisons:
          - ``compacted=False`` → ``result.messages`` is the exact
            ``real_api_messages`` object the caller passed in.
          - ``compacted=True``  → ``result.messages`` is a brand-new list.

        Subclasses implement ``_compact_impl()`` and are free to mutate the
        list they receive in place (e.g. slicing/reassigning) without any
        risk of corrupting the caller's original ``real_api_messages``
        reference — the copy here makes that guarantee, so callers (and
        subclasses) don't each have to reimplement it.

        Args:
            model_run_config: Model run config (provides model name, context window, provider)
            real_api_messages: All real API messages
            fixed_overhead_tokens: Pre-computed token overhead for system
                instructions + tool definitions.  Subtracted from internal
                budget calculations so compaction targets the correct size.

        Returns:
            CompactionResult with an explicit `compacted` flag.
        """
        working_copy = list(real_api_messages)
        result = await self._compact_impl(
            model_run_config, working_copy, fixed_overhead_tokens=fixed_overhead_tokens,
        )
        if not result.compacted:
            # No-op: hand back the TRUE original object regardless of what
            # `result.messages` happens to be (even if a subclass mutated
            # the working copy in place and echoed it back) — callers must
            # never see anything other than their own original reference
            # on the no-op path.
            return CompactionResult(
                messages=real_api_messages, summary=result.summary, compacted=False,
            )
        return result

    @abstractmethod
    async def _compact_impl(
        self,
        model_run_config: "ModelRunConfig",
        real_api_messages: List,
        *,
        fixed_overhead_tokens: int = 0,
    ) -> CompactionResult:
        """
        Concrete compaction logic implemented by subclasses.

        ``real_api_messages`` is a private copy owned by this call — see
        ``compact()`` for the identity contract this enables. Return a
        ``CompactionResult`` with ``compacted`` set explicitly:
          - ``compacted=False`` for a no-op (whatever ``messages`` you put
            in this case is discarded by ``compact()`` in favor of the
            caller's true original list).
          - ``compacted=True`` with ``messages`` set to the new list for a
            real change.

        Args:
            model_run_config: Model run config (provides model name, context window, provider)
            real_api_messages: All real API messages (private copy)
            fixed_overhead_tokens: Pre-computed token overhead for system
                instructions + tool definitions.  Subtracted from internal
                budget calculations so compaction targets the correct size.

        Returns:
            CompactionResult with an explicit `compacted` flag.
        """
        ...

    # ── fixed overhead calculation ───────────────────────────────────

    @staticmethod
    def calculate_fixed_overhead(
        context: "CodeAgentContext",
        instructions: str | None = None,
        tools=None,
    ) -> int:
        """
        Calculate the fixed token overhead for instructions + tools.

        This overhead is constant across compaction iterations and should be
        subtracted from budget calculations so messages are compressed to the
        correct target size.

        Args:
            context: code agent context (for model name)
            instructions: system instructions text
            tools: list of agent Tool objects

        Returns:
            Total fixed overhead in tokens
        """
        _t_overhead_start = time.perf_counter()
        overhead = 0
        model_name = context.model_run_config.model_name

        if instructions:
            instruction_tokens = calculate_tokens(model_name, instructions)
            overhead += instruction_tokens
            logger.info(
                "[calculate_fixed_overhead] instruction_tokens=%d, model=%s",
                instruction_tokens, model_name,
            )

        if tools:
            _t0 = time.perf_counter()
            try:
                import litellm
                openai_tools = _convert_tools_to_openai_params(tools)
                if openai_tools:
                    # Use litellm's _count_extra to measure tool definition tokens
                    with_tools = litellm.token_counter(
                        model=model_name,
                        messages=[{"role": "user", "content": "x"}],
                        tools=openai_tools,
                    )
                    without_tools = litellm.token_counter(
                        model=model_name,
                        messages=[{"role": "user", "content": "x"}],
                    )
                    tool_tokens = with_tools - without_tools
                    overhead += tool_tokens
                    logger.info(
                        "[calculate_fixed_overhead] tool_tokens=%d (with=%d, without=%d), "
                        "num_tools=%d, model=%s, tool_token_count=%.1fms",
                        tool_tokens, with_tools, without_tools,
                        len(openai_tools), model_name,
                        (time.perf_counter() - _t0) * 1000,
                    )
            except Exception as e:
                logger.warning(
                    "[calculate_fixed_overhead] Failed to calculate tool tokens: %s", e,
                )

        logger.info(
            "[PERF][calculate_fixed_overhead] total_overhead=%d, model=%s | %.1fms",
            overhead, model_name,
            (time.perf_counter() - _t_overhead_start) * 1000,
        )
        return overhead

    # ── message type helpers ────────────────────────────────────────

    @staticmethod
    def is_user_message(message) -> bool:
        """Check if a message is from user."""
        return (
            Converter.maybe_easy_input_message(message)
            or Converter.maybe_input_message(message)
        )

    @staticmethod
    def is_assistant_message(message) -> bool:
        """Check if a message is from assistant."""
        return (
            Converter.maybe_function_tool_call(message)
            or Converter.maybe_file_search_call(message)
            or Converter.maybe_reasoning_message(message)
            or Converter.maybe_response_output_message(message)
        )

    @staticmethod
    def is_function_response(message) -> bool:
        """Check if a message is a function/tool call response."""
        return Converter.maybe_function_tool_call_output(message)

    # ── index helpers ───────────────────────────────────────────────

    @staticmethod
    def find_index_after_fraction(history: List, fraction: float) -> int:
        """
        Find the index in history after a certain fraction of total content length.

        Args:
            history: List of messages/content items
            fraction: Fraction between 0 and 1 indicating where to split

        Returns:
            Index after the specified fraction of content
        """
        if fraction <= 0 or fraction >= 1:
            raise ValueError("Fraction must be between 0 and 1")

        content_lengths = [
            len(json.dumps(content, sort_keys=True, ensure_ascii=False))
            for content in history
        ]
        total_characters = sum(content_lengths)
        target_characters = total_characters * fraction

        characters_so_far = 0
        for i, length in enumerate(content_lengths):
            if characters_so_far >= target_characters:
                return i
            characters_so_far += length

        return len(content_lengths)

    def adjust_compression_index_for_boundary_cases(
        self, messages: List, compress_before_index: int
    ) -> int:
        """
        Adjust compression index to handle boundary cases where the index is at or near the end.

        This ensures we keep either:
        1. The last user message, or
        2. The complete tool-call-result pair (including the assistant message before the tool-call)

        When compression index reaches the end, adjust it backwards to preserve these sequences.

        Args:
            messages: List of all messages
            compress_before_index: Current compression index

        Returns:
            Adjusted compression index
        """
        if compress_before_index >= len(messages):
            compress_before_index = len(messages)

        # If we're at the very end or close to it, we need to move back
        # to ensure we keep a meaningful sequence
        if compress_before_index >= len(messages) - 1:
            # Start from the end and scan backwards
            idx = len(messages) - 1

            # Case 1: Last message is a user message - keep it
            if idx >= 0 and self.is_user_message(messages[idx]):
                return idx

            # Case 2: Last message is a function response - need to keep the complete sequence
            # Pattern: [user_message] -> [reasoning (optional)] -> [response] -> [function_call] -> [function_response]
            if idx >= 0 and self.is_function_response(messages[idx]):
                # Find the start of this tool call sequence
                # We need to include: function_response, function_call (assistant), and all assistant messages before

                # Look for the function call (assistant message with tool call)
                if idx >= 1 and self.is_assistant_message(messages[idx - 1]):
                    # Continue looking backwards for all consecutive assistant messages (reasoning, response, etc.)
                    # until we hit a non-assistant message (usually a user message)
                    start_idx = idx - 1
                    while start_idx > 0 and self.is_assistant_message(messages[start_idx - 1]):
                        start_idx -= 1

                    # Return the index of the first assistant message in the sequence
                    return start_idx

                # If we can't find a proper function call, at least keep the function response
                return idx

        # If we're not at the boundary, return the original index
        return compress_before_index

    @staticmethod
    def try_get_first_user_assistant_pair(
        messages: List, compress_before_index: int
    ) -> List:
        """Get the first user-assistant message pair as a header."""
        first_message = messages[0]
        if len(messages) >= 2 and Converter.maybe_response_output_message(messages[1]):
            return [first_message, messages[1]]
        return [first_message]

    def _snap_to_user_boundary(self, messages: List, index: int) -> int:
        """Advance index past assistant/function_response messages to land on a user message."""
        while index < len(messages) and (
            self.is_assistant_message(messages[index])
            or self.is_function_response(messages[index])
        ):
            index += 1
        return index

    # ── LLM summarization ──────────────────────────────────────────

    def _get_compaction_system_prompt(self) -> str:
        """Return the system prompt for the LLM summarization call.

        Subclasses can override to use a different prompt style.
        Default uses the CLI/TUI compact prompt.
        """
        return get_compact_system_prompt()

    def _get_compaction_user_prompt(self) -> str:
        """Return the user prompt for the LLM summarization call.

        Subclasses can override to use a different prompt style.
        Default uses the CLI/TUI compact prompt.
        """
        return _auto_compact_response()

    async def call_llm_to_compact(
        self, model_run_config: "ModelRunConfig", history_to_compact: List
    ) -> str | None:
        """
        Call LLM to generate a summary of the given message history.

        Uses _get_compaction_system_prompt() and _get_compaction_user_prompt()
        for prompt customization — subclasses override those methods
        instead of duplicating the LLM call logic.

        If SIADA_COMPACT_MODEL env var is set, uses that model for the
        summarization call instead of the main agent model. This allows
        using a cheaper/smaller model for compaction.

        Args:
            model_run_config: Model run config (provides provider and model info)
            history_to_compact: Messages to summarize

        Returns:
            Extracted summary string, or None on failure
        """
        import os

        provider = model_run_config.provider
        main_model = model_run_config.model_name
        # Allow overriding the compact model via env var
        model = os.environ.get("SIADA_COMPACT_MODEL", main_model)
        if model != main_model:
            logger.info(
                "[call_llm_to_compact] Using compact model '%s' instead of main model '%s'",
                model, main_model,
            )

        compact_messages = Converter.items_to_messages(history_to_compact) + [
            {"role": "user", "content": self._get_compaction_user_prompt()}
        ]
        compact_messages.insert(
            0, {"role": "system", "content": self._get_compaction_system_prompt()}
        )

        # Log the compact call details
        compact_msg_tokens = self._count_tokens(
            compact_messages, model_run_config,
        )
        logger.info(
            "[call_llm_to_compact] Sending %d messages (%d tokens) to model '%s'",
            len(compact_messages), compact_msg_tokens, model,
        )

        llm_client = get_client(provider)

        complete_kwargs = {
            "model": model,
            "messages": compact_messages,
        }

        # Only add empty tools list for Anthropic/Claude models to avoid litellm error
        if "anthropic" in model.lower() or "claude" in model.lower():
            complete_kwargs["tools"] = []

        # Temporarily override AGENT_NAME so the X-Siada-Event-Type header on
        # this LLM request is tagged as a compaction call. `agent_name_scope`
        # restores the previous value (or removes the key if it was absent)
        # on exit, preventing the override from leaking into subsequent
        # requests that share the same asyncio task.
        _t0 = time.perf_counter()
        with agent_name_scope(COMPACTION_AGENT_NAME):
            response = await llm_client.completion(**complete_kwargs)
        _llm_elapsed_ms = (time.perf_counter() - _t0) * 1000

        if response and response.choices and response.choices[0].message:
            raw_content = response.choices[0].message.content
            summary = self._extract_summary(raw_content)
            logger.info(
                "[PERF][call_llm_to_compact] model=%s input_tokens=%d "
                "summary_chars=%d | llm_call=%.1fms",
                model, compact_msg_tokens,
                len(summary) if summary else 0, _llm_elapsed_ms,
            )
            return summary
        logger.info(
            "[PERF][call_llm_to_compact] model=%s input_tokens=%d "
            "empty_response | llm_call=%.1fms",
            model, compact_msg_tokens, _llm_elapsed_ms,
        )
        return None

    @staticmethod
    def _extract_summary(content: str | None) -> str | None:
        """
        Extract the <context>...</context> block from the LLM response.

        Returns:
            Extracted block, or the full content if not found, or None if empty
        """
        if not content:
            return content

        match = re.search(r"<context>.*?</context>", content, re.DOTALL)
        if match:
            return match.group(0)
        return content

    # ── tool pair helpers (shared by subclasses) ────────────────────

    @staticmethod
    def _extract_tool_use_ids(msg) -> set:
        """Extract tool_use / function_call IDs from an assistant message.

        In the OpenAI Responses API, function_call items are top-level items
        in the messages list (not nested inside msg.content). The structure is:
        {type: "function_call", call_id: "xxx", name: "...", arguments: "..."}
        """
        ids: set = set()
        if isinstance(msg, dict):
            if msg.get("type") in ("tool_use", "function_call"):
                tid = msg.get("call_id") or msg.get("id")
                if tid:
                    ids.add(tid)
        else:
            msg_type = getattr(msg, "type", None)
            if msg_type in ("tool_use", "function_call"):
                tid = getattr(msg, "call_id", None) or getattr(msg, "id", None)
                if tid:
                    ids.add(tid)
        return ids

    @staticmethod
    def _extract_tool_result_ids(msg) -> set:
        """Extract the matching call_id from a function response message.

        In the OpenAI Responses API, FunctionCallOutput has:
        - call_id: the matching ID that pairs with function_call's call_id
        - id: the item's own unique ID (NOT for pairing, should be ignored)
        """
        ids: set = set()
        if isinstance(msg, dict):
            val = msg.get("call_id")
            if val:
                ids.add(val)
        else:
            val = getattr(msg, "call_id", None)
            if val:
                ids.add(val)
        return ids

    def _repair_tool_pairs(self, messages: List) -> List:
        """
        Fix orphan tool_use / tool_result after truncation.

        The API requires every function_call to have a matching
        function_call_output and vice versa. A typical response group is:
            [reasoning] -> [output_message] -> function_call -> function_call_output
        When an orphan function_call is removed, its preceding reasoning and
        output_message from the same response group must also be removed.
        """
        if not messages:
            return messages

        # Collect all function_call call_ids
        tool_use_ids: set = set()
        for msg in messages:
            if self.is_assistant_message(msg):
                tool_use_ids.update(self._extract_tool_use_ids(msg))

        # Collect all function_call_output call_ids
        tool_result_ids: set = set()
        for msg in messages:
            if self.is_function_response(msg):
                tool_result_ids.update(self._extract_tool_result_ids(msg))

        # Mark indices to remove
        remove_indices: set = set()
        for i, msg in enumerate(messages):
            if self.is_function_response(msg):
                # Orphan function_call_output (no matching function_call)
                msg_ids = self._extract_tool_result_ids(msg)
                if msg_ids and not msg_ids.intersection(tool_use_ids):
                    remove_indices.add(i)
            elif self.is_assistant_message(msg):
                use_ids = self._extract_tool_use_ids(msg)
                if use_ids and not use_ids.intersection(tool_result_ids):
                    # Orphan function_call (no matching function_call_output)
                    remove_indices.add(i)
                    # Also remove preceding reasoning/output_message items
                    # that belong to the same response group
                    j = i - 1
                    while j >= 0 and j not in remove_indices:
                        prev = messages[j]
                        if self.is_user_message(prev) or self.is_function_response(prev):
                            break
                        prev_use_ids = self._extract_tool_use_ids(prev)
                        if prev_use_ids:
                            break
                        if self.is_assistant_message(prev):
                            remove_indices.add(j)
                        else:
                            break
                        j -= 1

        # Build result excluding removed indices
        result = [msg for i, msg in enumerate(messages) if i not in remove_indices]

        # Ensure first message is user
        while result and not self.is_user_message(result[0]):
            result.pop(0)

        return result

    # ── token counting (shared by subclasses) ───────────────────────

    def _count_tokens(
        self, messages: List, model_run_config: "ModelRunConfig | None" = None
    ) -> int:
        """
        Count tokens using litellm when model_run_config is available,
        falling back to rough char-based estimate otherwise.

        Note: calculate_tokens() already applies TOKEN_ESTIMATION_SAFETY_MARGIN
        to inflate counts, so all budget comparisons automatically include
        safety headroom.
        """
        model_name = model_run_config.model_name if model_run_config is not None else None
        return calculate_tokens(model_name, messages)

    # ── prune / trim helpers (shared by subclasses) ─────────────────

    def _prune_messages_to_token_budget(
        self, messages: List, budget_tokens: int, model_run_config: "ModelRunConfig"
    ) -> List:
        """
        Prune messages from the oldest end so the total fits within budget_tokens.

        Uses binary search on user turn boundaries for efficiency.
        Repairs orphan tool pairs after pruning.

        Note: calculate_tokens() (called by _count_tokens) already applies
        a safety margin to inflate token counts, so all comparisons against
        budget_tokens automatically include safety headroom.

        Args:
            messages: messages to prune
            budget_tokens: max allowed token count
            model_run_config: model run config (for token counting)

        Returns:
            Pruned message list fitting within budget.
        """
        initial_count = len(messages)
        initial_tokens = self._count_tokens(messages, model_run_config)
        logger.info(
            "[_prune_messages_to_token_budget] START: "
            "initial_messages=%d, initial_tokens=%d (includes safety margin), "
            "budget_tokens=%d",
            initial_count, initial_tokens, budget_tokens,
        )

        if initial_tokens <= budget_tokens:
            logger.info(
                "[_prune_messages_to_token_budget] Already within budget, no pruning needed"
            )
            return messages

        # Find all user turn boundaries (each is a valid cut point)
        user_indices = [
            i for i, m in enumerate(messages) if self.is_user_message(m)
        ]
        logger.info(
            "[_prune_messages_to_token_budget] Found %d user turn boundaries at indices: %s",
            len(user_indices), user_indices,
        )
        if not user_indices:
            logger.warning(
                "[_prune_messages_to_token_budget] No user messages found, returning empty list"
            )
            return []

        # Binary search: find the earliest user turn boundary where
        # messages[boundary:] fits within budget
        lo, hi = 0, len(user_indices) - 1
        best = hi  # worst case: keep only the last user turn

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = messages[user_indices[mid]:]
            candidate_tokens = self._count_tokens(candidate, model_run_config)
            logger.debug(
                "[_prune_messages_to_token_budget] Binary search: lo=%d, hi=%d, mid=%d, "
                "cut_at_index=%d, candidate_messages=%d, candidate_tokens=%d",
                lo, hi, mid, user_indices[mid], len(candidate), candidate_tokens,
            )
            if candidate_tokens <= budget_tokens:
                best = mid
                hi = mid - 1  # try to keep more (earlier boundary)
            else:
                lo = mid + 1  # need to drop more old turns

        pruned_count = user_indices[best]
        messages = messages[user_indices[best]:]
        logger.info(
            "[_prune_messages_to_token_budget] Pruned %d oldest messages "
            "(cut at user turn index %d), remaining=%d messages",
            pruned_count, user_indices[best], len(messages),
        )

        # Repair orphan tool pairs caused by pruning
        before_repair = len(messages)
        messages = self._repair_tool_pairs(messages)
        after_repair = len(messages)
        if before_repair != after_repair:
            logger.info(
                "[_prune_messages_to_token_budget] Repaired orphan tool pairs: "
                "messages %d -> %d",
                before_repair, after_repair,
            )

        final_tokens = self._count_tokens(messages, model_run_config)
        logger.info(
            "[_prune_messages_to_token_budget] DONE: "
            "final_messages=%d, final_tokens=%d, budget_tokens=%d, "
            "tokens_saved=%d",
            len(messages), final_tokens, budget_tokens,
            initial_tokens - final_tokens,
        )
        return messages

    def _trim_kept_history(
        self, messages: List, model_run_config: "ModelRunConfig", budget_tokens: int
    ) -> List:
        """
        Trim history_to_keep to fit within budget_tokens.

        Strategy:
          1. If already within budget, return as-is.
          2. Keep only from the last user message onwards.
          3. If still over budget, remove oldest tool call groups
             (assistant msgs + function_call_output) one by one after
             the last user message, until within budget.

        Args:
            messages: the history_to_keep portion
            model_run_config: model run config (for token counting)
            budget_tokens: max allowed token count

        Returns:
            Trimmed message list.
        """
        initial_count = len(messages) if messages else 0
        initial_tokens = self._count_tokens(messages, model_run_config) if messages else 0
        logger.info(
            "[_trim_kept_history] START: "
            "initial_messages=%d, initial_tokens=%d, budget_tokens=%d",
            initial_count, initial_tokens, budget_tokens,
        )

        if not messages or initial_tokens <= budget_tokens:
            logger.info(
                "[_trim_kept_history] Already within budget or empty, no trimming needed"
            )
            return messages

        # Step 2: keep only from the last user message
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if self.is_user_message(messages[i]):
                last_user_idx = i
                break

        if last_user_idx is not None and last_user_idx > 0:
            dropped = last_user_idx
            messages = messages[last_user_idx:]
            tokens_after_step2 = self._count_tokens(messages, model_run_config)
            logger.info(
                "[_trim_kept_history] Step 2: Kept from last user message (index=%d), "
                "dropped %d messages, remaining=%d messages, tokens=%d",
                last_user_idx, dropped, len(messages), tokens_after_step2,
            )
        else:
            tokens_after_step2 = self._count_tokens(messages, model_run_config)
            logger.info(
                "[_trim_kept_history] Step 2: No earlier messages to drop "
                "(last_user_idx=%s), messages=%d, tokens=%d",
                last_user_idx, len(messages), tokens_after_step2,
            )

        if tokens_after_step2 <= budget_tokens:
            logger.info(
                "[_trim_kept_history] Within budget after Step 2, done"
            )
            return messages

        # Step 3: within the last user turn, remove oldest tool call groups
        # one by one until within budget.
        #
        # A tool call group = [reasoning?] [output_message?] [function_call] [function_call_output]
        # Groups are ordered oldest → newest.
        # We remove from the oldest side first, since newest groups are more relevant.
        tool_groups = self._identify_tool_call_groups(messages)
        logger.info(
            "[_trim_kept_history] Step 3: Found %d tool call groups to consider removing",
            len(tool_groups),
        )

        if not tool_groups:
            logger.info(
                "[_trim_kept_history] No tool call groups found, returning as-is"
            )
            return messages

        # Accumulate indices to remove, adding one more group each iteration
        indices_to_remove: set[int] = set()
        groups_removed = 0
        for group_start, group_end in tool_groups:
            # Mark this group's message indices for removal
            indices_to_remove.update(range(group_start, group_end))
            groups_removed += 1

            # Check if removing these groups brings us within budget
            candidate = [m for j, m in enumerate(messages) if j not in indices_to_remove]
            candidate_tokens = self._count_tokens(candidate, model_run_config)
            logger.debug(
                "[_trim_kept_history] Removed group %d (indices %d-%d), "
                "candidate_messages=%d, candidate_tokens=%d",
                groups_removed, group_start, group_end - 1,
                len(candidate), candidate_tokens,
            )
            if candidate_tokens <= budget_tokens:
                logger.info(
                    "[_trim_kept_history] Within budget after removing %d tool groups",
                    groups_removed,
                )
                break

        # Apply the accumulated removal
        before_removal = len(messages)
        messages = [m for j, m in enumerate(messages) if j not in indices_to_remove]
        logger.info(
            "[_trim_kept_history] Removed %d messages (%d tool groups), "
            "remaining=%d messages",
            before_removal - len(messages), groups_removed, len(messages),
        )

        # Repair any orphan pairs
        before_repair = len(messages)
        messages = self._repair_tool_pairs(messages)
        if before_repair != len(messages):
            logger.info(
                "[_trim_kept_history] Repaired orphan tool pairs: messages %d -> %d",
                before_repair, len(messages),
            )

        final_tokens = self._count_tokens(messages, model_run_config)
        logger.info(
            "[_trim_kept_history] DONE: "
            "final_messages=%d, final_tokens=%d, budget_tokens=%d, "
            "tokens_saved=%d",
            len(messages), final_tokens, budget_tokens,
            initial_tokens - final_tokens,
        )
        return messages

    def _identify_tool_call_groups(self, messages: List) -> List[tuple[int, int]]:
        """
        Identify tool call groups within a single user turn.

        A group is: [reasoning?] [output_message?] [function_call] [function_call_output]
        Starts scanning from index 1 (skipping the leading user message).

        Returns:
            List of (start_index, end_index_exclusive) tuples for each group,
            ordered from oldest to newest.
        """
        groups: list[tuple[int, int]] = []
        i = 1  # skip the first user message
        while i < len(messages):
            # Skip user messages (shouldn't happen within a single turn, but be safe)
            if self.is_user_message(messages[i]):
                i += 1
                continue

            # Start of a potential tool call group
            group_start = i

            # Scan consecutive assistant messages
            while i < len(messages) and self.is_assistant_message(messages[i]):
                i += 1

            # Check for function_call_output following the assistant messages
            if i < len(messages) and self.is_function_response(messages[i]):
                i += 1  # include the function_call_output
                groups.append((group_start, i))
            else:
                # No function_call_output — this is a trailing assistant block
                # (e.g. final response), don't treat as removable group
                break

        return groups

    # ── compressed history assembly ─────────────────────────────────

    def create_compressed_message_history(
        self, header_message: List[dict], summary: str, history_to_keep: List[dict]
    ) -> List[dict]:
        """
        Create a compressed message history with summary integration.

        Builds a new message history that includes:
        - Header messages (typically the first user message)
        - Summary of compressed conversations
        - Recent messages to preserve

        Args:
            header_message: Initial messages to keep at the beginning
            summary: Summary text of compressed conversations
            history_to_keep: Recent messages to preserve after compression

        Returns:
            List of compressed messages with integrated summary
        """
        summary_response_message = {
            "role": "user",
            "content": f"{summary}",
        }

        summary_acknowledgment_message = {
            "role": "assistant",
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "Got it. Thanks for the additional context!",
                }
            ],
        }

        # Build common messages that always appear
        result = header_message + [summary_response_message]

        # Add acknowledgment and history if we have messages to keep
        if history_to_keep:
            if self.is_user_message(history_to_keep[0]):
                # If the first message to keep is a user message, add acknowledgment
                result.append(summary_acknowledgment_message)
            # If the first message to keep is an assistant message,
            # summary itself is the user message, so no need to add acknowledgment to keep the sequence correct
            result.extend(history_to_keep)

        return result


def _resolve_strategy_by_name(name: str) -> CompactionStrategy | None:
    """Resolve a compaction strategy by its registered name.

    Returns:
        Strategy instance, or None if name is unrecognized.
    """
    # Lazy imports to avoid circular dependency
    from .header_summary_compaction_strategy import SummarizeWithHeaderCompaction
    from .turn_prune_compaction_strategy import TurnPruneSummaryCompaction

    registry: dict[str, type] = {
        "header_summary": SummarizeWithHeaderCompaction,
        "turn_prune_summary": TurnPruneSummaryCompaction,
    }
    cls = registry.get(name)
    return cls() if cls else None


def get_compaction_strategy(context: "CodeAgentContext") -> CompactionStrategy:
    """
    Factory: select the appropriate compaction strategy.

    Priority:
      1. User-configured strategy name (from conf.yaml `compaction_strategy`)
      2. Auto-detect based on session mode:
         - IM mode → TurnPruneSummaryCompaction
         - CLI/TUI mode → SummarizeWithHeaderCompaction

    Recognized strategy names:
      - "header_summary"      → SummarizeWithHeaderCompaction (CLI/TUI default)
      - "turn_prune_summary"  → TurnPruneSummaryCompaction (IM default)

    Args:
        context: The code agent context

    Returns:
        CompactionStrategy instance appropriate for the session mode.
    """
    # 1. User-configured override takes highest priority
    user_strategy = context.compaction_strategy_name
    if user_strategy:
        strategy = _resolve_strategy_by_name(user_strategy)
        if strategy:
            logger.info(f"Using user-configured compaction strategy: {user_strategy}")
            return strategy
        logger.warning(
            f"Unknown compaction_strategy '{user_strategy}', "
            f"falling back to auto-detection. "
            f"Valid options: header_summary, turn_prune_summary"
        )

    # 2. Auto-detect based on session mode
    if context.im_mode:
        # IM mode uses the dedicated multi-layer pipeline
        from .turn_prune_compaction_strategy import TurnPruneSummaryCompaction
        return TurnPruneSummaryCompaction()
    from .header_summary_compaction_strategy import SummarizeWithHeaderCompaction
    return SummarizeWithHeaderCompaction()
