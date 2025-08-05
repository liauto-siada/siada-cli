from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ToolCallFormatter(ABC):
    """
    Tool call formatter 接口
    用于格式化不同函数的输入参数
    """

    @abstractmethod
    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str, bool]:
        """
        格式化函数输入参数
        
        Args:
            call_id: tool_call id
            function_name: 函数名称
            arguments: 原始参数字符串
            
        Returns:
            一个包含样式、内容和完整性标志的元组 (style, content, is_complete)
        """
        pass
    
    def supports_streaming(self) -> bool:
        """
        是否支持流式渲染
        
        Returns:
            True if this formatter supports streaming rendering, False otherwise
        """
        return False

    @property
    @abstractmethod
    def supported_function(self) -> str:
        """
        返回支持的函数名
        
        Returns:
            支持的函数名
        """
        pass 


    def get_style(self) -> str:
        """
        返回样式
        
        Returns:
            样式
        """
        return "text"