from __future__ import annotations
from pathlib import Path
import re
from typing import List, TYPE_CHECKING, Any

from siada.agent_hub.coder.prompt.compact_prompt import (
    _auto_compact_response,
    get_compact_system_prompt,
)
from siada.models.model_run_config import ModelRunConfig
from siada.provider.client_factory import get_client
from siada.session.task_message_state import RealApiMessage
from siada.utils import DirectoryUtils
from .utils import compute_message_signature
from agents.models.chatcmpl_converter import Converter
from siada.foundation.logging import logger


if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.session.task_message_state import RealApiMessage


# Compression thresholds
COMPRESSION_TOKEN_THRESHOLD = 0.7
COMPRESSION_PRESERVE_THRESHOLD = 0.3


class ApiMessageTransferFilter:
    """
    Filter that transfers real API messages to model input with token management.

    This filter assembles real API messages from the task message state,
    calculates token counts, and applies compression if needed.
    """

    async def filter(
        self, model_data: ModelInputData, agent: Any, context: CodeAgentContext
    ) -> None:
        """
        Transfer real API messages to model input.

        Args:
            model_data: The model input data to filter
            agent: The agent instance
            context: The code agent context
        """
        if not context.auto_compact:
            logger.warning(
                "Auto compact is disabled, skipping ApiMessageTransferFilter"
            )
            return

        origin_input = model_data.input
        try:
            # 1. build real message state with token counting
            real_api_messages, tokens_count, last_index, last_signature = (
                await self._build_real_message_state(context, model_data.instructions)
            )
            # 2. try compact the real api messages if too long
            compacted_messages = await self._try_compact_real_api_messages(
                context=context,
                real_api_messages=real_api_messages,
                tokens_count=tokens_count,
                model_config=context.model_run_config,
            )
            # Update the model input data
            model_data.input = compacted_messages
            # 3. sync the real messages to file session
            # only sync to save the compacted messages to file for debugging
            self._sync_api_message_to_file(context, compacted_messages)

            # update the real_messages
            context.task_message_state.set_real_messages(
                RealApiMessage(
                    real_api_history=compacted_messages,
                    last_index=last_index,
                    last_signature=last_signature,
                )
            )
        except Exception as e:
            logger.error(f"RealMessageTransferFilter error {e}")
            # rollback the state to the original
            model_data.input = origin_input
            context.task_message_state.set_real_messages(RealApiMessage())

    async def _try_compact_real_api_messages(
        self,
        context: "CodeAgentContext",
        real_api_messages: List,
        tokens_count: int,
        model_config: ModelRunConfig,
    ) -> List:
        """
        Try to compact the real API messages if they exceed the token limit.

        Args:
            real_api_messages: List of messages to compact
            tokens_count: Current token count
            model_config: Model configuration

        Returns:
            Compacted list of messages
        """
        threshold = model_config.context_window * COMPRESSION_TOKEN_THRESHOLD
        # for testing, set a minimum
        if tokens_count < threshold:
            return real_api_messages

        # find the fisrt user message after the threshold, the compression should be placed before the user message
        compress_before_index = self._find_index_after_fraction(
            history=real_api_messages, fraction=1 - COMPRESSION_PRESERVE_THRESHOLD
        )
        while compress_before_index < len(real_api_messages) and (
            self._is_assistant_message(real_api_messages[compress_before_index])
            or self._is_function_response(real_api_messages[compress_before_index])
        ):
            compress_before_index += 1
            if self._is_function_response(real_api_messages[compress_before_index - 1]):
                # find the first function response, stop here
                break

        # Handle boundary cases to ensure context integrity:
        # - If last message is a user message: keep it
        # - If last message is a tool call result: keep the complete sequence
        #   (including all preceding assistant messages: reasoning, response, and function call)
        # When compression index reaches the end, adjust it backwards to preserve these sequences
        compress_before_index = self._adjust_compression_index_for_boundary_cases(
            real_api_messages, compress_before_index
        )
        # if compress_before_index is 0 or 1, no need to compress
        if compress_before_index <= 1:
            return real_api_messages

        history_to_compress = real_api_messages[0:compress_before_index]
        history_to_keep = real_api_messages[compress_before_index:]

        if not history_to_keep:
            raise ValueError("No messages to keep after compression")

        summary = await self._call_llm_to_compact(
            context=context, history_to_compact=history_to_compress
        )

        if not summary:
            # print summary failed
            return real_api_messages

        return self._create_compressed_message_history(
            header_message=self._try_get_first_user_assistant_pair(
                real_api_messages, compress_before_index
            ),
            summary=summary,
            history_to_keep=history_to_keep,
        )

    def _try_get_first_user_assistant_pair(
        self, messages: List, compress_before_index: int
    ) -> List:
        """
        Try to find the first user-assistant message pair in the list.

        Args:
            messages: List of messages to search

        Returns:
            Index of the first user-assistant pair, or -1 if not found
        """
        first_message = messages[0]

        if len(messages) >= 2:
            # in case, only get the first user-assistant pair, ignore the sequence resoning items、functions call items
            if Converter.maybe_response_output_message(messages[1]):
                return [first_message, messages[1]]
        return [first_message]

    def _create_compressed_message_history(
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
        # summary_request_message = {
        #     "role": "assistant",
        #     "type": "message",
        #     "content": [
        #         {
        #             "type": "output_text",
        #             "text": "Got it.",
        #         }
        #     ],
        # }

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
            if self._is_user_message(history_to_keep[0]):
                # If the first message to keep is a user message, add acknowledgment
                result.append(summary_acknowledgment_message)
            # If the first message to keep is an assistant message,
            # summary itself is the user message, so no need to add acknowledgment to keep the sequence correct
            result.extend(history_to_keep)

        return result

    def _needs_full_refresh(
        self, last_index: int, last_signature: str, api_messages: List
    ) -> bool:
        """
        Determine if a full refresh is needed based on current state.

        Args:
            last_index: The last processed message index
            last_signature: The last processed message signature
            api_messages: Current API messages

        Returns:
            True if full refresh is needed, False otherwise
        """
        # Full refresh needed if:
        # 1. No previous state (last_index == -1)
        # 2. No previous signature (empty string)
        # 3. No new messages to process (last_index >= len(api_messages) - 1)
        return (
            last_index == -1
            or last_signature == ""
            or last_index >= len(api_messages) - 1
        )

    def _calculate_tokens(
        self, context: "CodeAgentContext", messages_or_text: List | str
    ) -> int:
        """
        Calculate token count for given messages.

        Args:
            context: The code agent context
            messages_or_text: List of messages or the text to count tokens for

        Returns:
            Token count for the messages
        """
        import litellm

        if isinstance(messages_or_text, str):
            return litellm.token_counter(
                model=context.model_run_config.model_name, text=messages_or_text
            )
        return litellm.token_counter(
            model=context.model_run_config.model_name,
            messages=Converter.items_to_messages(messages_or_text),
        )

    def _do_full_refresh(
        self,
        context: "CodeAgentContext",
        system_instructions: str,
        api_messages: List,
        current_tokens: int,
    ) -> tuple[List, int]:
        """
        Perform a full refresh of real API messages with token calculation.

        Args:
            context: The code agent context
            system_instructions: The system instructions to include in the message state
            api_messages: All API messages to copy
            current_tokens: Current token count

        Returns:
            Tuple of (refreshed_messages, updated_token_count)
        """
        real_api_messages = api_messages.copy()
        total_tokens = (
            current_tokens
            + self._calculate_tokens(context, system_instructions)
            + self._calculate_tokens(context, real_api_messages)
        )
        return real_api_messages, total_tokens

    def _try_incremental_update(
        self,
        context: "CodeAgentContext",
        system_instructions: str,
        api_messages: List,
        real_api_messages: List,
        last_index: int,
        last_signature: str,
        current_tokens: int,
    ) -> tuple[List, int]:
        """
        Try to perform incremental update of real API messages.

        Args:
            context: The code agent context
            api_messages: Current API messages
            real_api_messages: Existing real API messages
            last_index: Last processed message index
            last_signature: Last processed message signature
            current_tokens: Current token count

        Returns:
            Tuple of (updated_messages, updated_token_count)
        """
        # Check if the message at last_index still matches
        last_sync_message = api_messages[last_index]
        index_signature = compute_message_signature(last_sync_message)

        if index_signature == last_signature and last_index < len(api_messages) - 1:
            # Signatures match and there are new messages to add
            delta = api_messages[last_index + 1 :]

            # Calculate tokens appropriately
            if current_tokens == 0:
                # If no tokens recorded, calculate for all messages
                total_tokens = self._calculate_tokens(
                    context, system_instructions
                ) + self._calculate_tokens(context, api_messages)
            else:
                # Add tokens for new messages only
                delta_tokens = self._calculate_tokens(context, delta)
                total_tokens = current_tokens + delta_tokens

            # Add new messages to existing ones
            updated_messages = real_api_messages.copy() + delta
            return updated_messages, total_tokens
        else:
            # Signature mismatch or other issues: fall back to full refresh
            return self._do_full_refresh(context, system_instructions, api_messages, 0)

    def _update_tracking_info(self, api_messages: List) -> tuple[int, str]:
        """
        Update tracking information based on current API messages.

        Args:
            api_messages: Current API messages

        Returns:
            Tuple of (last_index, last_signature)
        """
        if api_messages:
            last_index = len(api_messages) - 1
            last_message = api_messages[-1]
            last_signature = compute_message_signature(last_message)
        else:
            last_index = -1
            last_signature = ""

        return last_index, last_signature

    def _find_index_after_fraction(self, history: List, fraction: float) -> int:
        """
        Find the index in history after a certain fraction of total content length.

        Args:
            history: List of messages/content items
            fraction: Fraction between 0 and 1 indicating where to split

        Returns:
            Index after the specified fraction of content

        Raises:
            ValueError: If fraction is not between 0 and 1
        """
        if fraction <= 0 or fraction >= 1:
            raise ValueError("Fraction must be between 0 and 1")

        import json

        # Calculate length of each content item
        content_lengths = [
            len(json.dumps(content, sort_keys=True, ensure_ascii=False))
            for content in history
        ]

        # Calculate total characters and target
        total_characters = sum(content_lengths)
        target_characters = total_characters * fraction

        # Find index where we exceed target characters
        characters_so_far = 0
        for i, length in enumerate(content_lengths):
            if characters_so_far >= target_characters:
                return i
            characters_so_far += length

        return len(content_lengths)

    async def _build_real_message_state(
        self, context: CodeAgentContext, system_instructions: str
    ) -> tuple[List, int, int, str]:
        """
        Build real message state with incremental updates and token counting.
        Synchronizes real API messages and tracks message changes efficiently.

        Args:
            context: The code agent context containing session and state
            system_instructions: The system instructions to include in the message state

        Returns:
            Tuple of (real_api_messages, total_token_count, last_index, last_signature)
        """
        # Get current state
        api_messages = context.task_message_state.get_messages()
        real_api_messages = context.task_message_state.get_real_messages()
        last_index = context.task_message_state.get_real_message_last_index()
        last_signature = context.task_message_state.get_real_message_last_signature()

        # Determine update strategy and execute
        if self._needs_full_refresh(last_index, last_signature, api_messages):
            # Perform full refresh
            real_api_messages, total_tokens = self._do_full_refresh(
                context, system_instructions, api_messages, 0
            )
        else:
            # Get current token count
            current_tokens = (
                context.session.state.usage.input_tokens
                if context.session.state.usage
                else 0
            )
            # Try incremental update
            real_api_messages, total_tokens = self._try_incremental_update(
                context,
                system_instructions,
                api_messages,
                real_api_messages,
                last_index,
                last_signature,
                current_tokens,
            )

        # Update tracking information
        updated_last_index, updated_last_signature = self._update_tracking_info(
            api_messages
        )

        return (
            real_api_messages,
            total_tokens,
            updated_last_index,
            updated_last_signature,
        )

    async def _call_llm_to_compact(
        self, context: "CodeAgentContext", history_to_compact: List
    ):
        provider = context.provider
        model = context.model_run_config.model_name

        def _build_compact_messages(history_to_compact: List) -> List:
            """Build messages for LLM compacting request."""
            compact_messages = Converter.items_to_messages(history_to_compact) + [
                {"role": "user", "content": _auto_compact_response()}
            ]
            compact_messages.insert(
                0, {"role": "system", "content": get_compact_system_prompt()}
            )
            return compact_messages

        llm_client = get_client(provider)

        complete_kwargs = {
            "model": model,
            "messages": _build_compact_messages(history_to_compact=history_to_compact),
        }
        
        # Only add empty tools list for Anthropic/Claude models with default provider to avoid litellm error
        if provider == "default" and (
            "anthropic" in model.lower() or "claude" in model.lower()
        ):
            complete_kwargs["tools"] = []
        
        response = await llm_client.completion(**complete_kwargs)

        if response and response.choices and response.choices[0].message:
            raw_content = response.choices[0].message.content
            # Extract the context XML from the response
            return self.extractSummary(raw_content)
        return None

    def extractSummary(self, content: str | None) -> str:
        """
        Extract the summary XML from the LLM response content.

        Args:
            content: The full LLM response content

        Returns:
            Extracted summary XML string
        """
        import re

        if not content:
            return content

        # Use regex to find the <context>...</context> block
        match = re.search(r"<context>.*?</context>", content, re.DOTALL)
        if match:
            return match.group(0)
        return content

    def _adjust_compression_index_for_boundary_cases(
        self, messages: List, compress_before_index: int
    ) -> int:
        """
        Adjust compression index to handle boundary cases where the index is at or near the end.
        
        This ensures we keep either:
        1. The last user message, or
        2. The complete tool-call-result pair (including the assistant message before the tool-call)
        
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
            if idx >= 0 and self._is_user_message(messages[idx]):
                return idx

            # Case 2: Last message is a function response - need to keep the complete sequence
            # Pattern: [user_message] -> [reasoning (optional)] -> [response] -> [function_call] -> [function_response]
            if idx >= 0 and self._is_function_response(messages[idx]):
                # Find the start of this tool call sequence
                # We need to include: function_response, function_call (assistant), and all assistant messages before
                function_response_idx = idx

                # Look for the function call (assistant message with tool call)
                if idx >= 1 and self._is_assistant_message(messages[idx - 1]):
                    function_call_idx = idx - 1

                    # Continue looking backwards for all consecutive assistant messages (reasoning, response, etc.)
                    # until we hit a non-assistant message (usually a user message)
                    start_idx = function_call_idx
                    while start_idx > 0 and self._is_assistant_message(messages[start_idx - 1]):
                        start_idx -= 1

                    # Return the index of the first assistant message in the sequence
                    return start_idx

                # If we can't find a proper function call, at least keep the function response
                return function_response_idx

        # If we're not at the boundary, return the original index
        return compress_before_index

    def _is_user_message(self, message) -> bool:
        """
        Check if a message is from user.

        Args:
            message: The message to check
        Returns:
            True if the message is from user
        """
        if Converter.maybe_easy_input_message(message):
            return True
        if Converter.maybe_input_message(message):
            return True
        return False

    def _is_assistant_message(self, message) -> bool:
        """
        Check if a message is from assistant.

        Args:
            message: The message to check

        Returns:
            True if the message is from assistant
        """
        # TODO: implement proper assistant message detection
        if Converter.maybe_function_tool_call(message):
            return True
        if Converter.maybe_file_search_call(message):
            return True
        if Converter.maybe_reasoning_message(message):
            return True
        if Converter.maybe_response_output_message(message):
            return True

        return False

    def _is_function_response(self, message) -> bool:
        """
        Check if a message is a function response.

        Args:
            message: The message to check

        Returns:
            True if the message is a function response
        """
        if Converter.maybe_function_tool_call_output(message):
            return True
        return False

    def _sync_api_message_to_file(
        self, context: "CodeAgentContext", real_message_list: List[dict]
    ) -> None:
        """
        Sync the real API messages to the file session for persistence.

        Args:
            context: The code agent context
            real_message_list: List of message dictionaries to persist
        """
        import json
        try:
            # Build the path to the api_messages.json file
            session_dir = Path(DirectoryUtils.get_global_sessions_dir(context.root_dir))
            api_messages_path = session_dir / context.session_id / "api_messages.json"

            # Ensure the parent directory exists (including session_id subdirectory)
            api_messages_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the messages to file
            with open(str(api_messages_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": context.session.session_id,
                        "api_messages": real_message_list,
                    },
                    f,
                    ensure_ascii=False,
                    indent=4,
                )

        except OSError as e:
            logger.error(f"Failed to sync API messages to file: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error syncing API messages: {e}")
            raise
