"""
Summarize-with-header compaction strategy for CLI/TUI sessions.

Conservative approach: keeps the first user-assistant pair as a header,
summarizes older messages via LLM, and preserves recent message tail.
"""
from __future__ import annotations

import time
from typing import List, TYPE_CHECKING

from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionResult,
    CompactionStrategy,
)
from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.models.model_run_config import ModelRunConfig


class SummarizeWithHeaderCompaction(CompactionStrategy):
    """
    Conservative summarize-and-keep-header compaction.

    Triggers at 70% context window, preserves 30% of recent messages.
    Keeps the first user-assistant pair as a header in the compressed output,
    followed by an LLM-generated summary and the recent message tail.

    Typically used for CLI / TUI sessions.
    """

    @property
    def token_threshold_ratio(self) -> float:
        return 0.7

    @property
    def preserve_ratio(self) -> float:
        return 0.3

    @property
    def summary_budget_ratio(self) -> float:
        """Max portion of context window for the LLM summarization call.

        Lowered from 0.9 to 0.75 to leave headroom for token estimation
        inaccuracy (tiktoken vs Anthropic native counting) and the extra
        compact system/user prompts appended by call_llm_to_compact().
        """
        return 0.75

    @property
    def keep_budget_ratio(self) -> float:
        """Budget ratio for the kept history portion after compaction."""
        return 0.60

    async def _compact_impl(
        self,
        model_run_config: "ModelRunConfig",
        real_api_messages,
        *,
        fixed_overhead_tokens: int = 0,
    ) -> CompactionResult:
        _t_compact_start = time.perf_counter()
        _t0 = time.perf_counter()
        compress_before_index = self.find_index_after_fraction(
            history=real_api_messages, fraction=1 - self.preserve_ratio
        )
        _t_find_split = time.perf_counter() - _t0

        # Snap forward past assistant/function messages, advancing the split
        # point so that every function_call already in the compress segment
        # also has its matching function_call_output there.
        #
        # We maintain a queue ``open_call_ids`` of function_call ids whose
        # paired function_call_output has not yet been seen:
        #   * encountering an assistant function_call → enqueue its call_id
        #   * encountering a function_call_output     → dequeue its call_id
        # While this queue is non-empty we MUST keep advancing — otherwise
        # the compress segment would carry orphan fc's whose fco's leak into
        # keep segment (or vice-versa), producing the Responses API 400:
        #   "No tool call found for function call output with call_id ..."
        #
        # Bug case the queue fixes
        # -----------------------
        # Sequence: ... fc_A fc_B fc_C fco_A fco_B fco_C
        # split lands on fco_A.
        # Old code did `compress += 1` then `break` on fco_A, leaving
        # fco_B / fco_C in keep segment as orphans. The queue keeps
        # advancing through fco_B and fco_C until all three fc's are closed.
        # ``first_open_fc_idx`` tracks the absolute index of the earliest
        # still-unmatched fc seen so far (the start of the most recent
        # tool-call group). We use it as a safe retreat point: if the
        # forward sweep would consume every remaining message and leave
        # ``history_to_keep`` empty, we rewind compress_before_index to this
        # index so the entire group stays in keep segment intact.
        _t0 = time.perf_counter()
        open_call_ids: set = set()
        first_open_fc_idx: int = -1
        for i, msg in enumerate(real_api_messages[:compress_before_index]):
            if self.is_assistant_message(msg):
                ids = self._extract_tool_use_ids(msg)
                if ids:
                    if not open_call_ids:
                        first_open_fc_idx = i
                    open_call_ids.update(ids)
            elif self.is_function_response(msg):
                for cid in self._extract_tool_result_ids(msg):
                    open_call_ids.discard(cid)
                if not open_call_ids:
                    first_open_fc_idx = -1

        n = len(real_api_messages)
        while compress_before_index < n and (
            self.is_assistant_message(real_api_messages[compress_before_index])
            or self.is_function_response(real_api_messages[compress_before_index])
        ):
            msg = real_api_messages[compress_before_index]
            if self.is_assistant_message(msg):
                ids = self._extract_tool_use_ids(msg)
                if ids:
                    if not open_call_ids:
                        first_open_fc_idx = compress_before_index
                    open_call_ids.update(ids)
            else:  # function_call_output
                for cid in self._extract_tool_result_ids(msg):
                    open_call_ids.discard(cid)
            compress_before_index += 1
            # Only stop *after* a function_response when the queue is fully
            # drained — i.e. every fc in compress segment has its fco in
            # compress segment too. We deliberately DO NOT clear
            # ``first_open_fc_idx`` here: if the sweep also reached EOF, the
            # block below will rewind to that index to keep the whole group
            # in keep segment.
            if (
                self.is_function_response(msg)
                and not open_call_ids
            ):
                break

        # Edge case: if the forward sweep consumed every message (would
        # leave keep segment empty) AND there are still unmatched fc's in
        # compress segment, retreat the split to before the earliest such
        # fc — i.e. the start of the most recent tool-call group. This
        # happens when the conversation ends with a parallel tool-call
        # group not followed by a user turn (e.g.
        #   user, msg, fc_A, fc_B, fc_C, fco_A, fco_B, fco_C
        # ) and the split lands inside the fco run.
        #
        # We skip ``adjust_compression_index_for_boundary_cases`` in this
        # branch because its case 2 only looks at the single fco at idx-1
        # and rewinds to that fco's first preceding assistant — for a
        # parallel group this lands on the LAST fco's previous fco (still
        # an fco), re-creating the orphan we just fixed.
        if compress_before_index >= n and first_open_fc_idx >= 0:
            compress_before_index = first_open_fc_idx
        else:
            compress_before_index = self.adjust_compression_index_for_boundary_cases(
                real_api_messages, compress_before_index
            )
        _t_snap_boundary = time.perf_counter() - _t0

        if compress_before_index <= 1:
            return CompactionResult(messages=real_api_messages, compacted=False)

        history_to_compress = real_api_messages[:compress_before_index]
        history_to_keep = real_api_messages[compress_before_index:]

        if not history_to_keep:
            raise ValueError("No messages to keep after compression")

        # Fallback 1: prune history_to_compress if it exceeds LLM summary budget,
        # so the summarization call itself won't fail due to context overflow.
        context_window = model_run_config.context_window
        summary_budget = int(context_window * self.summary_budget_ratio) - fixed_overhead_tokens
        _t0 = time.perf_counter()
        _t_prune_compress = 0.0
        if self._count_tokens(history_to_compress, model_run_config) > summary_budget:
            logger.info(
                "history_to_compress exceeds summary budget, "
                "pruning oldest turns to fit LLM context"
            )
            history_to_compress = self._prune_messages_to_token_budget(
                history_to_compress, summary_budget, model_run_config
            )
            _t_prune_compress = time.perf_counter() - _t0

        _t0 = time.perf_counter()
        summary = await self.call_llm_to_compact(
            model_run_config=model_run_config, history_to_compact=history_to_compress
        )
        _t_llm_summarize = time.perf_counter() - _t0

        if not summary:
            return CompactionResult(messages=real_api_messages, compacted=False)

        # Fallback 2: trim history_to_keep if it is too large, so the final
        # compacted result won't still exceed context window.
        # Strategy: keep from last user msg, then drop oldest tool call groups.
        keep_budget = int(context_window * self.keep_budget_ratio) - fixed_overhead_tokens
        _t0 = time.perf_counter()
        _t_trim_keep = 0.0
        if self._count_tokens(history_to_keep, model_run_config) > keep_budget:
            logger.info(
                "history_to_keep exceeds keep budget, "
                "trimming from last user message and pruning oldest tool groups"
            )
            history_to_keep = self._trim_kept_history(
                history_to_keep, model_run_config, keep_budget
            )
            _t_trim_keep = time.perf_counter() - _t0

        if not history_to_keep:
            raise ValueError("No messages to keep after trimming")

        compacted_messages = self.create_compressed_message_history(
            header_message=self.try_get_first_user_assistant_pair(
                real_api_messages, compress_before_index
            ),
            summary=summary,
            history_to_keep=history_to_keep,
        )
        logger.info(
            "[PERF][SummarizeWithHeaderCompaction.compact] input_messages=%d "
            "output_messages=%d | find_split=%.1fms snap_boundary=%.1fms "
            "prune_compress=%.1fms llm_summarize=%.1fms trim_keep=%.1fms "
            "total=%.1fms",
            len(real_api_messages), len(compacted_messages),
            _t_find_split * 1000, _t_snap_boundary * 1000,
            _t_prune_compress * 1000, _t_llm_summarize * 1000,
            _t_trim_keep * 1000,
            (time.perf_counter() - _t_compact_start) * 1000,
        )
        return CompactionResult(messages=compacted_messages, summary=summary, compacted=True)

