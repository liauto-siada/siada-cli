"""Official ACP SDK adapter for Siada."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable
import inspect
import logging
from typing import Any
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION,
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
)
from acp.helpers import (
    SessionUpdate,
    update_agent_message_text,
    update_available_commands,
    update_user_message_text,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AvailableCommand,
    ClientCapabilities,
    Implementation,
    ListSessionsResponse,
    LoadSessionResponse,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionInfo,
    SessionListCapabilities,
    SessionResumeCapabilities,
    SetSessionConfigOptionResponse,
    TextContentBlock,
)

logger = logging.getLogger(__name__)

MODEL_CONFIG_OPTION_ID = "model"


def _mcp_servers_to_siada_configs(acp_mcp_servers: list[Any] | None) -> list[Any]:
    """Convert ACP ``mcpServers`` entries (from ``session/new``) into Siada
    ``MCPServerConfig`` objects so the turn runner can connect them.

    ``acp_mcp_servers`` is a list of SDK models (``HttpMcpServer``,
    ``SseMcpServer``, ``McpServerStdio``, ``AcpMcpServer``). ACP-over-ACP
    servers are not supported by Siada and are skipped.
    """
    if not acp_mcp_servers:
        return []
    from siada.config.mcp_config import MCPServerConfig

    def _headers_dict(headers: list[Any] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for header in headers or []:
            name = getattr(header, "name", None)
            value = getattr(header, "value", None)
            if name is not None and value is not None:
                result[str(name)] = str(value)
        return result

    def _env_dict(env: list[Any] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for variable in env or []:
            name = getattr(variable, "name", None)
            value = getattr(variable, "value", None)
            if name is not None and value is not None:
                result[str(name)] = str(value)
        return result

    configs: list[MCPServerConfig] = []
    for server in acp_mcp_servers:
        server_type = getattr(server, "type", None)
        name = getattr(server, "name", None) or "acp-mcp"
        try:
            if server_type == "http":
                configs.append(
                    MCPServerConfig(
                        type="http",
                        url=getattr(server, "url", None),
                        headers=_headers_dict(getattr(server, "headers", None)),
                    )
                )
            elif server_type == "sse":
                configs.append(
                    MCPServerConfig(
                        type="sse",
                        url=getattr(server, "url", None),
                        headers=_headers_dict(getattr(server, "headers", None)),
                    )
                )
            elif server_type == "stdio":
                configs.append(
                    MCPServerConfig(
                        type="stdio",
                        command=getattr(server, "command", None),
                        args=list(getattr(server, "args", None) or []),
                        env=_env_dict(getattr(server, "env", None)),
                    )
                )
            else:
                logger.warning("[acp] Skipping unsupported ACP MCP server type=%r name=%r", server_type, name)
        except Exception:
            logger.exception("[acp] Failed to convert ACP MCP server %r", server_type)
    return configs

TurnRunner = Callable[
    [str, str],
    Iterable[SessionUpdate] | AsyncIterable[SessionUpdate] | Awaitable[Iterable[SessionUpdate] | AsyncIterable[SessionUpdate]],
]


class SiadaAcpAgent(Agent):
    """Expose a Siada turn runner through the official ACP Python SDK."""

    def __init__(
        self,
        turn_runner: TurnRunner,
        session_creator: Callable[[str, str], None] | None = None,
        model_lister: Callable[[], list[str]] | None = None,
        model_getter: Callable[[str], str] | None = None,
        model_setter: Callable[[str, str], None] | None = None,
        command_matcher: Callable[[str], bool] | None = None,
        command_lister: Callable[[str], list[tuple[str, str]]] | None = None,
        command_runner: TurnRunner | None = None,
        session_lister: Callable[[str | None], list[dict[str, Any]]] | None = None,
        session_restorer: Callable[[str, str, list[Any] | None], Any] | None = None,
        history_lister: Callable[[str], list[dict[str, str]]] | None = None,
        # Optional browser-skill ACE wiring (all degrade to no-ops when None):
        #   connection_setter — receive the connected ACP client (runtime
        #     pushes suggestions and asks request_permission through it);
        #   tab_registrar — bind a client-declared tabId to a session;
        #   trajectory_handler — route `_trajectory_event` notifications to the
        #     runtime's managed queue (never awaited in the SDK reader loop);
        #   task_setter — register an explicit goal+conditions browser task;
        #   canceller — pass session/cancel through to in-flight skill tasks.
        connection_setter: Callable[[Any], None] | None = None,
        tab_registrar: Callable[[str, int], None] | None = None,
        trajectory_handler: Callable[[str, dict[str, Any]], None] | None = None,
        task_setter: Callable[[str, str, list[dict] | None], None] | None = None,
        canceller: Callable[[str], None] | None = None,
    ):
        self._turn_runner = turn_runner
        self._session_creator = session_creator
        self._model_lister = model_lister
        self._model_getter = model_getter
        self._model_setter = model_setter
        # Slash-command support is fully optional: `command_matcher` decides
        # whether prompt text is a command, `command_lister` builds the
        # menu advertised via available_commands_update, and `command_runner`
        # actually executes one. All three default to None so this class
        # keeps working unchanged for callers that don't wire them up.
        self._command_matcher = command_matcher
        self._command_lister = command_lister
        self._command_runner = command_runner
        # Session history support, also optional: `session_lister` returns
        # persisted sessions for session/list (dicts with session_id / cwd /
        # title / updated_at), `session_restorer` loads one back into a live
        # runtime session for session/load and session/resume, and
        # `history_lister` returns display-ready messages for the load
        # replay. All three default to None so capabilities degrade
        # gracefully when not wired up.
        self._session_lister = session_lister
        self._session_restorer = session_restorer
        self._history_lister = history_lister
        self._connection_setter = connection_setter
        self._tab_registrar = tab_registrar
        self._trajectory_handler = trajectory_handler
        self._task_setter = task_setter
        self._canceller = canceller
        self._conn: Client | None = None
        self._sessions: set[str] = set()
        self._session_cwd: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._active_prompts: dict[str, asyncio.Task[PromptResponse]] = {}

    def on_connect(self, conn: Client) -> None:
        self._conn = conn
        if self._connection_setter is not None:
            try:
                self._connection_setter(conn)
            except Exception:
                logger.exception("[acp] connection_setter failed")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **_: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                # Advertise the full session-history surface implemented by
                # this agent: session/list (disk-backed via session_lister),
                # session/load (restore + history replay) and the unstable
                # session/resume (restore without replay). load_session is
                # a top-level boolean on AgentCapabilities; list/resume hang
                # off session_capabilities.
                load_session=True,
                session_capabilities=SessionCapabilities(
                    list=SessionListCapabilities(),
                    resume=SessionResumeCapabilities(),
                ),
            ),
            agent_info=Implementation(name="siada", title="Siada", version="1.7.17"),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **meta: Any,
    ) -> NewSessionResponse:
        session_id = str(uuid4())
        try:
            mcp_configs = _mcp_servers_to_siada_configs(mcp_servers)
            if mcp_configs:
                logger.info("[acp] new_session forwarding %d MCP server(s)", len(mcp_configs))
            if self._session_creator is not None:
                # session_creator may accept an optional third MCP-configs arg.
                try:
                    result = self._session_creator(session_id, cwd, mcp_configs)
                    if inspect.isawaitable(result):
                        await result
                except TypeError:
                    self._session_creator(session_id, cwd)
            self._sessions.add(session_id)
            self._session_cwd[session_id] = cwd
            # Client-declared browser binding (SDK `_meta` → tabId /
            # browserTask) is applied only after the session is registered.
            self._register_browser_meta(session_id, meta)
            await self._advertise_commands(session_id)
            return NewSessionResponse(
                session_id=session_id,
                modes=None,
                config_options=self._build_config_options(session_id),
            )
        except Exception:
            logger.exception("new_session() failed for cwd=%s", cwd)
            raise

    def _register_browser_meta(self, session_id: str, meta: dict[str, Any] | None) -> None:
        """Wire client-declared browser metadata into the runtime bridge.

        The SDK router flattens a request's ``_meta`` (field_meta) into
        top-level kwargs, so ``tabId`` and ``browserTask`` arrive here as
        plain keys. ``browserTask`` is an explicit goal + acceptance
        conditions, NOT a post-hoc success claim. All optional; failures are
        logged, never fatal to session creation/restore.
        """
        meta = meta or {}
        tab_id = meta.get("tabId")
        if tab_id is not None and self._tab_registrar is not None:
            # Pass the raw value through: the runtime's register_tab enforces
            # "real non-negative int, not a bool/string", so a client sending
            # "42" or False can never silently steal a tab.
            try:
                self._tab_registrar(session_id, tab_id)
            except (TypeError, ValueError):
                logger.warning("[acp] invalid tabId in _meta for session %s: %r", session_id, tab_id)
            except Exception:
                logger.exception("[acp] tab_registrar failed for session %s", session_id)
        browser_task = meta.get("browserTask")
        if browser_task and self._task_setter is not None:
            try:
                self._task_setter(
                    session_id,
                    str((browser_task or {}).get("goal") or ""),
                    (browser_task or {}).get("conditions") or [],
                )
            except Exception:
                logger.exception("[acp] task_setter failed for session %s", session_id)

    async def _advertise_commands(self, session_id: str) -> None:
        """Push the slash-command menu as a session/update notification.

        There's no field for this on NewSessionResponse (unlike
        config_options) — ACP only exposes available commands through the
        available_commands_update SessionUpdate, so this has to happen as a
        separate push right after the session is created.
        """
        if self._conn is None or self._command_lister is None:
            return
        commands = self._command_lister(session_id)
        if not commands:
            return
        await self._conn.session_update(
            session_id,
            update_available_commands(
                AvailableCommand(name=name, description=description)
                for name, description in commands
            ),
        )

    def _build_config_options(self, session_id: str) -> list[SessionConfigOptionSelect] | None:
        if self._model_lister is None or self._model_getter is None:
            return None
        models = self._model_lister()
        if not models:
            return None
        return [
            SessionConfigOptionSelect(
                type="select",
                id=MODEL_CONFIG_OPTION_ID,
                name="Model",
                category="model",
                current_value=self._model_getter(session_id),
                options=[SessionConfigSelectOption(value=model, name=model) for model in models],
            )
        ]

    async def set_config_option(
        self, config_id: str, session_id: str, value: str | bool, **_: Any
    ) -> SetSessionConfigOptionResponse | None:
        try:
            if config_id == MODEL_CONFIG_OPTION_ID and self._model_setter is not None:
                self._model_setter(session_id, str(value))
            return SetSessionConfigOptionResponse(config_options=self._build_config_options(session_id) or [])
        except Exception:
            logger.exception(
                "set_config_option() failed for session_id=%s config_id=%s value=%r",
                session_id,
                config_id,
                value,
            )
            raise

    async def list_sessions(
        self, cwd: str | None = None, cursor: str | None = None, **_: Any
    ) -> ListSessionsResponse:
        # Disk-backed sessions (persisted by FileSession, restorable across
        # agent restarts) via the session_lister callback; in-memory sessions
        # created since this agent started are merged in as a fallback for
        # callers that haven't persisted anything yet.
        sessions: list[SessionInfo] = []
        if self._session_lister is not None:
            listed = self._session_lister(cwd)
            if inspect.isawaitable(listed):
                listed = await listed
            for entry in listed:
                sessions.append(self._to_session_info(entry))
        known = {info.session_id for info in sessions}
        for session_id, session_cwd in self._session_cwd.items():
            if session_id in known:
                continue
            if cwd and session_cwd != cwd:
                continue
            sessions.append(SessionInfo(session_id=session_id, cwd=session_cwd))
        return ListSessionsResponse(sessions=sessions, next_cursor=None)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        additional_directories: list[str] | None = None,
        **meta: Any,
    ) -> LoadSessionResponse | None:
        """Restore a persisted session and replay its history.

        Protocol contract (session/load): restore the session context and
        conversation history, connect to the specified MCP servers, and
        stream the entire history back to the client as user/agent message
        chunk notifications before responding.
        """
        await self._restore_session_common(session_id, cwd, mcp_servers, meta)
        await self._replay_history(session_id)
        return LoadSessionResponse(
            modes=None,
            config_options=self._build_config_options(session_id),
        )

    async def resume_session(
        self,
        session_id: str,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **meta: Any,
    ) -> ResumeSessionResponse:
        """Restore a persisted session without replaying history.

        Protocol contract (session/resume): like session/load, but the
        client explicitly opts out of the history replay.
        """
        await self._restore_session_common(session_id, cwd, mcp_servers, meta)
        return ResumeSessionResponse(
            modes=None,
            config_options=self._build_config_options(session_id),
        )

    async def _restore_session_common(
        self,
        session_id: str,
        cwd: str,
        mcp_servers: list[Any] | None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Shared restore path for session/load and session/resume.

        Routes the ACP mcp_servers entries through the same converter as
        new_session, delegates to the session_restorer callback, and re-
        advertises the slash-command menu so the restored session behaves
        like a freshly created one. Client-declared browser ``_meta``
        (tabId / browserTask) is applied after a successful restore.
        """
        if self._session_restorer is None:
            raise RuntimeError("Session restore is not configured for this agent")
        mcp_configs = _mcp_servers_to_siada_configs(mcp_servers)
        if mcp_configs:
            logger.info("[acp] load/resume forwarding %d MCP server(s)", len(mcp_configs))
        result = self._session_restorer(session_id, cwd, mcp_configs or None)
        if inspect.isawaitable(result):
            await result
        self._sessions.add(session_id)
        self._session_cwd[session_id] = cwd
        self._register_browser_meta(session_id, meta)
        await self._advertise_commands(session_id)

    async def _replay_history(self, session_id: str) -> None:
        """Stream the restored session's history as session/update chunks.

        Maps the display messages from history_lister to user_message_chunk
        / agent_message_chunk updates (tool-call entries are already
        rendered to text by the shared formatter, matching the /resume
        ui/loadHistory presentation).
        """
        if self._conn is None or self._history_lister is None:
            return
        messages = self._history_lister(session_id)
        if inspect.isawaitable(messages):
            messages = await messages
        for message in messages:
            text = message.get("content") or ""
            if not text:
                continue
            update = (
                update_user_message_text(text)
                if message.get("role") == "user"
                else update_agent_message_text(text)
            )
            await self._conn.session_update(session_id, update)
        logger.info("[acp] Replayed %d history messages for session %s", len(messages), session_id)

    @staticmethod
    def _to_session_info(entry: dict[str, Any]) -> SessionInfo:
        """Build an ACP SessionInfo from a session_lister dict entry."""
        updated_at = entry.get("updated_at")
        title = entry.get("title")
        return SessionInfo(
            session_id=entry["session_id"],
            cwd=entry.get("cwd") or "",
            title=title if title else None,
            updated_at=updated_at if updated_at else None,
        )

    async def prompt(self, session_id: str, prompt: list[TextContentBlock], **_: Any) -> PromptResponse:
        if session_id not in self._sessions:
            self._sessions.add(session_id)
        if self._conn is None:
            raise RuntimeError("ACP connection has not been established")
        self._cancelled.discard(session_id)
        active_task = asyncio.current_task()
        if active_task is not None:
            self._active_prompts[session_id] = active_task
        try:
            text = "".join(block.text for block in prompt if isinstance(block, TextContentBlock))
            # Clients may send the user's actual message as the last of
            # several text blocks (e.g. an IM bridge prepends a
            # "[Context: ...]" context block). Slash-command matching must run
            # against that block alone, or the prefix defeats the leading-"/"
            # check and "/model" silently becomes a normal agent turn.
            command_text = next(
                (block.text.strip() for block in reversed(prompt)
                 if isinstance(block, TextContentBlock) and block.text.strip()),
                "",
            )
            if (
                self._command_matcher is not None
                and self._command_runner is not None
                and self._command_matcher(command_text)
            ):
                updates = self._command_runner(session_id, command_text)
            else:
                updates = self._turn_runner(session_id, text)
            if inspect.isawaitable(updates):
                updates = await updates
            if isinstance(updates, AsyncIterable):
                async for update in updates:
                    if session_id in self._cancelled:
                        return PromptResponse(stop_reason="cancelled")
                    await self._conn.session_update(session_id, update)
            else:
                for update in updates:
                    if session_id in self._cancelled:
                        return PromptResponse(stop_reason="cancelled")
                    await self._conn.session_update(session_id, update)
            return PromptResponse(stop_reason="end_turn")
        except asyncio.CancelledError:
            if session_id in self._cancelled:
                return PromptResponse(stop_reason="cancelled")
            raise
        except Exception:
            logger.exception("prompt() failed for session_id=%s", session_id)
            raise
        finally:
            self._active_prompts.pop(session_id, None)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Route extension notifications (e.g. ``trajectory_event``).

        Only enqueues into the runtime's managed task queue — the SDK reader
        loop never waits on permission prompts here.
        """
        if self._trajectory_handler is None:
            return
        if method == "trajectory_event" and isinstance(params, dict):
            logger.info(
                "[STEP 9] siada-agenthub received trajectory_event: tabId=%s events=%d",
                params.get("tabId"),
                len(params.get("events") or []),
            )
        try:
            self._trajectory_handler(method, params or {})
        except Exception:
            logger.exception("[acp] trajectory_handler failed for method=%s", method)

    async def cancel(self, session_id: str, **_: Any) -> None:
        self._cancelled.add(session_id)
        active_task = self._active_prompts.get(session_id)
        if active_task is not None:
            active_task.cancel()
        # Also abort an in-flight browser-skill takeover for this session.
        if self._canceller is not None:
            try:
                self._canceller(session_id)
            except Exception:
                logger.exception("[acp] canceller failed for session=%s", session_id)
