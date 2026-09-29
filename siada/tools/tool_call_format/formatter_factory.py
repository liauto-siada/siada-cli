from typing import Dict, Optional, Type

from siada.tools.tool_call_format.formatters import DefaultFormatter
from .tool_call_formatter import ToolCallFormatter


class ToolCallFormatterFactory:
    """
    Factory class for tool call formatters.
    Creates the corresponding formatter instance based on the function name.
    """

    _formatters: Dict[str, Type[ToolCallFormatter]] = {}
    _instances: Dict[str, ToolCallFormatter] = {}

    @classmethod
    def register_formatter(cls, formatter_class: Type[ToolCallFormatter]) -> None:
        """
        Register a formatter class.
        
        Args:
            formatter_class: The Formatter class.
        """
        instance = formatter_class()
        cls._formatters[instance.supported_function] = formatter_class
            
    @classmethod
    def get_formatter(cls, function_name: str) -> Optional[ToolCallFormatter]:
        """
        Get the formatter instance for the given function name.
        
        Args:
            function_name: The function name.
            
        Returns:
            The corresponding formatter instance, or None if it does not exist.
        """
        if function_name not in cls._formatters:
            return DefaultFormatter()
            
        if function_name not in cls._instances:
            formatter_class = cls._formatters[function_name]
            cls._instances[function_name] = formatter_class()
            
        return cls._instances[function_name]

    @classmethod
    def create_formatter(cls, function_name: str) -> Optional[ToolCallFormatter]:
        """
        Create a formatter instance (a new instance each time).
        
        Args:
            function_name: The function name.
            
        Returns:
            A new formatter instance, or None if it does not exist.
        """
        if function_name not in cls._formatters:
            return None
            
        formatter_class = cls._formatters[function_name]
        return formatter_class()

    @classmethod
    def list_supported_functions(cls) -> list[str]:
        """
        List all supported function names.
        
        Returns:
            The list of supported function names.
        """
        return list(cls._formatters.keys())

    @classmethod
    def clear_registry(cls) -> None:
        """
        Clear the registered formatters (mainly for testing).
        """
        cls._formatters.clear()
        cls._instances.clear() 