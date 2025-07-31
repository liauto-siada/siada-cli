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
)

# 自动注册所有formatter
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
    ]
    
    for formatter_class in formatters:
        ToolCallFormatterFactory.register_formatter(formatter_class)

# 在模块导入时自动注册
_register_all_formatters()

# 导出的公共接口
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
