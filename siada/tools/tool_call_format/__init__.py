"""
Tool Call Formatter 模块

提供工具调用参数格式化功能，包括：
- ToolCallFormatter 抽象基类接口
- ToolCallFormatterFactory 工厂类
- 各种具体的 formatter 实现
- ParameterInterceptor 参数拦截装饰器
"""

from .tool_call_formatter import ToolCallFormatter
from .formatter_factory import ToolCallFormatterFactory
from .formatters import (
    DefaultFormatter,
    ListCodeDefinitionNamesFormatter,
    SearchFormatter,
    CommandFormatter,
    FixAttemptCompletionFormatter,
    ReproduceCompletionFormatter,
    FileEditFormatter,
    AskFollowupQuestionFormatter,
    BrowserOperateFormatter,
    RunSubtaskFormatter,
    SmartSearchMemoryFormatter,
)

# Auto-register all formatters
def _register_all_formatters():
    """自动注册所有可用的formatter"""
    formatters = [
        DefaultFormatter,
        SearchFormatter,
        CommandFormatter,
        FixAttemptCompletionFormatter,
        ReproduceCompletionFormatter,
        FileEditFormatter,
        AskFollowupQuestionFormatter,
        ListCodeDefinitionNamesFormatter,
        BrowserOperateFormatter,
        RunSubtaskFormatter,
        SmartSearchMemoryFormatter,
    ]
    
    for formatter_class in formatters:
        ToolCallFormatterFactory.register_formatter(formatter_class)

# Auto-register at module import time
_register_all_formatters()

# Public exported interface
__all__ = [
    'ToolCallFormatter',
    'ToolCallFormatterFactory',
    'DefaultFormatter',
    'FileReadFormatter',
    'SearchFormatter',
    'CommandFormatter',
    'ParameterInterceptor',
    'parameter_interceptor',
    'simple_interceptor',
]
