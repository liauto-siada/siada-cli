from __future__ import annotations
from typing import List, TYPE_CHECKING
import copy

from .base_filter import ContextFilter
from .message_history_capture_filter import MessageHistoryCaptureFilter
from .api_message_transfer_filter import ApiMessageTransferFilter
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
        _CONTEXT_FILTERS = [
            MessageHistoryCaptureFilter(),
            ApiMessageTransferFilter()
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
    # Deep copy the model_data to avoid modifying the original
    model_data_copy = copy.deepcopy(data.model_data)
    
    # Get filters (lazy loaded on first use)
    filters = get_context_filters()
    try:
    
        # Execute each filter in sequence asynchronously with separate parameters
        for filter_instance in filters:
            await filter_instance.filter(model_data_copy, data.agent, data.context)
        return model_data_copy
    except Exception as e:
        logging.warning(f"context_capture_filter error : {e}")

    # Return the model input data unmodified on error
    return data.model_data
