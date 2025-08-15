from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.cmd_runner import run_cmd_impl
from siada.tools.coder.observation.observation import FunctionCallResult


RUN_CMD_DOCS = """Execute a shell command using the most appropriate method for the current environment.

    This function automatically selects between pexpect (for interactive terminals on Unix-like
    systems) and subprocess (for Windows or non-interactive environments) to execute shell
    commands. It provides real-time output streaming and proper error handling.

    Args:
        command (str): The shell command to execute as a string.
"""


class RunCmdResult(FunctionCallResult):
    """This data class represents the output of a command."""

    def __init__(self, command: str, output: str, code: int):
        self.command = command
        self.output = output
        self.code = code if code is not None else 1

    @property
    def content(self) -> str:
        """Return the command output as content."""
        return str((self.code, self.output))

    def format_for_display(self) -> str:
        if self.code == 0:
            return f"`{self.command}` executed successfully!"
        else:
            return f"`{self.command}` executed with error!"

    def __str__(self):
        return self.content


@function_tool
def run_cmd(context: RunContextWrapper[CodeAgentContext], command) -> FunctionCallResult:
    """Execute a shell command using the most appropriate method for the current environment.

    This function automatically selects between pexpect (for interactive terminals on Unix-like
    systems) and subprocess (for Windows or non-interactive environments) to execute shell
    commands. It provides real-time output streaming and proper error handling.

    Args:
        command (str): The shell command to execute as a string.
        verbose (bool, optional): If True, prints detailed execution information including
            the execution method used, shell information, and command details. Defaults to False.
        error_print (callable, optional): Custom error printing function. If provided, errors
            will be output using this function instead of the default print(). Should accept
            a single string argument. Defaults to None.
    """
    cwd = context.context.root_dir
    code, output = run_cmd_impl(command=command, cwd=cwd)
    return RunCmdResult(command=command, output=output, code=code)
