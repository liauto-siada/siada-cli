from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ToolCallFormatter(ABC):
    """
    Tool call formatter interface
    Used to format input parameters for different functions
    """

    @abstractmethod
    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        """
        Format function input parameters
        
        Args:
            call_id: tool_call id
            function_name: function name
            arguments: raw parameter string
            
        Returns:
            A tuple containing content and completeness flag (content, is_complete)
        """
        pass
    
    def supports_streaming(self) -> bool:
        """
        Whether streaming rendering is supported
        
        Returns:
            True if this formatter supports streaming rendering, False otherwise
        """
        return False

    @property
    @abstractmethod
    def supported_function(self) -> str:
        """
        Return the supported function name
        
        Returns:
            The supported function name
        """
        pass 


    def get_style(self) -> str:
        """
        Return the style
        
        Returns:
            The style
        """
        return "text"