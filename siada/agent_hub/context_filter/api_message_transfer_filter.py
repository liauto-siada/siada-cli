from __future__ import annotations
from pathlib import Path
from typing import List, TYPE_CHECKING, Any

from siada.models.model_run_config import ModelRunConfig
from siada.session.task_message_state import RealApiMessage
from siada.utils import DirectoryUtils
from .utils import compute_message_signature, calculate_tokens
from .compaction_strategy import CompactionError, get_compaction_strategy
from siada.foundation.logging import logger


if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.session.task_message_state import RealApiMessage


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

        try:
            # 1. build real message state with token counting
            real_api_messages, tokens_count, last_index, last_signature = (
                await self._build_real_message_state(context, model_data.instructions)
            )
            # 2. try compact the real api messages if too long
            try:
                compacted_messages = await self._try_compact_real_api_messages(
                    context=context,
                    real_api_messages=real_api_messages,
                    tokens_count=tokens_count,
                    model_config=context.model_run_config,
                )
            except CompactionError as ce:
                # Compaction failed — rollback to pre-compaction messages
                logger.warning(f"Compaction failed, using uncompacted messages: {ce}")
                compacted_messages = real_api_messages
            # Update the model input data
            model_data.input = compacted_messages
            # 3. sync the real messages to file session
            # only sync to save the compacted messages to file for debugging
            # update the real_messages (only real_api_history in memory, tracking via file)
            context.task_message_state.set_real_messages(
                RealApiMessage(
                    real_api_history=compacted_messages,
                    last_index=last_index,
                    last_signature=last_signature,
                )
            )
            # Persist to file after updating in-memory state
            self._sync_api_message_to_file(
                context, compacted_messages, tokens_count,
                last_index=last_index, last_signature=last_signature,
            )
        except Exception as e:
            logger.error(f"RealMessageTransferFilter error {e}")
            # # rollback the state to the original
            # model_data.input = origin_input
            # context.task_message_state.set_real_messages(RealApiMessage())

    async def _try_compact_real_api_messages(
        self,
        context: "CodeAgentContext",
        real_api_messages: List,
        tokens_count: int,
        model_config: ModelRunConfig,
    ) -> List:
        """
        Try to compact the real API messages if they exceed the token limit.

        Uses unified get_compaction_strategy() factory which returns:
        - TurnPruneSummaryCompaction for IM mode (multi-layer: turn limit + tool truncation + LLM summary)
        - SummarizeWithHeaderCompaction for CLI/TUI mode

        Args:
            context: The code agent context
            real_api_messages: List of messages to compact
            tokens_count: Current token count
            model_config: Model configuration

        Returns:
            Compacted list of messages
        """
        strategy = get_compaction_strategy(context)

        if not strategy.should_compact(tokens_count, model_config):
            return real_api_messages

        try:
            return await strategy.compact(
                context=context,
                real_api_messages=real_api_messages,
            )
        except Exception as e:
            raise CompactionError(f"Compaction failed: {e}") from e

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
            + calculate_tokens(context.model_run_config.model_name, system_instructions)
            + calculate_tokens(context.model_run_config.model_name, real_api_messages)
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
                total_tokens = calculate_tokens(
                    context.model_run_config.model_name, system_instructions
                ) + calculate_tokens(context.model_run_config.model_name, api_messages)
            else:
                # Add tokens for new messages only
                delta_tokens = calculate_tokens(context.model_run_config.model_name, delta)
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
        # Read last_index/last_signature: prefer persisted file, fall back to in-memory
        # for backward compatibility with old sessions that don't have file-based tracking
        last_index, last_signature = self._read_tracking_info_from_file(context)
        if last_index == -1 and last_signature == "":
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
                context.session.state.usage.total_tokens
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

    def _get_api_messages_path(self, context: "CodeAgentContext") -> Path:
        """Get the path to api_messages.json for the current session."""
        session_dir = Path(DirectoryUtils.get_global_sessions_dir(context.root_dir))
        return session_dir / context.session_id / "api_messages.json"

    def _read_tracking_info_from_file(
        self, context: "CodeAgentContext"
    ) -> tuple[int, str]:
        """
        Read last_index and last_signature from the persisted api_messages.json file.

        Returns:
            Tuple of (last_index, last_signature). Defaults to (-1, "") if file not found.
        """
        import json
        api_messages_path = self._get_api_messages_path(context)
        if not api_messages_path.exists():
            return -1, ""
        try:
            with open(str(api_messages_path), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("last_index", -1), data.get("last_signature", "")
        except Exception:
            return -1, ""

    def _sync_api_message_to_file(
        self,
        context: "CodeAgentContext",
        real_message_list: List[dict],
        tokens_count: int = 0,
        last_index: int = -1,
        last_signature: str = "",
    ) -> None:
        """
        Sync the real API messages to the file session for persistence.

        Args:
            context: The code agent context
            real_message_list: List of message dictionaries to persist
            tokens_count: Token count at the time of this save
            last_index: Last processed message index for incremental tracking
            last_signature: Last processed message signature for incremental tracking
        """
        import json
        try:
            api_messages_path = self._get_api_messages_path(context)
            api_messages_path.parent.mkdir(parents=True, exist_ok=True)

            with open(str(api_messages_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": context.session.session_id,
                        "tokens_count": tokens_count,
                        "last_index": last_index,
                        "last_signature": last_signature,
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
