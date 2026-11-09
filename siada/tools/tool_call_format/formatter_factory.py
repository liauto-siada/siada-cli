from typing import Dict, Optional, Type

from siada.tools.tool_call_format.formatters import DefaultFormatter
from .tool_call_formatter import ToolCallFormatter


class ToolCallFormatterFactory:
    """
    Create tool call formatter instances by function name.
    """

    _formatters: Dict[str, Type[ToolCallFormatter]] = {}
    _instances: Dict[str, ToolCallFormatter] = {}

    @classmethod
    def register_formatter(cls, formatter_class: Type[ToolCallFormatter]) -> None:
        """
        Register a formatter class.
        
        Args:
            formatter_class: Formatter class.
        """
        instance = formatter_class()
        cls._formatters[instance.supported_function] = formatter_class
            
    @classmethod
    def get_formatter(cls, function_name: str) -> Optional[ToolCallFormatter]:
        """
        Get the formatter for a function name.
        
        Args:
            function_name: Function name.
            
        Returns:
            The formatter instance, or None if unavailable.
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
        Create a new formatter instance.
        
        Args:
            function_name: Function name.
            
        Returns:
            A new formatter instance, or None if unavailable.
        """
        if function_name not in cls._formatters:
            return None
            
        formatter_class = cls._formatters[function_name]
        return formatter_class()

    @classmethod
    def list_supported_functions(cls) -> list[str]:
        """
        List supported function names.
        
        Returns:
            Supported function names.
        """
        return list(cls._formatters.keys())

    @classmethod
    def clear_registry(cls) -> None:
        """
        Clear the formatter registry, primarily for tests.
        """
        cls._formatters.clear()
        cls._instances.clear() 