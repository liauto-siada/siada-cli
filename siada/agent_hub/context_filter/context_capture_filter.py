from __future__ import annotations
from typing import List, TYPE_CHECKING
import copy
import time

from .base_filter import ContextFilter
from .message_history_capture_filter import MessageHistoryCaptureFilter
from .api_message_transfer_filter import ApiMessageTransferFilter
from .pending_user_input_filter import PendingUserInputInjector
from siada.foundation.logging import logger as logging


if TYPE_CHECKING:
    from agents.run import CallModelData, ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


# Global filter list - lazy loaded on first use
_CONTEXT_FILTERS: List[ContextFilter] | None = None


def get_context_filters() -> List[ContextFilter]:
    """
    Get the list of context filters, initializing them if needed (lazy loading).
    
    Returns:
        List of context filters to be applied
    """
    global _CONTEXT_FILTERS
    if _CONTEXT_FILTERS is None:
        # Initialize filters on first use
        # NOTE: the /goal reminder is no longer injected here. It is merged
        # into the new turn's raw input once, before the agent run even
        # starts (see SiadaRunner.run_agent -> merge_goal_reminder_into_input),
        # so it becomes part of the SDK's real ``input`` and gets persisted
        # to api_history.json by the SDK's own session bookkeeping — a
        # call_model_input_filter here could only ever affect a single LLM
        # call's copy of the input and was never persisted (see git history
        # of goal_reminder_filter.py for the old design).
        # NOTE: the todo reminder is likewise no longer run here as a
        # call_model_input_filter. This filter only ever sees a deep-copied
        # model_data.input (see below), so any injection here would need
        # the same pending_reminder_items staging trick to survive past
        # this one call. Instead it now lives entirely in
        # TodoReminderProcessor (AgentHooks.on_llm_start/on_llm_end), which
        # fires after this filter chain on the real input_items list that
        # is actually sent to the model — guaranteeing the reminder is both
        # part of the live call and durably persisted to the Session.
        _CONTEXT_FILTERS = [
            PendingUserInputInjector(),
            MessageHistoryCaptureFilter(),
            ApiMessageTransferFilter(),
        ]

    return _CONTEXT_FILTERS


async def context_capture_filter(data: CallModelData['CodeAgentContext']) -> ModelInputData:
    """
    Main filter function that executes a list of context filters.
    
    This function processes the call model data through a chain of filters,
    allowing for modular and extensible data processing before LLM calls.
    
    Args:
        data: The call model data containing model input, agent, and context
        
    Returns:
        The ModelInputData after all filters have been applied
    """
    _t_pipeline_start = time.perf_counter()

    # Deep copy the model_data to avoid modifying the original
    _t0 = time.perf_counter()
    model_data_copy = copy.deepcopy(data.model_data)
    _t_deepcopy = time.perf_counter() - _t0

    input_len = len(model_data_copy.input) if isinstance(model_data_copy.input, list) else 0

    # Get filters (lazy loaded on first use)
    filters = get_context_filters()
    per_filter_ms: list[tuple[str, float]] = []
    try:
        # Execute each filter in sequence asynchronously with separate parameters
        for filter_instance in filters:
            _t_filter0 = time.perf_counter()
            await filter_instance.filter(model_data_copy, data.agent, data.context)
            per_filter_ms.append((
                type(filter_instance).__name__,
                (time.perf_counter() - _t_filter0) * 1000,
            ))

        logging.info(
            "[PERF][context_capture_filter] input_items=%d | deepcopy=%.1fms "
            "%s total=%.1fms",
            input_len, _t_deepcopy * 1000,
            " ".join(f"{name}={ms:.1f}ms" for name, ms in per_filter_ms),
            (time.perf_counter() - _t_pipeline_start) * 1000,
        )
        return model_data_copy
    except Exception as e:
        logging.warning(f"context_capture_filter error : {e}")

    # Return the model input data unmodified on error
    return data.model_data
