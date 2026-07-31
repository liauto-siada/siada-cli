import os
import platform
import re
import uuid
from typing import Optional

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger
from siada.tools.coder.cmd_runner import run_powershell_impl
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.tools.coder.run_cmd import (
    DEFAULT_TIMEOUT_S,
    MAX_TIMEOUT_S,
    _truncate_tool_output_if_needed,
)
from siada.tools.resolve_cwd import resolve_cwd


RUN_POWERSHELL_DOCS = f"""Execute a PowerShell command on Windows.

This tool runs PowerShell commands using pwsh (7+) when available, falling back
to powershell.exe (5.1). It is ONLY registered on Windows — on macOS/Linux this
tool is not exposed. Output encoding is forced to UTF-8 to avoid PS 5.1's UTF-16
BOM default. Exit codes are captured via $LASTEXITCODE with $? fallback to work
around PS 5.1's stderr-sets-$?-false bug.

WHEN TO USE PowerShell instead of run_cmd:
- Windows registry: Get-ItemProperty 'HKLM:\\SOFTWARE\\...'
- Windows services: Get-Service, Restart-Service
- Process objects with pipeline: Get-Process | Where-Object {{ $_.CPU -gt 10 }}
- Environment variables: $env:USERNAME (instead of cmd %USERNAME%)
- PS-native file ops: Get-ChildItem, Set-Content -Encoding UTF8
- Anything using cmdlets (Verb-Noun) or PS-specific syntax

SYNTAX ESSENTIALS:
- Verb-Noun naming: Get-ChildItem, Set-Location, Test-Path, Invoke-RestMethod
- Variables: $name = "value"; reference $env:VAR for env vars
- Pipeline: cmd1 | cmd2 | cmd3
- Here-string literal:    @'...'@   (no interpolation)
- Here-string expandable: @"..."@   (interpolates $vars)
- Conditional run-next-if-success: A; if ($?) {{ B }}

POWERSHELL 5.1 vs 7+ DIFFERENCES (default to 5.1-compatible syntax — you cannot
know which version is installed):
- 5.1 DOES NOT support: && || ?: ?? ?.   →  use:  A; if ($?) {{ B }}
- 7+ supports the above operators natively
- Default to 5.1 syntax to maximize compatibility

DO NOT USE for:
- Interactive prompts (Read-Host, git rebase -i, etc.) — this is non-interactive
- Long-running services — use timeout to bound execution
- Commands that require a TTY

Args:
    command (str): The PowerShell command to execute as a string.
    cwd (str, optional): Working directory for command execution.
        Defaults to the current workspace directory.
    timeout (int, optional): Timeout in seconds (max {MAX_TIMEOUT_S}s).
        Defaults to {DEFAULT_TIMEOUT_S}s.
"""


class RunPowerShellResult(FunctionCallResult):
    """Output of a PowerShell command execution."""

    def __init__(self, command: str, output: str, code: int, cwd: str = None):
        self.command = command
        self.output = output
        self.code = code if code is not None else 1
        self.cwd = cwd or os.getcwd()
        self.call_id = str(uuid.uuid4())
        self._content_cache: Optional[str] = None

    @property
    def content(self) -> str:
        if self._content_cache is not None:
            return self._content_cache
        raw_content = str((self.code, self.output))
        self._content_cache = _truncate_tool_output_if_needed(
            content=raw_content,
            call_id=self.call_id,
            cwd=self.cwd,
        )
        return self._content_cache

    def format_for_display(self) -> str:
        if self.code == 0:
            return f"`{self.command}` (PowerShell) executed successfully! \n {self.content}"
        else:
            return f"`{self.command}` (PowerShell) executed with code: {self.code}!"

    def format_for_display_im(self) -> str:
        """IM-friendly display: clean output wrapped in powershell code block."""
        IM_OUTPUT_MAX_CHARS = 3000

        header = "✅ **success (PowerShell)**" if self.code == 0 else f"❌ **failed (PowerShell)** (exit code: {self.code})"

        output = self.output or ""
        output = output.replace("\r\n", "\n").replace("\r", "")
        output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
        output = re.sub(r"\x1b\][^\x07]*\x07", "", output)

        if not output.strip():
            return header

        if len(output) > IM_OUTPUT_MAX_CHARS:
            cut_pos = output.rfind("\n", 0, IM_OUTPUT_MAX_CHARS)
            output = output[:cut_pos] if cut_pos > 0 else output[:IM_OUTPUT_MAX_CHARS]
            output += "\n... (truncated)"

        ticks = "```"
        while ticks in output:
            ticks += "`"
        return f"{header}\n{ticks}powershell\n{output}\n{ticks}"

    def __str__(self):
        return self.content


def _run_powershell_impl_tool(
    context: RunContextWrapper[CodeAgentContext],
    command: str,
    cwd: str | None = None,
    timeout: int | None = None,
) -> FunctionCallResult:
    """Shared implementation for the run_powershell tool variants."""
    effective_cwd = resolve_cwd(context, cwd)
    effective_timeout = (
        min(int(timeout), MAX_TIMEOUT_S) if timeout and timeout > 0 else DEFAULT_TIMEOUT_S
    )
    code, output = run_powershell_impl(
        command=command,
        verbose=True,
        cwd=effective_cwd,
        timeout=effective_timeout,
    )
    return RunPowerShellResult(command=command, output=output, code=code, cwd=effective_cwd)


@function_tool(
    name_override="run_powershell",
    description_override=RUN_POWERSHELL_DOCS,
)
def run_powershell(
    context: RunContextWrapper[CodeAgentContext],
    command: str,
    cwd: str | None = None,
    timeout: int | None = None,
) -> FunctionCallResult:
    return _run_powershell_impl_tool(context, command, cwd, timeout)


def get_run_powershell_tool_if_available():
    """Return the run_powershell tool only on Windows; None elsewhere.

    Designed to be used as:
        pwsh = get_run_powershell_tool_if_available()
        if pwsh is not None:
            tools.append(pwsh)
    """
    if platform.system() != "Windows":
        return None
    logger.info("[run_powershell] Windows detected, registering run_powershell tool")
    return run_powershell
