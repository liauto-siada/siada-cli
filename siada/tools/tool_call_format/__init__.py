"""
Tool Call Formatter module.

Provides tool call argument formatting, including:
- ToolCallFormatter abstract base class interface
- ToolCallFormatterFactory factory class
- Various concrete formatter implementations
- ParameterInterceptor argument interception decorator
"""

from .tool_call_formatter import ToolCallFormatter
from .formatter_factory import ToolCallFormatterFactory
from .formatters import (
    DefaultFormatter,
    ListCodeDefinitionNamesFormatter,
    SearchFormatter,
    CommandFormatter,
    PowerShellCommandFormatter,
    FixAttemptCompletionFormatter,
    ReproduceCompletionFormatter,
    FileEditFormatter,
    ReadFileFormatter,
    AskFollowupQuestionFormatter,
    BrowserOperateFormatter,
    RunSubtaskFormatter,
    SmartSearchMemoryFormatter,
    SearchMemoryFormatter,
    MemoryWriteFormatter,
    FactStoreFormatter,
    FactFeedbackFormatter,
    WebSearchFormatter,
    WebFetchFormatter,
    LarkNotificationFormatter,
    LarkDailySummaryFormatter,
    TodoWriteFormatter,
)


# Auto-register all formatters
def _register_all_formatters():
    """Automatically register all available formatters."""
    formatters = [
        DefaultFormatter,
        SearchFormatter,
        CommandFormatter,
        PowerShellCommandFormatter,
        FixAttemptCompletionFormatter,
        ReproduceCompletionFormatter,
        FileEditFormatter,
        ReadFileFormatter,
        AskFollowupQuestionFormatter,
        ListCodeDefinitionNamesFormatter,
        BrowserOperateFormatter,
        RunSubtaskFormatter,
        SmartSearchMemoryFormatter,
        SearchMemoryFormatter,
        MemoryWriteFormatter,
        FactStoreFormatter,
        FactFeedbackFormatter,
        WebSearchFormatter,
        WebFetchFormatter,
        LarkNotificationFormatter,
        LarkDailySummaryFormatter,
        TodoWriteFormatter,
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
    'ReadFileFormatter',
    'SearchFormatter',
    'CommandFormatter',
    'PowerShellCommandFormatter',
    'ParameterInterceptor',
    'parameter_interceptor',
    'simple_interceptor',
]
