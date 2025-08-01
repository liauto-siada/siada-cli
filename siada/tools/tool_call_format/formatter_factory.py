from typing import Dict, Optional, Type

from siada.tools.tool_call_format.formatters import DefaultFormatter
from .tool_call_formatter import ToolCallFormatter


class ToolCallFormatterFactory:
    """
    Tool call formatter 工厂类
    根据函数名创建相应的formatter实例
    """

    _formatters: Dict[str, Type[ToolCallFormatter]] = {}
    _instances: Dict[str, ToolCallFormatter] = {}

    @classmethod
    def register_formatter(cls, formatter_class: Type[ToolCallFormatter]) -> None:
        """
        注册一个formatter类
        
        Args:
            formatter_class: Formatter类
        """
        instance = formatter_class()
        cls._formatters[instance.supported_function] = formatter_class
            
    @classmethod
    def get_formatter(cls, function_name: str) -> Optional[ToolCallFormatter]:
        """
        根据函数名获取相应的formatter实例
        
        Args:
            function_name: 函数名称
            
        Returns:
            对应的formatter实例，如果不存在则返回None
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
        创建formatter实例（每次都创建新实例）
        
        Args:
            function_name: 函数名称
            
        Returns:
            新的formatter实例，如果不存在则返回None
        """
        if function_name not in cls._formatters:
            return None
            
        formatter_class = cls._formatters[function_name]
        return formatter_class()

    @classmethod
    def list_supported_functions(cls) -> list[str]:
        """
        列出所有支持的函数名
        
        Returns:
            支持的函数名列表
        """
        return list(cls._formatters.keys())

    @classmethod
    def clear_registry(cls) -> None:
        """
        清空注册的formatter（主要用于测试）
        """
        cls._formatters.clear()
        cls._instances.clear() 