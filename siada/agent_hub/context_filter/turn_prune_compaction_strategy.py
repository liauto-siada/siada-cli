"""
Turn-prune-summary compaction strategy: multi-layer context compression.

Pipeline:
  Layer 1: Turn limit — keep most recent N user turns (no LLM)
  Layer 2: Tool result truncation — head+tail large outputs (no LLM)
  Layer 3: Prune-then-summarize — prune oldest messages to budget,
           then single LLM structured summarization (at most 1 LLM call)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Tuple, TYPE_CHECKING

from agents.models.chatcmpl_converter import Converter
from siada.agent_hub.context_filter.utils import calculate_tokens_with_fallback, estimate_tokens
from siada.agent_hub.coder.prompt.im_compaction_prompt import (
    get_im_compaction_system_prompt,
    get_im_compaction_user_prompt,
)
from siada.agent_hub.context_filter.compaction_strategy import CompactionError, CompactionStrategy
from siada.provider.client_factory import get_client
from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.models.model_run_config import ModelRunConfig


# ── Result model ─────────────────────────────────────────────────────

@dataclass
class CompactionResult:
    """Result of the IM compaction pipeline."""

    messages: List                      # compacted message list
    summary: str | None = None          # generated summary (for persistence / cascading)
    compacted: bool = False             # whether LLM compaction actually triggered


# ── Strategy ─────────────────────────────────────────────────────────

class TurnPruneSummaryCompaction(CompactionStrategy):
    """
    Turn-prune-summary compaction: multi-layer context compression pipeline.

    Extends CompactionStrategy ABC so it can be used via the unified
    get_compaction_strategy() → strategy.should_compact() → strategy.compact()
    flow in ApiMessageTransferFilter.

    Layer 1: Turn limit (no LLM)
    Layer 2: Tool result truncation (no LLM)
    Layer 3: Prune-then-summarize (at most 1 LLM call)

    All Layer 1+2 logic (turn keeping, tool pair repair, tool result
    truncation) lives directly in this class — there is no separate
    truncation class.

    Default strategy for IM mode. Can also be explicitly selected via
    conf.yaml `compaction_strategy: turn_prune_summary`.
    """

    # ── Configuration ────────────────────────────────────────────────

    TOOL_RESULT_CONTEXT_RATIO = 0.30    # single tool_result max 30% of context
    TOOL_RESULT_HARD_LIMIT = 400_000    # absolute char limit per tool_result

    DEFAULT_RECENT_BOUNDARIES_PRESERVE = 6  # recent boundaries (user/tool_output) kept verbatim
    COMPACTION_TRIGGER_RATIO = 0.70     # trigger Layer 3 at 70% context window
    SUMMARY_BUDGET_RATIO = 0.75         # max context share for to-summarize content
    SAFETY_MARGIN = 1.2                 # 20% token estimation buffer

    # failure detection keywords in tool result output
    _FAILURE_KEYWORDS = (
        "error", "exception", "traceback", "failed", "failure",
        "errno", "exitcode", "exit code", "command failed",
    )

    # ── CompactionStrategy ABC implementation ────────────────────────

    @property
    def token_threshold_ratio(self) -> float:
        return self.COMPACTION_TRIGGER_RATIO

    @property
    def preserve_ratio(self) -> float:
        return 0.5  # not directly used; split logic uses DEFAULT_RECENT_BOUNDARIES_PRESERVE


    async def compact(
        self,
        context: "CodeAgentContext",
        real_api_messages: List,
    ) -> List:
        """
        CompactionStrategy ABC interface: compact messages and return List.

        Delegates to _do_compact() which returns a richer CompactionResult.
        """
        result = await self._do_compact(context, real_api_messages)
        return result.messages

    async def _do_compact(
        self,
        context: "CodeAgentContext",
        messages: List,
        *,
        previous_summary: str | None = None,
    ) -> CompactionResult:
        """
        Execute the full compaction pipeline (internal, returns CompactionResult).

        Key principle: do NOT discard old turns upfront. Instead, split the
        history into recent (verbatim) and older (to-summarize), then
        generate a structured LLM summary of the older portion. Only prune
        the to-summarize portion if it exceeds the LLM's budget.

        Flow:
          1. Split: keep recent N boundary segments (user/tool_output)
             verbatim, rest → to_summarize
          2. If to_summarize is too long for LLM, prune oldest + truncate
             tool results to fit the summary budget
          3. Single LLM call to summarize (with stats fallback)
          4. Assemble: [summary] + [recent verbatim]

        Returns:
            CompactionResult with compacted messages, summary, and flag.
        """
        # Split: recent N turns kept verbatim, older turns → to_summarize
        recent, to_summarize = self._split_recent_turns(messages)

        if not to_summarize:
            # Too few turns to summarize, nothing to compact
            return CompactionResult(messages=messages, compacted=False)

        # Prune + truncate tool results in to_summarize so it fits the LLM budget
        to_summarize = self._prepare_for_summarization(to_summarize, context)

        if not to_summarize:
            # Nothing left after pruning, just return recent
            return CompactionResult(messages=recent, compacted=False)

        # TODO: tool failure extraction temporarily disabled
        # tool_failures = self._extract_tool_failures(to_summarize)

        # Single LLM call to summarize
        summary = await self._call_llm_summarize(
            context,
            to_summarize,
            previous_summary=previous_summary,
            tool_failures=None,
        )

        compacted = self._assemble_compacted(summary, recent)
        return CompactionResult(
            messages=compacted, summary=summary, compacted=True
        )

    # ── Layer 1: Turn truncation ─────────────────────────────────────

    def _keep_recent_turns(self, messages: List, max_turns: int) -> List:
        """Keep the most recent max_turns user turns and everything after them."""
        user_indices = [
            i for i, msg in enumerate(messages) if self.is_user_message(msg)
        ]

        if len(user_indices) <= max_turns:
            return messages[:]

        cut_index = user_indices[-max_turns]
        return messages[cut_index:]

    # ── Tool pair repair ─────────────────────────────────────────────

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
                        # Check if prev is a function_call (stop boundary)
                        prev_use_ids = self._extract_tool_use_ids(prev)
                        if prev_use_ids:
                            break
                        # prev is reasoning or output_message, remove it
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

    # ── Layer 2: Tool result truncation ──────────────────────────────

    def _truncate_tool_results(self, messages: List, context_window: int) -> List:
        """Truncate oversized tool_result messages with head+tail strategy."""
        max_chars = min(
            int(context_window * 4 * self.TOOL_RESULT_CONTEXT_RATIO),
            self.TOOL_RESULT_HARD_LIMIT,
        )

        result = []
        for msg in messages:
            if self.is_function_response(msg):
                msg = self._truncate_single_tool_result(msg, max_chars)
            result.append(msg)
        return result

    def _truncate_single_tool_result(self, msg, max_chars: int):
        """Truncate a single tool result if its text content exceeds max_chars."""
        text = self._get_tool_result_text(msg)
        if text is None or len(text) <= max_chars:
            return msg

        half = max_chars // 2
        truncated_text = (
            text[:half]
            + f"\n\n... [truncated {len(text) - max_chars} characters] ...\n\n"
            + text[-half:]
        )
        return self._set_tool_result_text(msg, truncated_text)

    @staticmethod
    def _get_tool_result_text(msg) -> str | None:
        """Extract text content from a tool result message."""
        if isinstance(msg, dict):
            output = msg.get("output")
            if isinstance(output, str):
                return output
            content = msg.get("content")
            if isinstance(content, str):
                return content
        else:
            output = getattr(msg, "output", None)
            if isinstance(output, str):
                return output
        return None

    @staticmethod
    def _set_tool_result_text(msg, text: str):
        """Set text content on a tool result message, returning a copy if dict."""
        if isinstance(msg, dict):
            new_msg = msg.copy()
            if "output" in new_msg:
                new_msg["output"] = text
            elif "content" in new_msg:
                new_msg["content"] = text
            return new_msg
        else:
            try:
                msg.output = text
            except Exception:
                pass
            return msg

    # ── Layer 3: Prune-then-summarize ────────────────────────────────

    def _split_recent_turns(self, messages: List) -> Tuple[List, List]:
        """
        Split messages into (recent_verbatim, to_summarize).

        Uses fine-grained boundary-based splitting instead of user-turn-based.
        Boundaries are user messages and function_call_output (tool output)
        messages. This allows splitting within a single long user turn that
        triggers many tool calls, avoiding the edge case where one huge turn
        cannot be compacted at all.

        A new segment starts:
          - At a user message (same as the old behavior)
          - Right after a function_call_output (the tool pair is complete,
            next reasoning/assistant items begin a new segment)

        The last N such segment-start positions are kept verbatim.
        Everything before goes to summarization.
        """
        # Collect valid segment-start indices (deduplicated, sorted)
        split_candidates: set[int] = set()
        for i, m in enumerate(messages):
            if self.is_user_message(m):
                # A user message is itself the start of a segment
                split_candidates.add(i)
            elif self.is_function_response(m) and i + 1 < len(messages):
                # After a tool output, the next message starts a new segment
                split_candidates.add(i + 1)

        sorted_candidates = sorted(split_candidates)

        if len(sorted_candidates) <= self.DEFAULT_RECENT_BOUNDARIES_PRESERVE:
            return messages[:], []  # too few boundaries, nothing to summarize

        split_idx = sorted_candidates[-self.DEFAULT_RECENT_BOUNDARIES_PRESERVE]
        return messages[split_idx:], messages[:split_idx]

    def _prepare_for_summarization(
        self, messages: List, context: "CodeAgentContext"
    ) -> List:
        """
        Prepare to-summarize messages for the LLM call.

        1. Truncate oversized tool results (so they don't blow the budget)
        2. If still too long, prune oldest messages to fit the LLM budget
        """
        context_window = context.model_run_config.context_window

        # Truncate oversized tool results first
        messages = self._truncate_tool_results(messages, context_window)

        # If content exceeds LLM summary budget, prune from oldest end
        budget_tokens = int(context_window * self.SUMMARY_BUDGET_RATIO)
        if self._count_tokens(messages, context) > budget_tokens:
            messages = self._prune_to_budget(messages, context)

        return messages

    def _prune_to_budget(
        self, messages: List, context: "CodeAgentContext"
    ) -> List:
        """
        Prune messages from the oldest end so the total fits within
        SUMMARY_BUDGET_RATIO of the context window.

        Uses binary search on user turn boundaries for efficiency
        (O(log N) token calculations instead of O(N)).

        Repairs orphan tool pairs after pruning.
        """
        budget_tokens = int(
            context.model_run_config.context_window * self.SUMMARY_BUDGET_RATIO
        )

        # Find all user turn boundaries (each is a valid cut point)
        user_indices = [
            i for i, m in enumerate(messages) if self.is_user_message(m)
        ]
        if not user_indices:
            return []

        # Binary search: find the earliest user turn boundary where
        # messages[boundary:] fits within budget
        lo, hi = 0, len(user_indices) - 1
        best = hi  # worst case: keep only the last user turn

        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = messages[user_indices[mid]:]
            if self._count_tokens(candidate, context) <= budget_tokens:
                best = mid
                hi = mid - 1  # try to keep more (earlier boundary)
            else:
                lo = mid + 1  # need to drop more old turns

        messages = messages[user_indices[best]:]

        # Repair orphan tool pairs caused by pruning
        messages = self._repair_tool_pairs(messages)
        return messages

    def _extract_tool_failures(self, messages: List) -> list[dict]:
        """
        Scan messages for failed tool results and extract structured info.
        """
        failures: list[dict] = []
        for msg in messages:
            if not self.is_function_response(msg):
                continue
            text = self._get_tool_result_text(msg)
            if text and self._looks_like_failure(text):
                failures.append({
                    "tool_name": self._find_tool_name(msg, messages),
                    "call_id": (
                        msg.get("call_id") if isinstance(msg, dict)
                        else getattr(msg, "call_id", None)
                    ),
                    "summary": text[:500],  # first 500 chars of error
                })
        return failures

    def _looks_like_failure(self, text: str) -> bool:
        """Heuristic: check if tool output looks like an error."""
        lower = text[:2000].lower()
        return any(kw in lower for kw in self._FAILURE_KEYWORDS)

    @staticmethod
    def _find_tool_name(tool_result_msg, messages: List) -> str:
        """Find the tool name by matching call_id to a preceding function_call."""
        call_id = (
            tool_result_msg.get("call_id")
            if isinstance(tool_result_msg, dict)
            else getattr(tool_result_msg, "call_id", None)
        )
        if not call_id:
            return "unknown"

        for msg in messages:
            if isinstance(msg, dict):
                if msg.get("type") == "function_call" and msg.get("call_id") == call_id:
                    return msg.get("name", "unknown")
            else:
                if (
                    getattr(msg, "type", None) == "function_call"
                    and getattr(msg, "call_id", None) == call_id
                ):
                    return getattr(msg, "name", "unknown")
        return "unknown"

    async def _call_llm_summarize(
        self,
        context: "CodeAgentContext",
        history_to_compact: List,
        *,
        previous_summary: str | None = None,
        tool_failures: list[dict] | None = None,
    ) -> str:
        """Call LLM to generate a structured summary of the given message history."""
        provider = context.provider
        model = context.model_run_config.model_name

        user_prompt = get_im_compaction_user_prompt(
            previous_summary=previous_summary,
            tool_failures=tool_failures,
        )

        compact_messages = Converter.items_to_messages(history_to_compact) + [
            {"role": "user", "content": user_prompt}
        ]
        compact_messages.insert(
            0, {"role": "system", "content": get_im_compaction_system_prompt()}
        )

        llm_client = get_client(provider)

        complete_kwargs = {
            "model": model,
            "messages": compact_messages,
        }

        # Only add empty tools list for Anthropic/Claude models to avoid litellm error
        if "anthropic" in model.lower() or "claude" in model.lower():
            complete_kwargs["tools"] = []

        response = await llm_client.completion(**complete_kwargs)

        if response and response.choices and response.choices[0].message:
            raw_content = response.choices[0].message.content
            return self._extract_summary(raw_content)

        raise ValueError("LLM returned empty response for compaction")

    @staticmethod
    def _extract_summary(content: str | None) -> str:
        """Extract the <context>...</context> block from LLM response."""
        if not content:
            raise ValueError("Empty LLM response content")

        match = re.search(r"<context>.*?</context>", content, re.DOTALL)
        if match:
            return match.group(0)
        return content

    def _generate_stats_description(self, messages: List) -> str:
        """
        Last-resort fallback: generate a statistical description when
        LLM summarization completely fails.
        """
        user_count = sum(1 for m in messages if self.is_user_message(m))
        assistant_count = sum(1 for m in messages if self.is_assistant_message(m))
        tool_count = sum(1 for m in messages if self.is_function_response(m))

        return (
            f"<context>\n"
            f"## Conversation Overview\n"
            f"This is a statistical summary (LLM summarization failed).\n"
            f"The conversation contained {user_count} user messages, "
            f"{assistant_count} assistant messages, and {tool_count} tool calls.\n"
            f"The messages have been truncated to fit the context window.\n"
            f"</context>"
        )

    def _assemble_compacted(self, summary: str, recent: List) -> List:
        """
        Assemble the final compacted message list:
        [summary_as_user_msg] + [ack_if_needed] + [recent_verbatim]
        """
        summary_msg = {
            "role": "user",
            "content": summary,
        }

        ack_msg = {
            "role": "assistant",
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "Got it. Thanks for the additional context!",
                }
            ],
        }

        result = [summary_msg]

        if recent:
            if self.is_user_message(recent[0]):
                # Insert acknowledgment so user->user is avoided
                result.append(ack_msg)
            result.extend(recent)

        return result

    # ── Token counting ───────────────────────────────────────────────

    def _count_tokens(
        self, messages: List, context: "CodeAgentContext | None" = None
    ) -> int:
        """
        Count tokens using litellm when context is available,
        falling back to rough char-based estimate otherwise.

        Delegates to shared utilities in utils module.

        Args:
            messages: message items to count
            context: if provided, uses litellm model-aware tokenizer
        """
        model_name = context.model_run_config.model_name if context is not None else None
        return calculate_tokens_with_fallback(model_name, messages)

    @staticmethod
    def _estimate_tokens(messages: List) -> int:
        """Rough token estimate: ~4 chars per token with safety margin.

        Delegates to shared estimate_tokens() in utils module.
        Kept for backward compatibility.
        """
        return estimate_tokens(messages)

    def _should_compact(
        self, token_count: int, context: "CodeAgentContext"
    ) -> bool:
        """Check if Layer 3 compaction is needed based on token count."""
        threshold = (
            context.model_run_config.context_window * self.COMPACTION_TRIGGER_RATIO
        )
        return token_count >= threshold
