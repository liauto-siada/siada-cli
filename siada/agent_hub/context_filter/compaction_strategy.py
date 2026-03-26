"""
Compaction strategies for message history compression.

Uses Strategy pattern to separate different compression approaches:
- SummarizeWithHeaderCompaction: Conservative, keeps first user-assistant pair as header (CLI/TUI mode)
- SlidingWindowCompaction: Aggressive sliding-window, drops oldest turns first (IM/chat mode)
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

from agents.models.chatcmpl_converter import Converter
from siada.agent_hub.coder.prompt.compact_prompt import (
    _auto_compact_response,
    get_compact_system_prompt,
)
from siada.provider.client_factory import get_client
from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.models.model_run_config import ModelRunConfig


class CompactionError(Exception):
    """Raised when message compaction/truncation fails."""
    pass


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

    def should_compact(self, tokens_count: int, model_config: "ModelRunConfig") -> bool:
        """Check if compaction is needed based on token count and threshold."""
        threshold = model_config.context_window * self.token_threshold_ratio
        return tokens_count >= threshold

    @abstractmethod
    async def compact(
        self,
        context: "CodeAgentContext",
        real_api_messages: List,
    ) -> List:
        """
        Execute the compaction strategy.

        Args:
            context: The code agent context
            real_api_messages: All real API messages

        Returns:
            Compacted list of messages
        """
        ...

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

    async def call_llm_to_compact(
        self, context: "CodeAgentContext", history_to_compact: List
    ) -> str | None:
        """
        Call LLM to generate a summary of the given message history.

        Args:
            context: The code agent context (provides provider and model info)
            history_to_compact: Messages to summarize

        Returns:
            Extracted summary string, or None on failure
        """
        provider = context.provider
        model = context.model_run_config.model_name

        compact_messages = Converter.items_to_messages(history_to_compact) + [
            {"role": "user", "content": _auto_compact_response()}
        ]
        compact_messages.insert(
            0, {"role": "system", "content": get_compact_system_prompt()}
        )

        llm_client = get_client(provider)

        complete_kwargs = {
            "model": model,
            "messages": compact_messages,
        }

        # Only add empty tools list for Anthropic/Claude models with default provider to avoid litellm error
        if "anthropic" in model.lower() or "claude" in model.lower():
            complete_kwargs["tools"] = []
        response = await llm_client.completion(**complete_kwargs)

        if response and response.choices and response.choices[0].message:
            raw_content = response.choices[0].message.content
            return self._extract_summary(raw_content)
        return None

    @staticmethod
    def _extract_summary(content: str | None) -> str | None:
        """
        Extract the summary XML from the LLM response content.

        Args:
            content: The full LLM response content

        Returns:
            Extracted <context>...</context> block, or the full content if not found
        """
        if not content:
            return content

        match = re.search(r"<context>.*?</context>", content, re.DOTALL)
        if match:
            return match.group(0)
        return content

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

    async def compact(
        self,
        context,
        real_api_messages,
    ) -> List:
        compress_before_index = self.find_index_after_fraction(
            history=real_api_messages, fraction=1 - self.preserve_ratio
        )

        # Snap forward past assistant/function messages, but stop after a function response
        while compress_before_index < len(real_api_messages) and (
            self.is_assistant_message(real_api_messages[compress_before_index])
            or self.is_function_response(real_api_messages[compress_before_index])
        ):
            compress_before_index += 1
            if self.is_function_response(real_api_messages[compress_before_index - 1]):
                break

        compress_before_index = self.adjust_compression_index_for_boundary_cases(
            real_api_messages, compress_before_index
        )

        if compress_before_index <= 1:
            return real_api_messages

        history_to_compress = real_api_messages[:compress_before_index]
        history_to_keep = real_api_messages[compress_before_index:]

        if not history_to_keep:
            raise ValueError("No messages to keep after compression")

        summary = await self.call_llm_to_compact(
            context=context, history_to_compact=history_to_compress
        )

        if not summary:
            return real_api_messages

        return self.create_compressed_message_history(
            header_message=self.try_get_first_user_assistant_pair(
                real_api_messages, compress_before_index
            ),
            summary=summary,
            history_to_keep=history_to_keep,
        )


def _resolve_strategy_by_name(name: str) -> CompactionStrategy | None:
    """Resolve a compaction strategy by its registered name.

    Returns:
        Strategy instance, or None if name is unrecognized.
    """
    # Lazy import to avoid circular dependency
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
    return SummarizeWithHeaderCompaction()
