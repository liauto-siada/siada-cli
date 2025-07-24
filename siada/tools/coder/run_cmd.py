import os
import platform
import subprocess
import sys
from io import BytesIO

import pexpect
import psutil
from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext


@function_tool
def run_cmd(context: RunContextWrapper[CodeAgentContext], command, verbose=False, error_print=None):
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
    return do_run_cmd(command, verbose, cwd, error_print)





# These functions have been moved to cmd_runner.py to avoid circular imports
from siada.tools.coder.cmd_runner import do_run_cmd, run_cmd_subprocess, run_cmd_pexpect
