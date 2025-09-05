from __future__ import annotations
from typing import List
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents import Agent, TResponseInputItem
    from agents.run import CallModelData, ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext

def _capture_message_history(context: 'CodeAgentContext', input_items: List['TResponseInputItem']) -> None:
    """
    Helper function to reset message history in the task message state.
    
    Args:
        context: The code agent context containing session and state
        input_items: The input items to set as the new message history
    """
    if context and hasattr(context, 'session') and context.session:
        if hasattr(context.session, 'state') and hasattr(context.session.state, 'task_message_state'):
            context.session.state.task_message_state.reset_message_history(
                message_history=input_items.copy()
            )


def context_capture_filter(data: CallModelData['CodeAgentContext']) -> ModelInputData:
    """
    Filter that captures the input list and stores it in the context's task message state.
    
    This filter is used to track the conversation history by resetting the message
    history before each LLM call with the current input items.
    
    Args:
        data: The call model data containing model input, agent, and context
        
    Returns:
        The unmodified ModelInputData (pass-through behavior)
    """
    # Reset the message history with the current input items
    _capture_message_history(data.context, data.model_data.input)
    
    # Return the unmodified model input data
    return data.model_data
