from __future__ import annotations
from typing import TYPE_CHECKING, Any

from siada.entrypoint import _configure_litellm_logging

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


class MessageHistoryCaptureFilter:
    """
    Filter that captures the input list and stores it in the context's task message state.

    This filter is used to track the conversation history by resetting the message
    history before each LLM call with the current input items.
    """

    def __init__(self):
        _configure_litellm_logging()

    async def filter(
        self, model_data: ModelInputData, agent: Any, context: CodeAgentContext
    ) -> None:
        """
        Capture and reset message history in the task message state.

        Args:
            model_data: The model input data to filter
            agent: The agent instance
            context: The code agent context
        """
        input_items = model_data.input

        if context and hasattr(context, "session") and context.session:
            if hasattr(context.session, "state") and hasattr(
                context.session.state, "task_message_state"
            ):
                import copy
                context.session.state.task_message_state.reset_message_history(
                    message_history=copy.deepcopy(input_items)
                )
