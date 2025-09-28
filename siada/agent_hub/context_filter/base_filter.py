from __future__ import annotations
from typing import Protocol, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


class ContextFilter(Protocol):
    """
    Protocol for context filters that process model data.
    
    Filters modify the model_data in-place and don't return any value.
    """
    
    async def filter(self, model_data: ModelInputData, agent: Any, context: CodeAgentContext) -> None:
        """
        Process the model data.
        
        Args:
            model_data: The model input data to filter. Filters should modify
                        this data in-place as needed.
            agent: The agent instance
            context: The code agent context
        """
        ...
