import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.cmd_runner import run_cmd_impl
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.utils import DirectoryUtils
from siada.foundation.context import get_context_var
from siada.tools.resolve_cwd import resolve_cwd


DEFAULT_TIMEOUT_S = 60   # 1 minute
MAX_TIMEOUT_S = 600      # 10 minutes

RUN_CMD_DOCS = f"""Execute a shell command using the most appropriate method for the current environment.

    This function automatically selects between pexpect (for interactive terminals on Unix-like
    systems) and subprocess (for Windows or non-interactive environments) to execute shell
    commands. It provides real-time output streaming and proper error handling.

    Args:
        command (str): The shell command to execute as a string.
        cwd (str, optional): Working directory for command execution.
            If not provided, defaults to the current workspace directory.
        timeout (int, optional): Timeout in seconds (max {MAX_TIMEOUT_S}s / {MAX_TIMEOUT_S // 60} minutes).
            If not specified, commands will timeout after {DEFAULT_TIMEOUT_S}s ({DEFAULT_TIMEOUT_S // 60} minute).
"""


class RunCmdResult(FunctionCallResult):
    """This data class represents the output of a command."""

    def __init__(self, command: str, output: str, code: int, cwd: str = None):
        self.command = command
        self.output = output
        self.code = code if code is not None else 1
        self.cwd = cwd or os.getcwd()
        # Stable id for persistence across multiple .content property reads
        self.call_id = str(uuid.uuid4())
        self._content_cache: Optional[str] = None

    @property
    def content(self) -> str:
        """Return the command output as content with truncation if needed."""
        if self._content_cache is not None:
            return self._content_cache

        raw_content = str((self.code, self.output))

        # Apply tool output truncation strategy
        self._content_cache = _truncate_tool_output_if_needed(
            content=raw_content,
            call_id=self.call_id,
            cwd=self.cwd,
        )
        return self._content_cache

    def format_for_display(self) -> str:
        if self.code == 0:
            return f"`{self.command}` executed successfully! \n {self.content}"
        else:
            return f"`{self.command}` executed with code: {self.code}!"

    def format_for_display_im(self) -> str:
        """IM-friendly display: clean output wrapped in code block."""
        import re
        IM_OUTPUT_MAX_CHARS = 3000

        header = "✅ **success**" if self.code == 0 else f"❌ **failed** (exit code: {self.code})"

        output = self.output or ""
        # Normalize line endings and strip ANSI escape sequences
        output = output.replace("\r\n", "\n").replace("\r", "")
        output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
        output = re.sub(r"\x1b\][^\x07]*\x07", "", output)

        if not output.strip():
            return header

        # Truncate
        if len(output) > IM_OUTPUT_MAX_CHARS:
            cut_pos = output.rfind("\n", 0, IM_OUTPUT_MAX_CHARS)
            output = output[:cut_pos] if cut_pos > 0 else output[:IM_OUTPUT_MAX_CHARS]
            output += "\n... (truncated)"

        # Wrap in code block with enough backticks
        ticks = "```"
        while ticks in output:
            ticks += "`"
        return f"{header}\n{ticks}\n{output}\n{ticks}"

    def __str__(self):
        return self.content


# ---- Tool output truncation --------------------------------

# Default threshold: 200KB ( 4 chars~= 1 token in english)
DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD = 200_000
# Default lines to keep after truncation
DEFAULT_TRUNCATE_TOOL_OUTPUT_LINES = 1000
# Force wrap width for ultra-long single line outputs
WRAP_WIDTH = 120


def _safe_output_file_name(call_id: str) -> str:
    """Create a safe file name from call_id."""
    base = os.path.basename(call_id)
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)
    if not base:
        base = "tool_call"
    return f"{base}.output"


def _get_dynamic_truncation_threshold(static_threshold: int) -> int:
    """Compute a dynamic threshold if context info is available.

    Mirrors gemini-cli logic:
      threshold = min(4 * (tokenLimit - usedTokens), staticThreshold)

    Here we try to read from global contextvars set by the interaction loop.
    """
    try:
        # set by conversation_turn._print_context_usage (best-effort)
        used_tokens = int(get_context_var("last_prompt_token_count", 0) or 0)
        token_limit = int(get_context_var("model_context_window", 0) or 0)
    except Exception:
        return static_threshold

    if token_limit <= 0:
        return static_threshold

    remaining = max(0, token_limit - used_tokens)
    dynamic = 4 * remaining
    return min(dynamic, static_threshold)


def _wrap_long_lines_if_needed(lines: List[str], truncate_lines: int) -> List[str]:
    """If the output has too few lines to truncate by lines, force-wrap long lines."""
    has_long_line = any(len(line) > WRAP_WIDTH for line in lines)
    if not has_long_line:
        return lines
    
    wrapped: List[str] = []
    for line in lines:
        if len(line) > WRAP_WIDTH:
            for i in range(0, len(line), WRAP_WIDTH):
                wrapped.append(line[i : i + WRAP_WIDTH])
        else:
            wrapped.append(line)
    return wrapped


def _truncate_tool_output_if_needed(content: str, call_id: str, cwd: str) -> str:
    """Truncate oversized tool output while preserving head+tail and persisting full output."""
    # Allow env overrides for testing / tuning
    static_threshold = int(
        os.environ.get(
            "SIADA_TRUNCATE_TOOL_OUTPUT_THRESHOLD",
            DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD,
        )
    )
    truncate_lines = int(
        os.environ.get(
            "SIADA_TRUNCATE_TOOL_OUTPUT_LINES",
            DEFAULT_TRUNCATE_TOOL_OUTPUT_LINES,
        )
    )

    # layer 2 (dynamic threshold) - best effort
    threshold = _get_dynamic_truncation_threshold(static_threshold)

    if static_threshold <= 0 or truncate_lines <= 0:
        return content

    if len(content) <= threshold:
        return content

    # Step 2: split and optionally wrap long lines (when too few lines to truncate)
    lines = content.splitlines()
    lines = _wrap_long_lines_if_needed(lines, truncate_lines)

    # Step 3: keep head 20% + tail 80%
    head = max(1, truncate_lines // 5)  # 20%
    beginning = lines[:head]
    end = lines[-(truncate_lines - head) :] if len(lines) > head else []

    truncated_content = (
        "\n".join(beginning)
        + "\n... [CONTENT TRUNCATED] ...\n"
        + "\n".join(end)
    ).rstrip()

    # Step 4: persist full content
    project_temp_dir = DirectoryUtils.get_project_temp_dir(cwd)
    output_file = os.path.join(project_temp_dir, _safe_output_file_name(call_id))
    try:
        Path(project_temp_dir).mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(content, encoding="utf-8", errors="replace")
    except Exception:
        # If persistence fails, still return truncated content
        output_file = ""

    # Step 5: append reference to full output
    if output_file:
        truncated_content += f"\n\n[Full output saved to: {output_file}]"

    return truncated_content


def _run_cmd_impl_tool(context: RunContextWrapper[CodeAgentContext], command: str, cwd: str | None = None, timeout: int | None = None) -> FunctionCallResult:
    """Shared implementation for both TUI and IM run_cmd variants."""
    effective_cwd = resolve_cwd(context, cwd)
    effective_timeout = min(int(timeout), MAX_TIMEOUT_S) if timeout and timeout > 0 else DEFAULT_TIMEOUT_S
    code, output = run_cmd_impl(command=command, verbose=True, cwd=effective_cwd, timeout=effective_timeout)
    return RunCmdResult(command=command, output=output, code=code, cwd=effective_cwd)


@function_tool(
    name_override="run_cmd", description_override=RUN_CMD_DOCS
)
def run_cmd(context: RunContextWrapper[CodeAgentContext], command: str, cwd: str | None = None, timeout: int | None = None) -> FunctionCallResult:
    return _run_cmd_impl_tool(context, command, cwd, timeout)
