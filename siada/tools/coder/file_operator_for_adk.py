from google.adk.tools import ToolContext
from typing import Optional
import os

from siada.tools.coder.file_operator import _edit_file
from siada.tools.coder.tool_docs import EDIT_DOCS


class _CodeAgentContextMock:
    """Mock of CodeAgentContext for ADK compatibility."""
    def __init__(self, root_dir: str, siadaignore_controller, model_run_config):
        self.root_dir = root_dir
        self.siadaignore_controller = siadaignore_controller
        self.model_run_config = model_run_config


class _RunContextWrapperMock:
    """Mock of RunContextWrapper for ADK compatibility."""
    def __init__(self, context):
        self.context = context


async def edit_file(
        command: str,
        path: str,
        tool_context: ToolContext,
        file_text: Optional[str] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        insert_line: Optional[int] = None,
        view_range: Optional[list[int]] = None
) -> str:
    """Edit file using ADK framework.

    Args:
        command: The edit command to execute
        path: File path to edit
        tool_context: The tool context for state management
        file_text: Optional file text content
        old_str: Optional string to replace
        new_str: Optional replacement string
        insert_line: Optional line number for insertion
        view_range: Optional view range

    Returns:
        str: The result of the edit operation
    """
    # Extract context from tool_context.state
    root_dir = tool_context.state.get('root_dir', os.getcwd())
    siadaignore_controller = tool_context.state.get('siadaignore_controller')
    model_run_config = tool_context.state.get('model_run_config')

    # Create mock objects that match agents framework structure
    context_mock = _CodeAgentContextMock(
        root_dir=root_dir,
        siadaignore_controller=siadaignore_controller,
        model_run_config=model_run_config
    )
    
    run_context_mock = _RunContextWrapperMock(context=context_mock)

    # Call the core function with the mock context
    func_result = _edit_file(
        context=run_context_mock,
        command=command,
        path=path,
        file_text=file_text,
        old_str=old_str,
        new_str=new_str,
        insert_line=insert_line,
        view_range=view_range
    )

    return func_result.content

edit_file.__doc__ = EDIT_DOCS