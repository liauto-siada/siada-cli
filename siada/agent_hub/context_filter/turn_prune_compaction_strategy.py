"""
Turn-prune-summary compaction strategy: multi-layer context compression.

Pipeline:
  Layer 1: Tool result truncation — head+tail large outputs (no LLM)
  Layer 2: Prune-then-summarize — prune oldest messages to budget,
           then single LLM structured summarization (at most 1 LLM call)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Tuple, TYPE_CHECKING

from siada.agent_hub.coder.prompt.im_compaction_prompt import (
    get_im_compaction_system_prompt,
    get_im_compaction_user_prompt,
)
from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionResult,
    CompactionStrategy,
)
from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.models.model_run_config import ModelRunConfig


# ── Strategy ─────────────────────────────────────────────────────────

class TurnPruneSummaryCompaction(CompactionStrategy):
    """
    Turn-prune-summary compaction: multi-layer context compression pipeline.

    Extends CompactionStrategy ABC so it can be used via the unified
    get_compaction_strategy() → strategy.should_compact() → strategy.compact()
    flow in ApiMessageTransferFilter.

    Layer 1: Tool result truncation (no LLM)
    Layer 2: Prune-then-summarize (at most 1 LLM call)

    Default strategy for IM mode. Can also be explicitly selected via
    conf.yaml `compaction_strategy: turn_prune_summary`.
    """

    # ── Configuration ────────────────────────────────────────────────

    TOOL_RESULT_CONTEXT_RATIO = 0.30    # single tool_result max 30% of context
    TOOL_RESULT_HARD_LIMIT = 400_000    # absolute char limit per tool_result

    DEFAULT_RECENT_BOUNDARIES_PRESERVE = 6  # recent boundaries (user/tool_output) kept verbatim

    # ── CompactionStrategy ABC implementation ────────────────────────

    @property
    def token_threshold_ratio(self) -> float:
        return 0.7

    @property
    def preserve_ratio(self) -> float:
        return 0.5  # not directly used; split logic uses DEFAULT_RECENT_BOUNDARIES_PRESERVE

    @property
    def summary_budget_ratio(self) -> float:
        """Max portion of context window for the LLM summarization call."""
        return 0.75

    # ── Prompt overrides for IM mode ─────────────────────────────────

    def _get_compaction_system_prompt(self) -> str:
        return get_im_compaction_system_prompt()

    def _get_compaction_user_prompt(self) -> str:
        return get_im_compaction_user_prompt()

    # ── compact entry point ──────────────────────────────────────────

    async def _compact_impl(
        self,
        model_run_config: "ModelRunConfig",
        real_api_messages: List,
        *,
        fixed_overhead_tokens: int = 0,
    ) -> CompactionResult:
        """
        CompactionStrategy ABC interface: compact messages and return a
        CompactionResult.

        `_do_compact()` already produces exactly this shape (with the
        richer `summary` field populated too), so this simply delegates.
        """
        return await self._do_compact(
            model_run_config, real_api_messages,
            fixed_overhead_tokens=fixed_overhead_tokens,
        )

    async def _do_compact(
        self,
        model_run_config: "ModelRunConfig",
        messages: List,
        *,
        fixed_overhead_tokens: int = 0,
    ) -> CompactionResult:
        """
        Execute the full compaction pipeline (internal, returns CompactionResult).

        Flow:
          1. Split: keep recent N boundary segments verbatim, rest → to_summarize
          2. If to_summarize is too long for LLM, truncate tool results + prune oldest
          3. Single LLM call to summarize
          4. Assemble: [summary] + [recent verbatim]
        """
        _t_compact_start = time.perf_counter()

        # Split: recent N turns kept verbatim, older turns → to_summarize
        _t0 = time.perf_counter()
        recent, to_summarize = self._split_recent_turns(messages)
        _t_split = time.perf_counter() - _t0

        if not to_summarize:
            return CompactionResult(messages=messages, compacted=False)

        # Prune + truncate tool results so it fits the LLM budget
        _t0 = time.perf_counter()
        to_summarize = self._prepare_for_summarization(
            to_summarize, model_run_config,
            fixed_overhead_tokens=fixed_overhead_tokens,
        )
        _t_prepare = time.perf_counter() - _t0

        if not to_summarize:
            logger.info(
                "[PERF][TurnPruneSummaryCompaction._do_compact] input_messages=%d "
                "compacted=False (nothing left after prepare) | split=%.1fms "
                "prepare=%.1fms total=%.1fms",
                len(messages), _t_split * 1000, _t_prepare * 1000,
                (time.perf_counter() - _t_compact_start) * 1000,
            )
            return CompactionResult(messages=recent, compacted=False)

        # Single LLM call to summarize (uses base class template method)
        _t0 = time.perf_counter()
        summary = await self.call_llm_to_compact(model_run_config, to_summarize)
        _t_llm_summarize = time.perf_counter() - _t0

        if not summary:
            logger.info(
                "[PERF][TurnPruneSummaryCompaction._do_compact] input_messages=%d "
                "compacted=False (no summary returned) | split=%.1fms "
                "prepare=%.1fms llm_summarize=%.1fms total=%.1fms",
                len(messages), _t_split * 1000, _t_prepare * 1000,
                _t_llm_summarize * 1000,
                (time.perf_counter() - _t_compact_start) * 1000,
            )
            return CompactionResult(messages=messages, compacted=False)

        compacted = self._assemble_compacted(summary, recent)
        logger.info(
            "[PERF][TurnPruneSummaryCompaction._do_compact] input_messages=%d "
            "output_messages=%d compacted=True | split=%.1fms prepare=%.1fms "
            "llm_summarize=%.1fms total=%.1fms",
            len(messages), len(compacted), _t_split * 1000, _t_prepare * 1000,
            _t_llm_summarize * 1000,
            (time.perf_counter() - _t_compact_start) * 1000,
        )
        return CompactionResult(
            messages=compacted, summary=summary, compacted=True
        )

    # ── Tool result truncation ───────────────────────────────────────

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

    # ── Prune-then-summarize ─────────────────────────────────────────

    def _split_recent_turns(self, messages: List) -> Tuple[List, List]:
        """
        Split messages into (recent_verbatim, to_summarize).

        Uses fine-grained boundary-based splitting. Boundaries are user
        messages and the position right after function_call_output messages.
        The last N such segment-start positions are kept verbatim.
        """
        split_candidates: set[int] = set()
        for i, m in enumerate(messages):
            if self.is_user_message(m):
                split_candidates.add(i)
            elif self.is_function_response(m) and i + 1 < len(messages):
                split_candidates.add(i + 1)

        sorted_candidates = sorted(split_candidates)

        if len(sorted_candidates) <= self.DEFAULT_RECENT_BOUNDARIES_PRESERVE:
            return messages[:], []  # too few boundaries, nothing to summarize

        split_idx = sorted_candidates[-self.DEFAULT_RECENT_BOUNDARIES_PRESERVE]
        return messages[split_idx:], messages[:split_idx]

    def _prepare_for_summarization(
        self,
        messages: List,
        model_run_config: "ModelRunConfig",
        *,
        fixed_overhead_tokens: int = 0,
    ) -> List:
        """
        Prepare to-summarize messages for the LLM call.

        1. Truncate oversized tool results
        2. If still too long, prune oldest messages to fit the LLM budget
        """
        context_window = model_run_config.context_window

        # Truncate oversized tool results first
        messages = self._truncate_tool_results(messages, context_window)

        # If content exceeds LLM summary budget, prune from oldest end
        budget_tokens = int(context_window * self.summary_budget_ratio) - fixed_overhead_tokens
        if self._count_tokens(messages, model_run_config) > budget_tokens:
            messages = self._prune_messages_to_token_budget(
                messages, budget_tokens, model_run_config,
            )

        return messages

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
