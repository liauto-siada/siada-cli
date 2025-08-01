from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ToolCallFormatter(ABC):
    """
    Tool call formatter 接口
    用于格式化不同函数的输入参数
    """

    @abstractmethod
    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        """
        格式化函数输入参数
        
        Args:
            call_id: tool_call id
            function_name: 函数名称
            arguments: 原始参数字符串
            
        Returns:
            一个包含样式和内容的元组 (style, content)
        """
        pass

    @property
    @abstractmethod
    def supported_function(self) -> str:
        """
        返回支持的函数名
        
        Returns:
            支持的函数名
        """
        pass 