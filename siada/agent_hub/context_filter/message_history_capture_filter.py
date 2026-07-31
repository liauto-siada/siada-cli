from __future__ import annotations
import time
from typing import TYPE_CHECKING, Any

from siada.entrypoint import _configure_litellm
from siada.foundation.logging import logger

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
        _configure_litellm()

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
                import json as _json
                _t0 = time.perf_counter()
                filtered_items = copy.deepcopy(input_items)
                _t_deepcopy = time.perf_counter() - _t0
                for i in range(len(filtered_items) - 1, -1, -1):
                    item = filtered_items[i]
                    if not isinstance(item, dict) or item.get("type") != "function_call":
                        continue
                    if isinstance(item.get("arguments"), str):
                        try:
                            _json.loads(item["arguments"])
                        except (_json.JSONDecodeError, ValueError):
                            call_id = item.get("call_id")
                            filtered_items = [
                                x for j, x in enumerate(filtered_items)
                                if not (isinstance(x, dict) and j >= i and x.get("call_id") == call_id and x.get("type") in ("function_call", "function_call_output"))
                            ]
                    break
                _t0 = time.perf_counter()
                context.session.state.task_message_state.reset_message_history(
                    message_history=filtered_items
                )
                logger.debug(
                    "[PERF][MessageHistoryCaptureFilter] input_items=%d | "
                    "deepcopy=%.1fms reset_history=%.1fms",
                    len(input_items), _t_deepcopy * 1000,
                    (time.perf_counter() - _t0) * 1000,
                )
