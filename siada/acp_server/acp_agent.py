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
from acp.helpers import SessionUpdate, update_available_commands
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AuthenticateResponse,
    AvailableCommand,
    ClientCapabilities,
    Implementation,
    ListSessionsResponse,
    SessionCapabilities,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionInfo,
    SessionListCapabilities,
    SetSessionConfigOptionResponse,
    TextContentBlock,
)

from siada import __version__
from siada.acp_server.auth import get_auth_methods

logger = logging.getLogger(__name__)

MODEL_CONFIG_OPTION_ID = "model"

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
        self._conn: Client | None = None
        self._sessions: set[str] = set()
        self._session_cwd: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._active_prompts: dict[str, asyncio.Task[PromptResponse]] = {}

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **_: Any,
    ) -> InitializeResponse:
        # Zed decides whether to render the "Authenticate" banner from
        # ClientCapabilities._meta["terminal-auth"]; the registry-required
        # type/args/env shape is always emitted regardless.
        meta = (client_capabilities.field_meta or {}) if client_capabilities else {}
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                session_capabilities=SessionCapabilities(list=SessionListCapabilities()),
            ),
            agent_info=Implementation(name="siada", title="Siada", version=__version__),
            auth_methods=get_auth_methods(meta.get("terminal-auth") is True),
        )

    async def authenticate(self, method_id: str, **_: Any) -> AuthenticateResponse | None:
        """Terminal Auth happens out-of-band via ``siada-cli --login``.

        Clients that call ``authenticate`` anyway get a successful no-op;
        credentials written by the terminal flow are picked up when the
        agent process is restarted.
        """
        logger.info("authenticate() called with method_id=%s (terminal auth is out-of-band)", method_id)
        return None

    async def new_session(self, cwd: str, **_: Any) -> NewSessionResponse:
        session_id = str(uuid4())
        try:
            if self._session_creator is not None:
                self._session_creator(session_id, cwd)
            self._sessions.add(session_id)
            self._session_cwd[session_id] = cwd
            await self._advertise_commands(session_id)
            return NewSessionResponse(
                session_id=session_id,
                modes=None,
                config_options=self._build_config_options(session_id),
            )
        except Exception:
            logger.exception("new_session() failed for cwd=%s", cwd)
            raise

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
        # Sessions only live in this process's memory, so this reports what
        # was created since the agent started (no cross-restart persistence).
        sessions = [
            SessionInfo(session_id=session_id, cwd=session_cwd)
            for session_id, session_cwd in self._session_cwd.items()
            if cwd is None or session_cwd == cwd
        ]
        return ListSessionsResponse(sessions=sessions, next_cursor=None)

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
            # "[上下文: ...]" context block). Slash-command matching must run
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

    async def cancel(self, session_id: str, **_: Any) -> None:
        self._cancelled.add(session_id)
        active_task = self._active_prompts.get(session_id)
        if active_task is not None:
            active_task.cancel()
