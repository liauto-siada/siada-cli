"""Runtime bridge from ACP sessions to Siada execution sessions."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from acp.helpers import (
    start_tool_call,
    text_block,
    tool_content,
    update_agent_message_text,
    update_agent_thought_text,
    update_tool_call,
)

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.logging import logger
from siada.io.io import InputOutput
from siada.models.model_base_config import get_model_settings
from siada.models.model_run_config import ModelRunConfig
from siada.services.siada_runner import SiadaRunner
from siada.session import RunningSessionManager
from siada.session.session_models import RunningSession


@dataclass(frozen=True)
class AcpRuntimeSession:
    workspace: str
    session: RunningSession


# Commands excluded from the ACP `/`-menu because they need an interactive
# TTY, a UI surface ACP doesn't have yet, or (for "model"/"models") because
# model switching already has a dedicated ACP config_options flow (see
# SiadaAcpAgent._build_config_options) and shouldn't be exposed twice.
# Mirrors the rationale of LarkSlashCommandHandler._IM_BLOCKED_COMMANDS for
# another headless, non-TTY caller.
_BLOCKED_SLASH_COMMANDS = {
    "agent", "compare", "configure", "edit", "editor", "exit", "goal",
    "init", "issue-fix", "lark-auth", "logout", "map", "map-refresh",
    "migrate-detect", "migrate-import", "model", "models",
    "multiline-mode", "quit", "restore", "resume", "run", "shell",
    "task-list", "undo",
}


def is_slash_command(text: str) -> bool:
    """Match the terminal's slash-command heuristic (leading `/`, valid
    command-name characters, not an existing filesystem path), minus the
    `!shell` shortcut, which only makes sense in an interactive TTY.
    """
    text = text.strip()
    if not text.startswith("/") or text.startswith("//"):
        return False
    from siada.support.slash_commands import _looks_like_filepath

    return not _looks_like_filepath(text)


class SiadaTurnRunner:
    """Own a Siada runtime session for each ACP session id."""

    def __init__(self, agent_name: str = "coder") -> None:
        self._agent_name = agent_name
        self._sessions: dict[str, AcpRuntimeSession] = {}
        self._slash_commands: dict[str, Any] = {}

    def create_session(self, session_id: str, cwd: str) -> None:
        workspace = str(Path(cwd).resolve())
        if not Path(workspace).is_dir():
            raise ValueError(f"ACP cwd is not a directory: {cwd}")
        acp_io = InputOutput(pretty=False, fancy_input=False, output=io.StringIO())
        # The ACP server builds sessions directly (bypassing siadahub), so it
        # must run the same model setup as the TUI: load conf.yaml, then let
        # get_config() resolve provider/model and inject the user's models
        # (models.json / models_dev fallback) into the global model settings.
        # Otherwise list_available_models() and the session model fall back to
        # the built-in defaults shipped in agent_config.yaml.
        try:
            from siada.config.config_loader import load_conf
            from siada.entrypoint.helpers.model_setup import get_config

            conf = load_conf()
            acp_args = SimpleNamespace(
                model=None,
                provider=None,
                verbose=False,
                thinking=None,
                reasoning_effort=None,
                parallel_tool_calls=None,
            )
            llm_config = get_config(acp_args, acp_io, conf)
        except Exception as e:
            logger.warning(f"[acp] get_config failed, falling back to defaults: {e}")
            llm_config = ModelRunConfig.get_default_config()
        runtime_config = RunningConfig(
            llm_config=llm_config,
            io=acp_io,
            workspace=workspace,
            agent_name=self._agent_name,
            console_output=False,
            interactive=False,
            acp_mode=False,
        )
        self._sessions[session_id] = AcpRuntimeSession(
            workspace=workspace,
            session=RunningSessionManager.create_session(runtime_config, session_id=session_id),
        )

    def list_available_models(self) -> list[str]:
        return [model.model_name for model in get_model_settings()]

    def get_model(self, session_id: str) -> str:
        return self._sessions[session_id].session.siada_config.llm_config.model_name

    def set_model(self, session_id: str, model_name: str) -> None:
        llm_config = self._sessions[session_id].session.siada_config.llm_config
        new_config = ModelRunConfig(model_name)
        new_config.provider = llm_config.provider
        self._sessions[session_id].session.siada_config.llm_config = new_config

    def _get_slash_commands(self, session_id: str):
        """Lazily create the per-session SlashCommands instance, bound to
        this session's own IO (so print_info/print_error capture below only
        ever intercepts this session's output).
        """
        if session_id not in self._slash_commands:
            from siada.support.slash_commands import SlashCommands

            io = self._sessions[session_id].session.siada_config.io
            self._slash_commands[session_id] = SlashCommands(io=io)
        return self._slash_commands[session_id]

    def list_available_commands(self, session_id: str) -> list[tuple[str, str]]:
        """List (name, description) pairs safe to advertise to an ACP client,
        reusing SlashCommands.get_commands() and filtering out entries that
        don't make sense for a headless caller (see _BLOCKED_SLASH_COMMANDS).
        """
        session = self._sessions[session_id].session
        slash_cmds = self._get_slash_commands(session_id)
        names = sorted(
            {name.lstrip("/") for name in slash_cmds.get_commands(session)}
            - _BLOCKED_SLASH_COMMANDS
        )
        commands = []
        for name in names:
            method = getattr(slash_cmds, f"cmd_{name.replace('-', '_')}", None)
            doc = (method.__doc__ or "").strip() if method else ""
            description = doc.splitlines()[0] if doc else "No description available."
            commands.append((name, description))
        return commands

    async def run_slash_command(self, session_id: str, text: str):
        """Execute a slash command and yield ACP updates.

        Mirrors LarkSlashCommandHandler.handle(): temporarily redirect
        print_info/print_error into a buffer, run the command through the
        same SlashCommands.run() dispatcher used by the terminal and IM
        bridge, then surface the captured output as one agent message. A
        SwitchEvent carrying `ai_analysis_prompt` (e.g. from /goal, /btw's
        cousins) is hand off to a normal agent turn via __call__ so it still
        streams like any other prompt.
        """
        from siada.support.slash_commands import SwitchEvent

        runtime_session = self._sessions[session_id]
        session = runtime_session.session
        slash_cmds = self._get_slash_commands(session_id)
        session_io = session.siada_config.io

        output_lines: list[str] = []
        original_print_info = session_io.print_info
        original_print_error = session_io.print_error

        def _capture_info(text, *args, **kwargs):
            output_lines.append(text)

        def _capture_error(text, *args, **kwargs):
            output_lines.append(f"Error: {text}")

        session_io.print_info = _capture_info
        session_io.print_error = _capture_error
        try:
            result = slash_cmds.run(session, text)
        except Exception as exc:
            output_lines.append(f"Command failed: {exc}")
            result = None
        finally:
            session_io.print_info = original_print_info
            session_io.print_error = original_print_error

        if output_lines:
            yield update_agent_message_text("\n".join(output_lines))

        if isinstance(result, SwitchEvent):
            # cmd_model applies the switch to the session itself and only
            # returns SwitchEvent(model=...) for the terminal's outer loop —
            # which doesn't exist here, so surface the confirmation ourselves.
            if result.kwargs.get("model"):
                yield update_agent_message_text(f"Switched model to {result.kwargs['model']}")
            if result.kwargs.get("ai_analysis_prompt"):
                async for update in self(session_id, result.kwargs["ai_analysis_prompt"]):
                    yield update

    async def __call__(self, session_id: str, prompt: str):
        """Yield standard ACP session updates, mirroring the event types that
        ConversationTurn.output_stream_content() maps to the legacy ACP adapter
        (answer / thinking / tool_call), without invoking that legacy UI layer.
        """
        runtime_session = self._sessions[session_id]
        result = await SiadaRunner.run_agent(
            agent_name=self._agent_name,
            user_input=prompt,
            workspace=runtime_session.workspace,
            session=runtime_session.session,
            stream=True,
        )

        from agents import RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
        from openai.types.responses import (
            ResponseFunctionToolCall,
            ResponseOutputItemAddedEvent,
            ResponseOutputItemDoneEvent,
            ResponseReasoningSummaryTextDeltaEvent,
            ResponseTextDeltaEvent,
        )

        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):
                data = event.data
                if isinstance(data, ResponseTextDeltaEvent) and data.delta:
                    yield update_agent_message_text(data.delta)
                elif isinstance(data, ResponseReasoningSummaryTextDeltaEvent) and data.delta:
                    yield update_agent_thought_text(data.delta)
                elif isinstance(data, ResponseOutputItemAddedEvent) and isinstance(
                    data.item, ResponseFunctionToolCall
                ):
                    yield start_tool_call(
                        tool_call_id=data.item.call_id,
                        title=data.item.name,
                        status="pending",
                    )
                elif isinstance(data, ResponseOutputItemDoneEvent) and isinstance(
                    data.item, ResponseFunctionToolCall
                ):
                    yield update_tool_call(
                        tool_call_id=data.item.call_id,
                        status="in_progress",
                        raw_input=_parse_tool_arguments(data.item.arguments),
                    )
            elif isinstance(event, RunItemStreamEvent) and isinstance(event.item, ToolCallOutputItem):
                call_id = event.item.raw_item.get("call_id") if isinstance(event.item.raw_item, dict) else None
                if call_id:
                    output_text = _stringify_tool_output(event.item.output)
                    yield update_tool_call(
                        tool_call_id=call_id,
                        status="completed",
                        raw_output=event.item.output,
                        content=[tool_content(text_block(output_text))],
                    )


def _parse_tool_arguments(arguments: str) -> Any:
    """Best-effort JSON decode of a tool call's raw arguments string."""
    if not arguments:
        return None
    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return arguments


def _stringify_tool_output(output: Any) -> str:
    """Render a tool's raw output as text for the ACP tool_call content block."""
    from agents import ToolOutputText

    if isinstance(output, str):
        return output
    if isinstance(output, ToolOutputText):
        return output.text
    if isinstance(output, list):
        return "\n".join(_stringify_tool_output(item) for item in output)
    return str(output)
