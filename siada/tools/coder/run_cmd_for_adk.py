import os
from siada.tools.coder.run_cmd import RunCmdResult, RUN_CMD_DOCS
from siada.tools.coder.cmd_runner import run_cmd_impl


def run_command(
        command: str,
        tool_context
) -> str:
    """Execute a CLI command for ADK framework.

    Args:
        command: The command to execute
        tool_context: The tool context for state management

    Returns:
        str: The result of the command execution
    """
    # Extract root_dir from ADK context
    root_dir = tool_context.state.get('root_dir', os.getcwd())
    
    # Call the underlying implementation directly
    code, output = run_cmd_impl(command=command, verbose=True, cwd=root_dir)
    
    # Wrap the result
    result = RunCmdResult(command=command, output=output, code=code, cwd=root_dir)
    return result.content



run_command.__doc__ = RUN_CMD_DOCS
