"""Runtime bridge from ACP sessions to Siada execution sessions."""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from acp.helpers import (
    start_tool_call,
    text_block,
    tool_content,
    update_agent_message_text,
    update_agent_thought_text,
    update_tool_call,
)

from siada.entrypoint.interaction.running_config import RunningConfig, build_running_config_from_conf
from siada.entrypoint.runtime.turn_event import (
    REASONING_DELTA,
    TEXT_DELTA,
    TOOL_CALL_DONE,
    TOOL_CALL_START,
    TOOL_OUTPUT,
)
from siada.entrypoint.runtime.turn_orchestrator import TurnOrchestrator
from siada.io.io import InputOutput
from siada.models.model_base_config import get_model_settings
from siada.models.model_run_config import ModelRunConfig
from siada.services.browser_skill.event_utils import sanitize_events, sanitize_text
from siada.services.browser_skill.llm_utils import call_fast_llm, parse_json_from_model
from siada.services.browser_skill.models import ExecutionRecord, VerificationResult
from siada.services.browser_skill.pipeline import BrowserLearningWorker
from siada.services.browser_skill.playbook import PlaybookStore
from siada.services.browser_skill.verification import parse_tool_result, verify_conditions
from siada.services.memory.holographic.marker import wrap_user_input
from siada.session import RunningSessionManager
from siada.session.session_models import RunningSession
from siada.tools.coder.apply_patch_presentation import render_apply_patch_display

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Browser-skill ACE bridge (see design_docs/browser-skill-graph-design.md)
# ---------------------------------------------------------------------------

# How long we wait for the user to answer the proactive skill-suggestion
# permission prompt. Reject / timeout / cancel are all no-ops.
_PERMISSION_TIMEOUT_SECONDS = 60

# Post-hoc acceptance criteria are restricted to this whitelist; values must
# be non-empty strings. Anything else is refused up front.
_ALLOWED_CONDITION_TYPES = frozenset({"url_equals", "text_present", "text_absent"})

# Auto-drafted acceptance contracts: when a browser turn carries no explicit
# _meta.browserTask contract, the fast LLM derives conditions from the task
# text BEFORE execution (it never sees the outcome), so the pre-declaration
# property of explicit contracts is preserved. Any failure — quota, timeout,
# malformed output — degrades to the no-contract behavior of today.
_AUTO_CONTRACT_TIMEOUT_SECONDS = 20

_AUTO_CONTRACT_PROMPT = """\
You draft acceptance conditions for a browser task. Derive 1-3 conditions \
that can be checked with mechanical rules AFTER the task executes.

Only three condition kinds are allowed:
- url_equals: the full URL the tab should display once the task is complete \
(must start with http:// or https://)
- text_present: a short distinctive string that should appear on the final page
- text_absent: text that should NOT appear on the final page

Rules:
- value must be a non-empty string; keep feature text short and distinctive, \
never a full sentence
- derive conditions only from the task's intent; never assume the execution \
outcome
- return an empty list when the task cannot be verified with these kinds
- output JSON only, no explanations

Output format: {{"conditions": [{{"kind": "...", "value": "..."}}]}}

Starting page: {url}
User task: {task}
"""

# Explicit browser-context marker a client may embed in a prompt so a turn is
# attributed to the current page even before trajectory events arrive. Two
# forms are accepted:
#     <browser-context url="https://example.com/a" tabId="42">user text</browser-context>
#     <browser-context>Current tab ... URL: https://example.com/a ...</browser-context> user text
# Only the named URL/domain is used (low-trust experience suggestions); a
# tabId, when present, must match this session's registered tab, and without a
# tabId the marker is only honored for sessions with a registered tab.
_BROWSER_CONTEXT_RE = re.compile(
    r"<browser-context\s*([^>]*)>(.*?)</browser-context>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class BrowserTask:
    """Explicit pre-execution acceptance contract for a browser turn.

    Set via ``set_browser_task`` (from the ACP client's ``_meta.browserTask``)
    before the turn runs; consumed exactly once by the first turn that
    performs browser operations.
    """

    goal: str = ""
    conditions: list[dict] = field(default_factory=list)
    consumed: bool = False


def _is_http_url_with_host(value: str) -> bool:
    """An absolute http(s) URL with a non-empty host (``https://`` alone is not)."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _normalize_browser_conditions(conditions: Any) -> list[dict] | None:
    """Validate + normalize acceptance conditions to ``[{"kind", "value"}]``.

    Returns ``None`` when the payload is malformed, ``[]`` when nothing was
    provided. The container must be a list of dicts; every item must carry the
    ``kind``/``value`` pair used by the verification module (url_equals /
    text_present / text_absent) with non-empty string values, and url_equals
    values must be absolute http(s) URLs with a host. Conditions are decided
    BEFORE execution, never derived from a post-hoc page state.
    """
    if not conditions:
        return []
    if not isinstance(conditions, list):
        return None
    normalized: list[dict] = []
    for item in conditions:
        if not isinstance(item, dict) or "kind" not in item or "value" not in item:
            return None
        kind = item.get("kind")
        value = item.get("value")
        if not isinstance(kind, str):
            return None
        kind = kind.strip()
        if kind not in _ALLOWED_CONDITION_TYPES:
            return None
        if not isinstance(value, str) or not value.strip():
            return None
        value = value.strip()
        if kind == "url_equals" and not _is_http_url_with_host(value):
            return None
        normalized.append({"kind": kind, "value": value})
    return normalized


async def _await_auto_contract(task: "asyncio.Task[BrowserTask | None]") -> BrowserTask | None:
    """Resolve the concurrent draft with a hard cap; None on any failure.

    Cancellation of the CURRENT (turn) task is deliberately re-raised: only
    draft-internal failures (timeout, LLM error, malformed output) degrade to
    None; a cancelled turn must keep propagating its cancellation.
    """
    try:
        return await asyncio.wait_for(task, timeout=_AUTO_CONTRACT_TIMEOUT_SECONDS)
    except Exception:
        task.cancel()  # no-op when already done; harmless otherwise
        return None


def _discard_auto_contract(task: "asyncio.Task[BrowserTask | None] | None") -> None:
    """Abandon a draft that is no longer needed (no-op when already done)."""
    if task is not None:
        task.cancel()


def _extract_browser_context(prompt: str) -> dict | None:
    """Parse an explicit ``<browser-context ...>`` marker from a prompt.

    Both the attribute form (``url=... tabId=...``) and the plain form
    (``URL: https://...`` inside the tag) are accepted. The user prompt always
    stays the ENTIRE original text — the marker is context metadata, never a
    replacement for the user's request.
    """
    match = _BROWSER_CONTEXT_RE.search(prompt or "")
    if match is None:
        return None
    attributes = dict(
        re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', match.group(1) or "")
    )
    url = attributes.get("url", "")
    tab_id = None
    tab_raw = attributes.get("tabId")
    if tab_raw is not None and isinstance(tab_raw, str) and tab_raw.isdigit():
        tab_id = int(tab_raw)
    if not url:
        inner = match.group(2)
        url_match = re.search(r"URL\s*[:：]\s*(https?://[^\s>\"']+)", inner, re.IGNORECASE)
        if url_match is not None:
            url = url_match.group(1).strip().rstrip(".,;")
    if not url:
        return None
    return {
        "url": url,
        "tab_id": tab_id,
        "prompt": prompt,
    }


def _is_browser_tool(tool_name: Any) -> bool:
    """Whether a model tool call targets the browser MCP server.

    chrome-acp's tools (browser_read / browser_execute / browser_replay /
    browser_navigate / ...) surface with the MCP server-name prefix applied,
    so matching on the ``browser_`` marker is robust to that prefix.
    """
    name = str(tool_name or "").lower()
    return "browser_" in name or name.startswith("browser-")


def _registered_domain(url: str) -> str:
    """Best-effort registrable domain; mirrors event_utils.registered_domain."""
    if not url:
        return ""
    from siada.services.browser_skill.event_utils import registered_domain

    return registered_domain(url)


class SiadaTurnRunner:
    """Own a Siada runtime session for each ACP session id."""

    def __init__(self, agent_name: str = "coder") -> None:
        self._agent_name = agent_name
        # Shared turn pipeline (run_agent + TurnEvent translation); this class
        # adds only the ACP surface concerns (session registry, MCP forwarding,
        # browser-skill bridge, SessionUpdate rendering).
        self._orchestrator = TurnOrchestrator()
        self._sessions: dict[str, AcpRuntimeSession] = {}
        self._slash_commands: dict[str, Any] = {}
        # Per-session MCP server configs forwarded from ACP `session/new`'s
        # `mcpServers` (e.g. chrome-acp's `browser` server). Connected lazily at
        # the start of each turn via `extra_mcp_servers` on run_agent.
        self._session_mcp_configs: dict[str, list[Any]] = {}

        # --- Browser-skill ACE bridge state (design doc §6/§8) ---
        # ACP client connected via on_connect -> set_connection; used to push
        # suggestions and ask request_permission before taking over a tab.
        self._conn: Any | None = None
        # tabId -> session_id; a tab belongs to exactly one live session.
        self._tab_to_session: dict[int, str] = {}
        # session_id -> BrowserSkillSessionState (matcher state per tab).
        self._browser_skill_states: dict[str, Any] = {}
        # Pre-execution acceptance contracts consumed by the next browser turn.
        self._browser_tasks: dict[str, BrowserTask] = {}
        # Sessions currently inside a normal __call__ turn (event routing and
        # ordinary prompts are mutually exclusive per session).
        self._active_turn_sessions: set[str] = set()
        # Sessions where the skill executor drives __call__ fallback turns:
        # context is still injected, but persistence is owned by the executor.
        self._browser_skill_executing: set[str] = set()
        # session_id -> in-flight skill execution task (cancellable).
        self._skill_tasks: dict[str, asyncio.Task] = {}
        # session_id -> the managed task currently awaiting a permission
        # answer (cancellable: cancel() must abort the whole suggest -> wait
        # -> execute lifecycle, not only the execution part).
        self._permission_tasks: dict[str, asyncio.Task] = {}
        # session_id -> tab binding generation; bumped on every register_tab
        # so a permission granted for a stale binding is never executed.
        self._tab_generations: dict[str, int] = {}
        # Managed trajectory-notification tasks (never awaited inside the
        # JSON-RPC reader loop).
        self._trajectory_tasks: set[asyncio.Task] = set()
        # One normal-turn lock per session: ordinary prompts of the same
        # session serialize on it (different sessions stay unaffected).
        self._turn_locks: dict[str, asyncio.Lock] = {}
        # One trajectory-processing lock per session so matcher state is never
        # fed concurrently by two managed notification tasks.
        self._trajectory_locks: dict[str, asyncio.Lock] = {}
        # Lazy BrowserLearningWorker; woken after records are enqueued.
        self._worker: Any | None = None
        # Per-session record buffer for the CURRENT turn: browser tool calls
        # collected from the run_agent stream plus sanitized trajectory
        # notifications that arrive while the turn is active (so activity-time
        # evidence is never dropped). Exposed via last_turn_events() for the
        # skill executor's own persistence.
        self._browser_turn_events: dict[str, list[dict]] = {}
        # Set once close() starts; blocks new skill tasks from being spawned
        # by a late permission grant during shutdown.
        self._closing = False

    def create_session(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: list[Any] | None = None,
    ) -> None:
        workspace = str(Path(cwd).resolve())
        if not Path(workspace).is_dir():
            raise ValueError(f"ACP cwd is not a directory: {cwd}")
        runtime_config = self._build_running_config(workspace)
        if mcp_servers:
            self._session_mcp_configs[session_id] = list(mcp_servers)
        self._sessions[session_id] = AcpRuntimeSession(
            workspace=workspace,
            session=RunningSessionManager.create_session(runtime_config, session_id=session_id),
        )

    def list_sessions(self, cwd: str | None = None) -> list[dict[str, Any]]:
        """List persisted (on-disk) sessions for the ACP ``session/list`` method.

        Reuses SessionManager's disk scan (the same data source as the
        ``/resume`` command's session browser), so sessions survive agent
        restarts — unlike the in-memory sessions tracked by SiadaAcpAgent.
        Returned dicts carry the fields of an ACP SessionInfo: session_id /
        cwd / title / updated_at.

        When a cwd filter is given, only that project's sessions directory is
        scanned (scope='current'): the cross-project scan (scope='all')
        json-loads the api_history.json of every session on the machine,
        which takes tens of seconds with thousands of sessions.
        """
        from siada.services.session_management import SessionManager

        manager = SessionManager(cwd or str(Path.cwd()))
        try:
            infos = manager.list_sessions(scope="current" if cwd else "all")
        except Exception:
            logger.exception("[acp] Failed to list persisted sessions")
            return []

        sessions: list[dict[str, Any]] = []
        for info in infos:
            project_root = info.project_root or ""
            if cwd and project_root and project_root != "Unknown" and (
                os.path.normpath(project_root) != os.path.normpath(cwd)
            ):
                continue
            sessions.append({
                "session_id": info.session_id,
                "cwd": project_root or (cwd or ""),
                "title": (info.first_user_message or "")[:80] or None,
                "updated_at": info.last_updated,
            })
        # Newest first, matching how clients render thread history.
        sessions.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return sessions

    def restore_session(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: list[Any] | None = None,
    ) -> None:
        """Restore a persisted Siada session into a live runtime session.

        Mirrors ``/resume`` (SlashCommands.cmd_resume): loads the session
        from disk and applies it to a freshly created RunningSession,
        reusing the original session_id and storage path. Idempotent — a
        session already restored in this process is reused as-is.

        Locates the session via the workspace's project-hash directory
        (SessionManager.resolve_session_path), the same O(1) lookup
        ``/resume`` relies on — never via find_session(scope='all'), whose
        full-machine scan takes tens of seconds with thousands of sessions.
        """
        if session_id in self._sessions:
            return
        workspace = str(Path(cwd).resolve())
        if not Path(workspace).is_dir():
            raise ValueError(f"ACP cwd is not a directory: {cwd}")

        from siada.services.session_management import SessionManager

        session_dir = SessionManager.resolve_session_path(workspace, session_id)
        if not session_dir.is_dir():
            raise LookupError(f"Session not found in workspace {workspace}: {session_id}")

        # Same cross-workspace guard as cmd_resume: refuse to restore a
        # session into a different workspace. The hash directory is derived
        # from cwd, so a mismatch can only come from stale metadata; treat
        # it as advisory when it's absent.
        session_data = SessionManager(workspace).load_session(session_id, session_path=session_dir)
        origin_root = session_data.metadata.get("project_root") or ""
        if origin_root and origin_root != "Unknown" and (
            os.path.normpath(origin_root) != os.path.normpath(workspace)
        ):
            raise ValueError(f"Session belongs to workspace: {origin_root}")

        # Backfill metadata.json for older session folders that only
        # persisted api_history.json: creating a FileSession for such a
        # folder stamps an empty "Untitled Session" metadata template over
        # it (FileSession._init_metadata), which then masks the title
        # extraction fallback in SessionManager's session listing. Writing
        # the real metadata extracted from history first keeps the
        # on-disk listing intact.
        if not (session_dir / "metadata.json").exists():
            try:
                manager = SessionManager(workspace)
                metadata = manager._extract_metadata_from_history(session_id, session_data.items)
                metadata["project_root"] = origin_root or None
                tmp_file = session_dir / "metadata.json.tmp"
                tmp_file.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                tmp_file.replace(session_dir / "metadata.json")
                logger.info("[acp] Backfilled metadata.json for session %s", session_id)
            except Exception:
                logger.debug("[acp] metadata backfill failed for %s", session_id, exc_info=True)

        runtime_config = self._build_running_config(workspace)
        from siada.support.session_restore import restore_into_fresh_session

        running_session = restore_into_fresh_session(
            session_data,
            target_workspace=workspace,
            siada_config=runtime_config,
            session_id=session_id,
        )
        if mcp_servers:
            self._session_mcp_configs[session_id] = list(mcp_servers)
        self._sessions[session_id] = AcpRuntimeSession(
            workspace=workspace,
            session=running_session,
        )
        logger.info("[acp] Restored session %s from disk (cwd=%s)", session_id, workspace)

    def load_history_messages(self, session_id: str) -> list[dict[str, str]]:
        """Display-ready user/assistant messages for replaying a session.

        Reuses format_native_items_for_display (the same formatter as
        ``/resume``'s ui/loadHistory push) over the restored session's
        native item history. Each dict has keys: role, content, and
        optionally subtype.
        """
        runtime_session = self._sessions[session_id]
        items = runtime_session.session.state.task_message_state.get_messages()
        if not items:
            return []
        from siada.support.message_classifier import format_native_items_for_display

        return format_native_items_for_display(items)

    def _build_running_config(self, workspace: str) -> RunningConfig:
        """Build the session's RunningConfig from ~/.siada-cli/conf.yaml.

        Mirrors siadahub._build_session: the model/provider/thinking settings
        come from conf.yaml via get_config_from_conf(), and the memory /
        compaction / notification / MCP sections are carried over — so the
        ACP server honors the same user configuration as the CLI instead of
        only the repo's agent_config.yaml defaults.
        """
        from siada.config.config_loader import load_conf
        from siada.entrypoint.helpers.model_setup import get_config_from_conf
        from siada.services.mcp.setup import setup_mcp_config

        session_io = InputOutput(pretty=False, fancy_input=False, output=io.StringIO())

        try:
            conf = load_conf()
        except Exception:
            logger.exception("[acp] Failed to load conf.yaml; falling back to defaults")
            conf = None

        llm_config = ModelRunConfig.get_default_config()
        if conf is not None:
            try:
                llm_config = get_config_from_conf(session_io, conf)
            except Exception:
                logger.exception("[acp] Failed to resolve model from conf.yaml; using defaults")

        runtime_config = build_running_config_from_conf(
            conf,
            llm_config=llm_config,
            io=session_io,
            workspace=workspace,
            agent_name=self._agent_name,
            console_output=False,
            interactive=False,
            acp_mode=False,
        )
        # Register global MCP servers from conf.yaml into the shared
        # singleton (idempotent; connections are deferred to the agent run).
        setup_mcp_config(runtime_config)
        return runtime_config

    async def _connect_session_mcp(self, session_id: str) -> list[Any]:
        """Build and connect the ACP-injected MCP servers for a session.

        Returns a list of connected ``MCPServer`` instances ready to be handed
        to ``run_agent(extra_mcp_servers=...)``. Failures are logged and the
        offending server is skipped so a broken server never blocks the turn.
        """
        configs = self._session_mcp_configs.get(session_id, [])
        if not configs:
            return []
        from siada.services.mcp.manager_service import MCPServerFactory

        servers: list[Any] = []
        for idx, config in enumerate(configs):
            # MCPServerConfig has no name field; derive a stable one from the
            # endpoint / command so MCPServer(tool-name prefixing) is readable.
            url = getattr(config, "url", None) or getattr(config, "http_url", None)
            command = getattr(config, "command", None)
            if url:
                name = f"acp-{url.split('://')[-1].split('/')[0].replace('.', '-')}"
            elif command:
                name = f"acp-{Path(command).stem}"
            else:
                name = f"acp-mcp-{idx}"
            try:
                server = MCPServerFactory.create_server(name, config)
                if server is None:
                    continue
                # The mcp SDK's streamable-http client can deadlock on its
                # anyio cancel-scope teardown when the transport fails (the
                # exception is swallowed and the await never returns), which
                # silently hangs the whole turn. A hard timeout keeps the
                # contract above: a broken server never blocks the turn.
                await asyncio.wait_for(server.connect(), timeout=30)
                servers.append(server)
                logger.info("[acp] Connected MCP server %r (%s)", name, url or command)
            except Exception:
                logger.exception("[acp] Failed to connect MCP server %r", name)
        return servers

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
                prompt = result.kwargs["ai_analysis_prompt"]
                if result.kwargs.get("goal_command"):
                    # Shared with Controller._build_pending_input_for_ai_analysis
                    # via turn_input.format_ai_analysis_followup: /goal's kickoff
                    # turn must be persisted as the full "/goal <objective>" text
                    # (cmd_goal hands us the stripped objective), or history loses
                    # the fact this was a /goal invocation. __call__ wraps it in
                    # <user_input>...</user_input> like any other literal user text,
                    # so the persisted shape matches the TUI's exactly. No
                    # list-shape recursion guard is needed here: __call__ goes
                    # straight to run_agent and never re-parses slash commands.
                    from siada.entrypoint.interaction.turn_input import format_ai_analysis_followup

                    prompt = format_ai_analysis_followup(prompt, goal_command=True)
                async for update in self(session_id, prompt):
                    yield update

    async def __call__(self, session_id: str, prompt: str):
        """Yield standard ACP session updates, mirroring the event types that
        ConversationTurn.output_stream_content() maps to the legacy ACP adapter
        (answer / thinking / tool_call), without invoking that legacy UI layer.

        Browser-skill ACE wiring: when the session has browser state (a live
        trajectory domain or an explicit ``<browser-context>`` URL), active
        playbook entries for that domain are appended OUTSIDE the user's
        ``<user_input>`` label as low-trust experience suggestions, actual
        browser tool calls/outputs are captured as trajectory evidence, and a
        verified ExecutionRecord is enqueued for background learning. Non-
        browser turns keep the plain ``wrap_user_input`` semantics untouched.

        Concurrency contract: ordinary prompts of one session serialize on a
        per-session turn lock; while a browser skill owns the session only the
        skill's own fallback task may enter (any other prompt raises a busy
        RuntimeError instead of silently racing the executor).
        """
        current = asyncio.current_task()
        if session_id in self._browser_skill_executing and self._skill_tasks.get(session_id) is not current:
            raise RuntimeError(
                f"session {session_id} is busy executing a browser skill; concurrent prompts are refused"
            )
        if session_id in self._permission_tasks:
            raise RuntimeError(
                f"session {session_id} has a pending browser-skill permission request"
            )
        async with self._turn_lock(session_id):
            self._active_turn_sessions.add(session_id)
            try:
                async for update in self._stream_turn(session_id, prompt):
                    yield update
            finally:
                self._active_turn_sessions.discard(session_id)

    # ------------------------------------------------------------------
    # Browser-skill ACE bridge — entry points (called by SiadaAcpAgent)
    # ------------------------------------------------------------------

    def set_connection(self, conn: Any) -> None:
        """Bind the ACP client used for suggestions / permission prompts."""
        self._conn = conn

    def register_tab(self, session_id: str, tab_id: Any) -> None:
        """Bind a tabId to a session for trajectory routing.

        tab_id must be a real ``int >= 0`` — booleans, strings and ``None``
        are refused instead of being coerced, so a client sending ``"42"`` or
        ``False`` can never silently steal a tab. A tab belongs to exactly one
        live session; rebinding it unbinds the previous owner (matcher state
        reset, pending permission/skill task cancelled, pending acceptance
        contract cleared). When the SAME session moves from tab A to tab B the
        A mapping is dropped and the matcher window/domain/reminded state is
        reset so old-tab events can never drive suggestions on the new tab.
        """
        if isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id < 0:
            raise ValueError(f"tabId must be a non-negative int, got {tab_id!r}")
        state = self._browser_skill_states.get(session_id)
        previous_tab = state.tab_id if state is not None else None
        self._tab_generations[session_id] = self._tab_generations.get(session_id, 0) + 1

        if previous_tab is not None and previous_tab != tab_id:
            # Same session switched tabs: drop the old mapping and reset the
            # matcher state so the previous tab's domain/window never bleeds
            # into the new binding (the same state object is reused, so any
            # external reference observes the reset). An in-flight task
            # operating on the old tab is cancelled — it must not keep acting
            # on either tab.
            self._tab_to_session.pop(previous_tab, None)
            self._cancel_session_browser(session_id)
        previous_session = self._tab_to_session.get(tab_id)
        if previous_session is not None and previous_session != session_id:
            # Another session owned this tab: unbind it and cancel its
            # pending permission / skill task (stale takeover must not fire).
            self._tab_to_session.pop(tab_id, None)
            old_state = self._browser_skill_states.get(previous_session)
            if old_state is not None:
                old_state.tab_id = None
                old_state._reset_window("")
                old_state._reminded.clear()
            self._cancel_session_browser(previous_session)
            logger.info(
                "[browser-skill] tab %s rebound from session %s to %s",
                tab_id, previous_session, session_id,
            )

        self._tab_to_session[tab_id] = session_id
        if state is None:
            from siada.services.browser_skill.matcher import BrowserSkillSessionState

            state = BrowserSkillSessionState(session_id=session_id, tab_id=tab_id)
            self._browser_skill_states[session_id] = state
        else:
            state.tab_id = tab_id
            state._reset_window("")
            state._reminded.clear()
        # Rebinding invalidates any pre-execution contract written for the old
        # tab — it can never be consumed against a different page.
        self._browser_tasks.pop(session_id, None)
        # Registering a browser session is a wake signal for the lazy learning
        # worker (recovering pending/expired records from a previous process);
        # it only wakes inside a running event loop.
        self.wake_browser_learning()

    def set_browser_task(self, session_id: str, goal: str, conditions: Any) -> None:
        """Pre-execution explicit acceptance contract for the next browser turn.

        ``conditions`` is restricted to the fixed ``kind``/``value`` whitelist
        (url_equals / text_present / text_absent) with non-empty values;
        malformed contracts are rejected with ValueError. The goal must be a
        non-empty string. The contract is consumed at the START of the next
        turn (even a turn with no browser events), so it can never leak into a
        later unrelated prompt. Setting or replacing a contract while a turn,
        a permission ask, or a skill execution is in flight is refused — a
        post-hoc contract would be written after the fact.
        """
        if session_id in self._active_turn_sessions:
            raise RuntimeError("cannot set a browser task while a turn is active")
        if session_id in self._permission_tasks:
            raise RuntimeError("cannot set a browser task while a permission request is pending")
        if session_id in self._browser_skill_executing:
            raise RuntimeError("cannot set a browser task while a browser skill is executing")
        normalized = _normalize_browser_conditions(conditions)
        if normalized is None:
            raise ValueError(
                "browserTask conditions must be a list of "
                f"{{'kind': ..., 'value': ...}} with kinds in "
                f"{sorted(_ALLOWED_CONDITION_TYPES)} and non-empty string values "
                "(url_equals values must be absolute http(s) URLs with a host)"
            )
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("browserTask goal must be a non-empty string")
        self._browser_tasks[session_id] = BrowserTask(
            goal=goal,
            conditions=normalized,
        )

    def cancel_browser_task(self, session_id: str) -> None:
        """Cancel the full per-session browser lifecycle (permission + skill).

        Used by ACP session/cancel: aborts a pending permission ask AND a
        running takeover, clears any pending acceptance contract (an
        un-consumed contract can never be applied to a later unrelated turn),
        and leaves no floating tasks behind.
        """
        self._cancel_session_browser(session_id)

    def _cancel_session_browser(self, session_id: str) -> None:
        """Cancel a session's pending permission and in-flight skill task."""
        permission_task = self._permission_tasks.get(session_id)
        if permission_task is not None and not permission_task.done():
            permission_task.cancel()
            logger.info("[browser-skill] cancelled pending permission for session %s", session_id)
        task = self._skill_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()
            logger.info("[browser-skill] cancelled skill task for session %s", session_id)
        self._browser_tasks.pop(session_id, None)

    def _turn_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._turn_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._turn_locks[session_id] = lock
        return lock

    def _trajectory_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._trajectory_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._trajectory_locks[session_id] = lock
        return lock

    # ------------------------------------------------------------------
    # Trajectory notifications (client -> managed tasks, never blocking
    # the JSON-RPC reader loop)
    # ------------------------------------------------------------------

    def queue_trajectory_event(self, method: str, params: dict[str, Any]) -> None:
        """Enqueue a client trajectory notification into a managed task.

        Synchronous, so ``ext_notification`` never blocks the SDK reader on
        permission prompts. No-op when no event loop is running — unit tests
        either run inside a loop or call ``handle_trajectory_event`` directly.
        A done callback consumes task exceptions so a cancelled/failed managed
        task can never surface as an unhandled-task warning.
        """
        if self._closing:
            logger.debug("[browser-skill] dropping trajectory event %s during close", method)
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("[browser-skill] no running loop; dropping trajectory event %s", method)
            return
        task = asyncio.create_task(self.handle_trajectory_event(method, params or {}))
        self._trajectory_tasks.add(task)
        task.add_done_callback(self._trajectory_done)

    def _trajectory_done(self, task: asyncio.Task) -> None:
        """Consume a managed trajectory task's outcome (no unhandled-task warnings)."""
        self._trajectory_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("[browser-skill] trajectory task failed", exc_info=exc)

    async def handle_trajectory_event(self, method: str, params: Any) -> None:
        """Process one trajectory notification batch (directly testable).

        Strictly validates the payload: ``params`` must be a dict, ``tabId`` a
        real non-negative int, ``events`` a list of dicts — invalid shapes
        (strings, None, mixed tabs) are ignored without crashing. Only the
        known ``trajectory_event`` method on a registered tab is acted on.
        While a session is busy (normal turn or skill execution) the batch is
        NOT fed to the matcher (no self-suggestion), but the sanitized browser
        actions are appended to the session's current record buffer so
        activity-time evidence is never dropped. Matcher state is fed under a
        per-session lock so two concurrent batches can never race ``on_events``.
        """
        if method != "trajectory_event":
            logger.debug("[browser-skill] ignoring unknown trajectory method %r", method)
            return
        if not isinstance(params, dict):
            logger.debug("[browser-skill] ignoring non-dict trajectory params %r", params)
            return
        tab_id = params.get("tabId")
        if isinstance(tab_id, bool) or not isinstance(tab_id, int) or tab_id < 0:
            logger.debug("[browser-skill] ignoring invalid trajectory tabId %r", tab_id)
            return
        events = params.get("events")
        if not isinstance(events, list) or not events:
            return
        dict_events = [event for event in events if isinstance(event, dict)]
        if not dict_events:
            return
        session_id = self._tab_to_session.get(tab_id)
        if session_id is None:
            logger.debug("[browser-skill] ignoring trajectory for unregistered tab %r", tab_id)
            return
        logger.info(
            "[STEP 10] routing %d trajectory event(s) to session %s (tab %s)%s",
            len(dict_events), session_id, tab_id,
            " [busy: buffer only]"
            if session_id in self._active_turn_sessions or session_id in self._browser_skill_executing
            else " -> matcher.on_events",
        )
        for event in dict_events:
            event_tab = event.get("tabId")
            if event_tab is not None and event_tab != tab_id:
                logger.info("[browser-skill] rejecting mixed-tab trajectory batch for tab %s", tab_id)
                return
        if session_id in self._active_turn_sessions or session_id in self._browser_skill_executing:
            buffer = self._browser_turn_events.get(session_id)
            if buffer is not None:
                for event in sanitize_events(dict_events):
                    if event.get("type") in ("action", "navigation"):
                        # Human interventions on the live page during an
                        # agent-driven turn: labeled so the Reflector treats
                        # them as user corrections/steers, not agent output.
                        buffer.append({**event, "origin": "human"})
                logger.debug(
                    "[browser-skill] session %s busy; buffered %d trajectory event(s)",
                    session_id, len(dict_events),
                )
            return
        state = self._browser_skill_states.get(session_id)
        if state is None:
            return
        lock = self._trajectory_lock(session_id)
        async with lock:
            match = await state.on_events(dict_events)
        if match is not None:
            await self._suggest_and_maybe_run(session_id, match)

    # ------------------------------------------------------------------
    # Proactive suggestion + permission-gated execution
    # ------------------------------------------------------------------

    async def _suggest_and_maybe_run(self, session_id: str, match: Any) -> None:
        """Surface a proactive skill suggestion and ask the user.

        Emits an ACP suggestion message, then request_permission with a 60s
        timeout. Only an explicit ``allow_once`` answer executes; deny,
        reject, timeout and cancel are all no-ops. The permission wait itself
        is registered in ``_permission_tasks`` so cancel/rebind can abort the
        whole suggest -> wait -> execute lifecycle, and the binding
        (session + tab + generation + no concurrent turn) is re-validated
        AFTER the grant — authorization for a stale tab is never executed.
        """
        conn = self._conn
        state = self._browser_skill_states.get(session_id)
        if conn is None or state is None or state.tab_id is None:
            return
        tab_id = state.tab_id
        if self._tab_to_session.get(tab_id) != session_id:
            logger.info("[browser-skill] tab %s no longer bound to session %s; skipping suggestion", tab_id, session_id)
            return
        if session_id in self._permission_tasks or session_id in self._skill_tasks:
            logger.info("[browser-skill] session %s already asked/executing; skipping suggestion", session_id)
            return

        capacity_id = getattr(match, "capacity_id", "")
        skill_name = getattr(match, "skill_name", capacity_id)
        generation = self._tab_generations.get(session_id, 0)
        permission_task = asyncio.current_task()
        if permission_task is not None:
            self._permission_tasks[session_id] = permission_task
        try:
            await conn.session_update(
                session_id,
                update_agent_message_text(
                    f"Detected browser skill \"{skill_name}\". Allow me to take over? ({capacity_id})"
                ),
            )
            from acp.schema import PermissionOption, ToolCallUpdate

            permission = await asyncio.wait_for(
                conn.request_permission(
                    session_id,
                    ToolCallUpdate(
                        tool_call_id=f"skill-{capacity_id}",
                        kind="execute",
                        status="pending",
                        title=f"Run browser skill \"{skill_name}\"",
                        raw_input={"capacity_id": capacity_id},
                    ),
                    [
                        PermissionOption(option_id="allow_once", name="Allow once", kind="allow_once"),
                        PermissionOption(option_id="reject_once", name="Reject", kind="reject_once"),
                    ],
                ),
                timeout=_PERMISSION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.info("[browser-skill] permission not granted (timeout) for session %s", session_id)
            return
        except asyncio.CancelledError:
            logger.info("[browser-skill] permission request cancelled for session %s", session_id)
            raise
        except Exception:
            logger.exception("[browser-skill] permission request failed for session %s", session_id)
            return
        finally:
            if self._permission_tasks.get(session_id) is permission_task:
                self._permission_tasks.pop(session_id, None)

        outcome = getattr(permission, "outcome", None)
        option_id = getattr(outcome, "option_id", None)
        if getattr(outcome, "outcome", None) != "selected" or option_id != "allow_once":
            logger.info(
                "[browser-skill] user did not allow_once for session %s (outcome=%r option=%r)",
                session_id, getattr(outcome, "outcome", None), option_id,
            )
            return

        # Re-validate the whole binding after the grant; anything that moved
        # while the user was deciding (tab rebound, session busy, shutdown)
        # cancels the takeover silently.
        if self._closing:
            logger.info("[browser-skill] closing; skipping execution for session %s", session_id)
            return
        if session_id in self._active_turn_sessions or session_id in self._skill_tasks:
            logger.info("[browser-skill] session %s busy after permission; skipping execution", session_id)
            return
        if self._tab_generations.get(session_id, 0) != generation:
            logger.info("[browser-skill] tab binding changed while waiting; skipping execution for session %s", session_id)
            return
        state = self._browser_skill_states.get(session_id)
        if state is None or state.tab_id != tab_id or self._tab_to_session.get(tab_id) != session_id:
            logger.info("[browser-skill] tab %s no longer owned by session %s; skipping execution", tab_id, session_id)
            return

        logger.info("[browser-skill] user allowed takeover; executing %s for session %s", capacity_id, session_id)
        task = asyncio.create_task(self._run_skill_task(session_id, match))
        self._skill_tasks[session_id] = task
        task.add_done_callback(lambda done, sid=session_id: self._skill_task_done(sid, done))

    def _skill_task_done(self, session_id: str, task: asyncio.Task) -> None:
        """Consume a skill task's outcome; never leave an unhandled-task warning."""
        if self._skill_tasks.get(session_id) is task:
            self._skill_tasks.pop(session_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("[browser-skill] skill task failed for session %s", session_id, exc_info=exc)

    async def _run_skill_task(self, session_id: str, match: Any) -> None:
        """Run the matched skill via executor.run_skill (which self-enqueues).

        Marks the session as executor-owned so ``__call__`` fallback turns
        still inject context but never double-persist records — but only while
        the executing task is actually this one.
        """
        self._browser_skill_executing.add(session_id)
        try:
            from siada.services.browser_skill import executor

            await executor.run_skill(match, self, session_id)
        except asyncio.CancelledError:
            logger.info("[browser-skill] skill task cancelled for session %s", session_id)
            raise
        except Exception:
            logger.exception("[browser-skill] skill execution failed for session %s", session_id)
        finally:
            self._browser_skill_executing.discard(session_id)
            if self._skill_tasks.get(session_id) is asyncio.current_task():
                self._skill_tasks.pop(session_id, None)

    def _executor_owns_persistence(self, session_id: str) -> bool:
        """Whether the CURRENT task is the skill owner for this session.

        Merely being in ``_browser_skill_executing`` is not enough: only the
        executor's own fallback task may skip runtime persistence; an unrelated
        prompt reaching the same code path must keep runtime ownership.
        """
        return (
            session_id in self._browser_skill_executing
            and self._skill_tasks.get(session_id) is asyncio.current_task()
        )

    def last_turn_events(self, session_id: str) -> list[dict]:
        """Browser-action evidence collected during the session's last turn.

        Normal turns and executor fallback turns fill this buffer; trajectory
        notifications arriving while a turn is active are appended here too, so
        the skill executor can persist complete evidence in its own record.
        """
        return self._browser_turn_events.get(session_id, [])

    # ------------------------------------------------------------------
    # Background learning worker (lazy; managed by close())
    # ------------------------------------------------------------------

    def wake_browser_learning(self) -> None:
        """Wake the lazy BrowserLearningWorker so queued records are distilled.

        Only spawns/calls into the worker when an event loop is actually
        running — synchronous registration paths (unit tests, scheduler setup)
        never create coroutines or fake a wake.
        """
        if self._worker is None:
            self._worker = BrowserLearningWorker()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("[browser-skill] no running loop; deferring worker wake")
            return
        try:
            self._worker.wake()
        except Exception:
            logger.exception("[browser-skill] worker wake failed")

    async def close(self) -> None:
        """Cancel the full browser lifecycle and shut down the worker.

        Sets the closing flag first so a permission grant racing shutdown can
        never spawn a new skill task, then cancels skill tasks, pending
        permission asks, and remaining trajectory tasks, waits for them, and
        clears every map — no floating tasks survive close().
        """
        self._closing = True

        skill_tasks = [task for task in self._skill_tasks.values() if not task.done()]
        for task in skill_tasks:
            task.cancel()
        if skill_tasks:
            await asyncio.gather(*skill_tasks, return_exceptions=True)
        self._skill_tasks.clear()
        self._browser_skill_executing.clear()

        permission_tasks = [task for task in self._permission_tasks.values() if not task.done()]
        for task in permission_tasks:
            task.cancel()
        if permission_tasks:
            await asyncio.gather(*permission_tasks, return_exceptions=True)
        self._permission_tasks.clear()

        trajectory_tasks = [task for task in self._trajectory_tasks if not task.done()]
        for task in trajectory_tasks:
            task.cancel()
        if trajectory_tasks:
            await asyncio.gather(*trajectory_tasks, return_exceptions=True)
        self._trajectory_tasks.clear()

        if self._worker is not None:
            try:
                await self._worker.close()
            except Exception:
                logger.exception("[browser-skill] worker close failed")
            self._worker = None

    # ------------------------------------------------------------------
    # Normal turn: read/write loop over existing browser state
    # ------------------------------------------------------------------

    def _resolve_browser_context(self, session_id: str, prompt: str) -> dict | None:
        """Determine whether this turn has browser context.

        Priority: an explicit ``<browser-context ...>`` marker. A marker with a
        tabId must match this session's registered tab; a marker WITHOUT a
        tabId is only honored for sessions that already have a registered tab
        (the tab is implied). The plain ``URL:``-inside-tag form is parsed the
        same way. Fallback: the current domain tracked from live trajectory
        events. A non-browser turn returns None and keeps the plain
        wrap_user_input semantics.
        """
        explicit = _extract_browser_context(prompt)
        if explicit is not None:
            state = self._browser_skill_states.get(session_id)
            if explicit["tab_id"] is not None:
                if state is None or state.tab_id != explicit["tab_id"]:
                    logger.info(
                        "[browser-skill] browser-context tabId %s does not match session %s; ignoring marker",
                        explicit["tab_id"], session_id,
                    )
                    return None
            elif state is None or state.tab_id is None:
                logger.info(
                    "[browser-skill] browser-context without tabId requires a registered tab; ignoring marker for %s",
                    session_id,
                )
                return None
            if not _registered_domain(explicit["url"]):
                return None
            return explicit
        state = self._browser_skill_states.get(session_id)
        if (
            state is not None
            and state.tab_id is not None
            and getattr(state, "_current_domain", "")
        ):
            return {
                "url": state._current_domain,
                "tab_id": state.tab_id,
                "prompt": prompt,
            }
        return None

    async def _inject_browser_context(self, ctx: dict) -> tuple[str, list[str]]:
        """Load active playbook entries for the turn's domain.

        Returns (context_text, entry_ids). The text is explicitly framed as a
        low-trust experience suggestion — it must never expand user
        authorization. Failures degrade to no context, never to a broken turn.
        """
        domain = _registered_domain(ctx.get("url") or "")
        if not domain:
            return "", []
        try:
            text, entry_ids = PlaybookStore().context_for_domain(domain)
        except Exception:
            logger.exception(
                "[browser-skill] context_for_domain failed for %s; continuing without context", domain
            )
            return "", []
        if not text:
            return "", []
        return f"[Low-trust experience suggestion · browser-skill · {domain}]\n{text}", list(entry_ids or [])

    async def _stream_turn(self, session_id: str, prompt: str):
        """Run one agent turn and yield ACP updates (see ``__call__``)."""
        runtime_session = self._sessions[session_id]
        extra_mcp_servers = await self._connect_session_mcp(session_id)

        # The pending acceptance contract is snapshotted at turn START: the
        # next turn — browser or not, with events or not — consumes it, so a
        # stale contract can never leak into a later unrelated prompt.
        contract = self._browser_tasks.pop(session_id, None)

        browser_ctx = self._resolve_browser_context(session_id, prompt)
        user_prompt = browser_ctx.get("prompt") if browser_ctx is not None else prompt
        context_text = ""
        injected_ids: list[str] = []
        if browser_ctx is not None:
            context_text, injected_ids = await self._inject_browser_context(browser_ctx)

        # No explicit contract: concurrently draft one via the fast LLM so the
        # verified-promotion gate can open for ordinary turns. Drafting sees
        # only the task text — the contract stays pre-declared — and it is
        # resolved only when the turn actually performed browser operations.
        auto_contract_task: asyncio.Task[BrowserTask | None] | None = None
        if contract is None and browser_ctx is not None:
            auto_contract_task = asyncio.create_task(
                self._draft_browser_contract(user_prompt, browser_ctx)
            )

        # Wrap the raw ACP client text in <user_input> tags, mirroring the
        # TUI entry points (nointeractive_controller.py / conversation_turn.py)
        # so downstream consumers (frontend display, history, memory review)
        # can recover exactly what the human typed via strip_user_input().
        # Playbook experience suggestions are appended OUTSIDE that label:
        # they are untrusted injected context, never part of the user's text.
        user_input = wrap_user_input(user_prompt)
        if context_text:
            user_input = f"{user_input}\n\n{context_text}"

        domain = _registered_domain(browser_ctx["url"]) if browser_ctx else ""
        # The per-turn record buffer: browser tool calls collected below plus
        # sanitized trajectory notifications arriving while the turn is active.
        collected: list[dict] = []
        browser_calls: dict[str, dict] = {}
        # Native apply_patch calls seen so far this turn, keyed by call id: the
        # result renders from the SDK's custom display data when the local
        # editor recorded the applied text, and falls back to the operation of
        # the call itself otherwise.
        native_patch_calls: dict[str, object] = {}
        self._browser_turn_events.pop(session_id, None)
        if browser_ctx is not None:
            self._browser_turn_events[session_id] = collected

        try:
            async for te in self._orchestrator.run_agent_turn(
                session=runtime_session.session,
                user_input=user_input,
                agent_name=self._agent_name,
                workspace=runtime_session.workspace,
                extra_mcp_servers=extra_mcp_servers,
            ):
                if te.kind == TEXT_DELTA and te.delta:
                    yield update_agent_message_text(te.delta)
                elif te.kind == REASONING_DELTA and te.delta:
                    yield update_agent_thought_text(te.delta)
                elif te.kind == TOOL_CALL_START:
                    yield start_tool_call(
                        tool_call_id=te.call_id,
                        title=te.name,
                        status="pending",
                    )
                    if te.is_apply_patch:
                        # Keep the call so its operation can stand in for the
                        # display when the SDK collected no custom patch data.
                        native_patch_calls[te.call_id] = te.raw_item
                    # Browser tools are only collected for turns that
                    # actually have browser context; a browser-like tool in
                    # an ordinary code turn must never form a domain-less
                    # record.
                    if _is_browser_tool(te.name) and browser_ctx is not None:
                        browser_calls[te.call_id] = {
                            "event_id": str(uuid4()),
                            "ts": int(time.time() * 1000),
                            "type": "action",
                            "origin": "agent",
                            "url": domain,
                            "action": {
                                "kind": "tool",
                                "tool": te.name,
                                "tool_call_id": te.call_id,
                                "arguments": None,
                            },
                        }
                elif te.kind == TOOL_CALL_DONE:
                    if te.is_apply_patch:
                        # A native patch call has no JSON arguments: its
                        # operation is what the client shows as the input.
                        native_patch_calls[te.call_id] = te.raw_item
                        yield update_tool_call(
                            tool_call_id=te.call_id,
                            status="in_progress",
                            raw_input=_apply_patch_operation(te.raw_item),
                        )
                    else:
                        yield update_tool_call(
                            tool_call_id=te.call_id,
                            status="in_progress",
                            raw_input=_parse_tool_arguments(te.arguments),
                        )
                        pending = browser_calls.get(te.call_id)
                        if pending is not None:
                            pending["action"]["arguments"] = _parse_tool_arguments(te.arguments)
                elif te.kind == TOOL_OUTPUT:
                    if te.call_id:
                        if te.is_apply_patch:
                            # Native patches render from the text the local
                            # editor actually applied; the call's operation is
                            # the fallback for replays without that payload.
                            output_text = render_apply_patch_display(
                                custom_data=te.custom_data,
                                raw_call=native_patch_calls.get(te.call_id),
                                output=te.output,
                            )
                        else:
                            output_text = _stringify_tool_output(te.output)
                        yield update_tool_call(
                            tool_call_id=te.call_id,
                            status="completed",
                            # Pass the stringified text, NOT the raw observation
                            # object: FunctionCallResult subclasses (e.g.
                            # WebSearchObservation) hand-write __init__ without
                            # the dataclass `content` field, and pydantic's
                            # Any-field serializer dumps them AS the parent
                            # dataclass → AttributeError → the whole turn fails
                            # with "Internal error".
                            raw_output=output_text,
                            content=[tool_content(text_block(output_text))],
                        )
                        pending = browser_calls.pop(te.call_id, None)
                        if pending is not None:
                            pending["response"] = output_text
                            pending["raw_output"] = output_text
                            pending["raw_input"] = pending["action"].get("arguments")
                            parsed = parse_tool_result(te.output)
                            pending["ok"] = parsed.get("ok")
                            if parsed.get("error"):
                                pending["tool_error"] = parsed["error"]
                            collected.append(pending)

            # Any browser call that started but never produced an output event
            # is still part of the evidence (attempted operation).
            collected.extend(browser_calls.values())
            if collected:
                if auto_contract_task is not None:
                    contract = await _await_auto_contract(auto_contract_task)
                await self._record_browser_turn(
                    session_id,
                    prompt=user_prompt,
                    domain=domain,
                    events=collected,
                    contract=contract,
                    injected_ids=injected_ids,
                    extra_mcp_servers=extra_mcp_servers,
                )
        except asyncio.CancelledError:
            _discard_auto_contract(auto_contract_task)
            if collected or contract is not None:
                await self._record_browser_turn(
                    session_id,
                    prompt=user_prompt,
                    domain=domain,
                    events=collected,
                    contract=contract,
                    injected_ids=injected_ids,
                    extra_mcp_servers=extra_mcp_servers,
                    failure_reason="cancelled",
                )
            raise
        except Exception as exc:
            _discard_auto_contract(auto_contract_task)
            failure_reason = f"{type(exc).__name__}: {exc}" if exc else "agent turn failed"
            if collected or contract is not None:
                await self._record_browser_turn(
                    session_id,
                    prompt=user_prompt,
                    domain=domain,
                    events=collected,
                    contract=contract,
                    injected_ids=injected_ids,
                    extra_mcp_servers=extra_mcp_servers,
                    failure_reason=failure_reason,
                )
            raise
        finally:
            # Abandon any draft that was never resolved (no browser ops,
            # or the failure paths above already discarded it).
            _discard_auto_contract(auto_contract_task)

    async def _record_browser_turn(
        self,
        session_id: str,
        *,
        prompt: str,
        domain: str,
        events: list[dict],
        contract: BrowserTask | None = None,
        injected_ids: list[str],
        extra_mcp_servers: list[Any],
        failure_reason: str | None = None,
    ) -> None:
        """Persist one ExecutionRecord for a real browser turn.

        Only actual browser operations on a registered tab produce records; a
        browser-like tool call in a turn without browser context never forms an
        empty-domain record. While the skill executor's OWN task drives the
        turn, persistence is skipped (the executor records itself) — an
        unrelated prompt reaching the same code path keeps runtime ownership.

        Verification status rules (design doc §3.1): no pre-declared criteria
        or un-attributable tab evidence -> unknown; turn-level failures
        (including user cancel) -> unknown; a clear tool error with a
        terminal verification success is still success (recovery). The
        pre-declared conditions and the fresh observation are both kept as
        verification evidence.
        """
        if not events and not failure_reason:
            return
        state = self._browser_skill_states.get(session_id)
        if state is None or state.tab_id is None or not domain:
            logger.debug(
                "[browser-skill] no registered browser state/domain for session %s; not recording",
                session_id,
            )
            return
        if self._executor_owns_persistence(session_id):
            logger.debug(
                "[browser-skill] executor owns persistence for session %s; skipping runtime enqueue",
                session_id,
            )
            return

        # The contract was snapshotted at turn start; it is passed in so the
        # same frozen goal/conditions are used by every record path.
        goal = (contract.goal if contract and contract.goal else prompt) or "browser task"
        conditions = list(contract.conditions) if contract else []
        tab_id = state.tab_id

        # Verify AFTER execution, only against pre-declared conditions.
        verification_result: VerificationResult | None = None
        observation: dict | None = None
        if failure_reason:
            verification_result = VerificationResult("unknown", f"agent turn {failure_reason}")
        elif not self._events_attributable_to_tab(events, tab_id):
            # Another tab's behavior can never be used to pass this tab's
            # acceptance criteria.
            verification_result = VerificationResult(
                "unknown", "browser actions could not be attributed to the registered tab"
            )
        elif conditions:
            verification_result, observation = await self._verify_turn_conditions(
                session_id, conditions, extra_mcp_servers
            )
            if verification_result is None:
                verification_result = VerificationResult(
                    "unknown", "verification unavailable or tab unbound"
                )
        else:
            verification_result = VerificationResult("unknown", "no acceptance criteria specified")

        # Pre-declared conditions + fresh observation are themselves evidence.
        events = [
            *events,
            {
                "event_id": str(uuid4()),
                "ts": int(time.time() * 1000),
                "type": "verification",
                "conditions": conditions,
                "result": verification_result.status if verification_result else "unknown",
                "reason": verification_result.reason if verification_result else "",
                "observation": observation or {},
            },
        ]

        # One deterministic capacity per goal text (language-agnostic): the
        # playbook knowledge, replay steps, and feedback attribution for this
        # task all accumulate under the same id across runs.
        from siada.services.browser_skill.registry import task_capacity_id

        capacity_id = task_capacity_id(domain, goal)
        used_ids = self._filter_used_entry_ids(capacity_id, injected_ids)

        record = ExecutionRecord(
            execution_id=str(uuid4()),
            capacity_id=capacity_id,
            domain=domain,
            goal=sanitize_text(goal),
            events=sanitize_events(events),
            verification=verification_result,
            source="agent",
            used_entry_ids=used_ids,
        )
        try:
            PlaybookStore().enqueue(record)
            logger.info(
                "[STEP 11] execution record enqueued to learning queue: "
                "execution_id=%s capacity=%s verification=%s events=%d session=%s (source=turn-end)",
                record.execution_id,
                capacity_id,
                verification_result.status if verification_result else "unknown",
                len(events),
                session_id,
            )
            self.wake_browser_learning()
        except Exception:
            logger.exception(
                "[browser-skill] failed to enqueue execution record (user task unaffected) for session %s",
                session_id,
            )

    async def _draft_browser_contract(
        self, user_prompt: str, browser_ctx: dict
    ) -> BrowserTask | None:
        """Draft an acceptance contract for a browser turn without an explicit one.

        The fast LLM sees only the task text and the starting page URL — never
        the execution outcome — so drafted conditions stay pre-declared. The
        goal is deliberately left empty: `_record_browser_turn` falls back to
        the prompt text, keeping capacity identity identical to the
        no-contract path. Any failure (quota, timeout, malformed output)
        returns None, which is exactly today's no-contract behavior.
        """
        prompt = _AUTO_CONTRACT_PROMPT.format(
            url=browser_ctx.get("url") or "", task=user_prompt
        )
        try:
            async with asyncio.timeout(_AUTO_CONTRACT_TIMEOUT_SECONDS):
                text = await call_fast_llm(
                    prompt, agent_name="browser_skill_contract_drafter"
                )
        except Exception:
            return None
        data = parse_json_from_model(text)
        conditions = _normalize_browser_conditions(data.get("conditions"))
        if not conditions:
            return None
        return BrowserTask(goal="", conditions=conditions)

    @staticmethod
    def _events_attributable_to_tab(events: list[dict], tab_id: int) -> bool:
        """Whether every action explicitly names ``tab_id`` (or no tab at all).

        A browser call that names a DIFFERENT tab (or names nothing and cannot
        be pinned to this tab) must not be verified against this tab's page.
        """
        for event in events:
            if event.get("type") != "action":
                continue
            event_tab = event.get("tabId")
            action = event.get("action") or {}
            arguments = action.get("arguments") if isinstance(action, dict) else None
            call_tab = arguments.get("tabId") if isinstance(arguments, dict) else None
            if event_tab is not None and event_tab != tab_id:
                return False
            if call_tab is not None and call_tab != tab_id:
                return False
        return True

    async def _verify_turn_conditions(
        self, session_id: str, conditions: list[dict], extra_mcp_servers: list[Any]
    ) -> tuple[VerificationResult | None, dict | None]:
        """Verify pre-declared conditions against the live tab observation.

        A verification failure degrades to ``(None, None)`` (recorded as
        unknown) but a real condition result is always returned for the queue.
        """
        state = self._browser_skill_states.get(session_id)
        tab_id = state.tab_id if state else None
        if tab_id is None:
            logger.info("[browser-skill] no registered tab for session %s; cannot verify", session_id)
            return None, None
        try:
            result = verify_conditions(extra_mcp_servers or [], tab_id, conditions)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            logger.exception("[browser-skill] verify_conditions failed for session %s", session_id)
            return None, None
        if not isinstance(result, tuple) or len(result) != 2:
            logger.warning("[browser-skill] verify_conditions returned unexpected shape for session %s", session_id)
            return None, None
        return result

    def _filter_used_entry_ids(self, capacity_id: str, injected_ids: list[str]) -> list[str]:
        """Keep only injected entry ids that belong to this capacity's snapshot.

        Prevents attributing a turn's outcome to entries of another skill —
        a failure to resolve the snapshot degrades to no attribution (logged),
        never to cross-skill attribution. The snapshot is the ``{entries:
        [...]}`` dict shape returned by PlaybookStore.snapshot.
        """
        if not injected_ids:
            return []
        try:
            snapshot = PlaybookStore().snapshot(capacity_id)
        except Exception:
            logger.exception(
                "[browser-skill] snapshot(%s) unavailable; recording no used entries", capacity_id
            )
            return []
        if not isinstance(snapshot, dict):
            return []
        entries = snapshot.get("entries")
        if not isinstance(entries, list):
            return []
        valid: set[str] = set()
        for entry in entries:
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            if entry_id is not None:
                valid.add(str(entry_id))
        return [iid for iid in injected_ids if iid in valid]


def _parse_tool_arguments(arguments: str) -> Any:
    """Best-effort JSON decode of a tool call's raw arguments string."""
    if not arguments:
        return None
    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return arguments


def _apply_patch_operation(raw_call: Any) -> Any:
    """Return the JSON-compatible operation payload of a native apply_patch call.

    Newer Agents SDK builds expose the operation as a pydantic model while
    older ones pass the mapping straight through; the client shows either
    shape as the tool call's input.
    """
    operation = getattr(raw_call, "operation", None)
    if hasattr(operation, "model_dump"):
        return operation.model_dump(exclude_none=True)
    return operation


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
