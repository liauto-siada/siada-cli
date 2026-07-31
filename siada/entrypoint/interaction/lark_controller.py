from __future__ import annotations

"""LarkController - Receives messages from transport and dispatches to SiadaRunner.

Supports both relay mode (RelayTransport) and direct mode (DirectTransport).
Runs as a background async loop inside the SiadaDaemon.

OOP design:
- LarkController: base class for direct mode (open-source default)
- RelayLarkController: subclass with relay-specific logic (login polling, credential forwarding)
- create_if_configured(): factory method returning the appropriate subclass

Delegated components (under siada/im/feishu/):
- LarkCardSender: card/message sending
- LarkStreamConsumer: stream event consumption
- LarkSlashCommandHandler: slash command parsing & execution
- LarkAccessControl: DM access policy
- ThreadSessionRouter: thread-based session routing
- GroupChatHandler: group chat processing
- IpcMessageHandler: IPC message queue management
- LarkSessionResolver: session cache, preload, resolution
- LarkAgentExecutor: agent execution, task lifecycle, ownership
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from siada.im.feishu.access_control import LarkAccessControl
from siada.im.feishu.card_sender import LarkCardSender
from siada.im.feishu.group_handler import GroupChatHandler
from siada.im.feishu.ipc_handler import IpcMessageHandler
from siada.im.feishu.lark_agent_executor import LarkAgentExecutor
from siada.im.feishu.lark_session_resolver import LarkSessionResolver
from siada.im.feishu.pending_history import DEFAULT_HISTORY_LIMIT
from siada.im.feishu.slash_command_handler import LarkSlashCommandHandler
from siada.im.feishu.stream_consumer import LarkStreamConsumer
from siada.im.feishu.thread_router import ThreadSessionRouter
from siada.im.feishu.verbose_config import VerboseConfig
from siada.im.feishu.utils import format_exception_for_user, get_default_workspace
from siada.entrypoint.interaction.im_controller import ImController
from siada.foundation.logging import setup_im_logger
from siada.im.models import IMMessage
from siada.im.transport.base import Transport
from siada.io.feishu_io import LarkIO

if TYPE_CHECKING:
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.session.ownership import SessionOwner
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.controller")

# Default idle window (seconds) after which a new P2P session is auto-created.
# 24 hours by default; configurable via lark.access.idle_session_timeout.
# A value <= 0 disables the idle-reset behavior entirely.
DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS = 86400

# ── Backward-compatible aliases for existing test imports ─────────
_format_exception_for_user = format_exception_for_user
_get_default_workspace = get_default_workspace
from siada.im.feishu.group_handler import GROUP_PAUSE_KEYWORDS  # noqa: E402, F401
from siada.im.feishu.utils import decode_embedded_bytes_literals as _decode_embedded_bytes_literals  # noqa: E402


def create_if_configured() -> Optional["LarkController"]:
    """Factory: load lark config and create the appropriate controller subclass."""
    from siada.im.config import load_im_config

    lark_config = load_im_config()
    if not lark_config:
        logger.debug("No lark config found in conf.yaml, skipping LarkController")
        lark_config = {}

    # Honour lark.enabled switch: when explicitly set to false, skip the
    # controller entirely so the daemon starts without a Lark connection.
    if not lark_config.get("lark", {}).get("enabled", True):
        logger.info("lark.enabled=false in conf.yaml, skipping LarkController")
        return None

    mode = lark_config.get("lark", {}).get("mode", "relay")
    if mode not in ("relay", "direct"):
        raise RuntimeError(
            f"Invalid lark mode '{mode}' in conf.yaml. Expected 'relay' or 'direct'."
        )

    if mode == "relay":
        try:
            from siada.internal.controller.relay_lark_controller import RelayLarkController
        except ImportError as e:
            raise RuntimeError(
                "Relay mode is not available: failed to import RelayLarkController. "
                "Currently only 'direct' mode is supported."
            ) from e
        return RelayLarkController(lark_config)

    direct_cfg = lark_config.get("lark", {}).get("direct", {})
    if not direct_cfg.get("app_id") or not direct_cfg.get("app_secret"):
        raise RuntimeError(
            "Direct mode requires lark.direct.app_id and lark.direct.app_secret "
            "to be set in conf.yaml."
        )
    return LarkController(lark_config)


class LarkController(ImController):
    """Controller that bridges Lark messages to SiadaRunner.

    Base implementation for direct mode (open-source default).

    Subclass extension points:
    - _create_transport(): override to provide a different transport
    - _on_transport_connected(): hook called after transport.connect() succeeds
    - _get_lark_client(): override for different Lark SDK credentials
    - _resolve_notify_email(): override for different email resolution
    """

    @classmethod
    def create_if_configured(cls) -> Optional["LarkController"]:
        return create_if_configured()

    def __init__(self, config: dict):
        logger.debug("[LarkController.__init__] BEGIN")
        super().__init__()
        setup_im_logger()

        self._config = config
        self._transport: Optional[Transport] = None
        self._lark_io: Optional[LarkIO] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Per-chat active task tracking (keyed by task_key = chat_id)
        from siada.im.feishu.lark_agent_executor import ActiveTaskEntry
        self._active_entries: dict[str, ActiveTaskEntry] = {}

        # Note: _last_activity_ts (per-chat idle tracking) is provided and
        # persisted by the ImController base class; it is reloaded from disk
        # during _init_routing() -> _load_routing() -> _load_last_activity().

        lark_cfg = config.get("lark", {})
        self._mode = lark_cfg.get("mode", "direct")
        self._agent_name = "coder"
        self._workspace = lark_cfg.get("workspace", None)

        # Set app_id for state isolation (direct mode reads from config)
        direct_cfg = lark_cfg.get("direct", {})
        self._app_id = direct_cfg.get("app_id") or None

        # Delegated components (some initialized lazily in _init_components_and_connect)
        self._card_sender: Optional[LarkCardSender] = None
        self._stream_consumer: Optional[LarkStreamConsumer] = None
        self._slash_handler: Optional[LarkSlashCommandHandler] = None
        self._access_control = LarkAccessControl(config, self._mode)
        self._verbose_config = VerboseConfig(self.platform_name)
        self._thread_router: Optional[ThreadSessionRouter] = None
        self._group_handler: Optional[GroupChatHandler] = None
        self._ipc_handler: Optional[IpcMessageHandler] = None

        # Composition components (initialized after routing is ready)
        self._session_resolver = LarkSessionResolver(self)
        self._agent_executor = LarkAgentExecutor(self)

        # Load routing table and migrate legacy sessions
        # (relay mode defers this to _on_transport_connected when app_id is known)
        self._init_routing()

        # Initialize thread router (depends on session_cache)
        self._thread_router = ThreadSessionRouter(
            get_session=self._session_cache.get,
            get_routed_session_id=self._get_routed_session_id,
        )
        logger.debug("[LarkController.__init__] END")

    # ── Routing initialization (override point) ───────────────────────

    def _init_routing(self) -> None:
        """Load routing tables and migrate legacy sessions.

        Direct mode: app_id is available from config, loads immediately.
        Relay mode overrides this to defer until _on_transport_connected
        when the Gateway provides the actual app_id.
        """
        self._load_routing()
        self._migrate_legacy_sessions()

    # ── Component initialization ──────────────────────────────────────

    def _resolve_history_limit(self) -> int:
        lark_cfg = self._config.get("lark", {})
        return lark_cfg.get("access", {}).get("history_limit", DEFAULT_HISTORY_LIMIT)

    def _resolve_idle_session_timeout(self) -> float:
        """Resolve the idle window (in seconds) for auto-creating a new P2P session.

        When a single chat stays silent longer than this threshold, the next
        message starts a fresh session and the previous one can be resumed via
        ``/resume <session_id>``. Configured via ``lark.access.idle_session_timeout``
        (seconds); a value <= 0 disables the behavior.
        """
        lark_cfg = self._config.get("lark", {})
        raw = lark_cfg.get("access", {}).get(
            "idle_session_timeout", DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS,
        )
        try:
            return float(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid lark.access.idle_session_timeout=%r, falling back to %s",
                raw, DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS,
            )
            return float(DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS)

    def _init_delegated_components(self) -> None:
        """Initialize delegated components that require _card_sender."""
        self._group_handler = GroupChatHandler(
            card_sender=self._card_sender,
            active_entries=self._active_entries,
            history_limit=self._resolve_history_limit(),
            check_group_access=self._access_control.check_group_access,
        )
        self._ipc_handler = IpcMessageHandler(
            card_sender=self._card_sender,
            get_routed_session_id=self._get_routed_session_id,
            get_session=self._session_resolver.get_or_load,
            is_single_chat=self._is_single_chat,
            resolve_notify_email=self._resolve_notify_email,
            resolve_preferred_language=self._resolve_preferred_language,
        )

    # ── Transport creation (override point) ──────────────────────────

    def _create_transport(self) -> Transport:
        from siada.im.transport.direct import DirectTransport, DirectTransportConfig
        from siada.im.adapter.feishu import LarkDirectAdapter

        lark_cfg = self._config.get("lark", {})
        direct_cfg = lark_cfg.get("direct", {})
        notify_email = self._resolve_notify_email()
        config = DirectTransportConfig(
            app_id=direct_cfg.get("app_id", ""),
            app_secret=direct_cfg.get("app_secret", ""),
            domain=direct_cfg.get("domain", "lark"),
            http_timeout_ms=direct_cfg.get("http_timeout_ms", 30000),
            media_max_mb=direct_cfg.get("media_max_mb", 30),
            resolve_sender_names=direct_cfg.get("resolve_sender_names", True),
            notify_email=notify_email,
            preferred_language=self._resolve_preferred_language(),
        )
        adapter = LarkDirectAdapter(config)
        return DirectTransport(config, adapter)

    async def _on_transport_connected(self) -> None:
        """Hook called after transport.connect() succeeds."""
        pass

    # ── Start / connect ──────────────────────────────────────────────

    async def _init_components_and_connect(self) -> None:
        self._transport = self._create_transport()
        self._lark_io = LarkIO(transport=self._transport)
        self._card_sender = LarkCardSender(
            config=self._config, mode=self._mode, transport=self._transport,
        )
        self._card_sender.create_typing_indicator()
        self._stream_consumer = LarkStreamConsumer(
            card_sender=self._card_sender, mode=self._mode,
        )
        self._slash_handler = LarkSlashCommandHandler(
            lark_io=self._lark_io, card_sender=self._card_sender,
            verbose_config=self._verbose_config,
            controller=self,
        )
        self._init_delegated_components()

        logger.info("Connecting transport...")
        await self._transport.connect()
        await self._on_transport_connected()
        await self._bootstrap_routing_from_email()
        self._session_resolver.preload_routed_sessions()

        # Register MCP configuration with the global manager so that agent
        # runs dispatched by this controller pick up MCP servers from
        # conf.yaml. Mirrors what siadahub._build_session() does for the
        # CLI path. Without this call ``_mcp_manager_service.has_config()``
        # stays False and ``siada_runner`` silently skips MCP setup.
        self._register_mcp_config()

        self._running = True
        self._task = asyncio.create_task(self._message_loop())
        logger.info("LarkController started in %s mode", self._mode)

    def _register_mcp_config(self) -> None:
        """Register MCP configuration into the shared global manager.

        Idempotent and best-effort: any failure is logged but never
        propagated, so MCP misconfiguration cannot prevent the IM
        controller from starting.
        """
        try:
            from siada.services.mcp.setup import setup_mcp_config

            setup_mcp_config(self._build_running_config())
        except Exception as e:
            logger.warning(
                "Failed to register MCP config for LarkController: %s",
                e,
                exc_info=True,
            )


    async def start(self) -> None:
        if self._running:
            logger.warning("LarkController already running")
            return
        logger.info("Starting LarkController (mode=%s)...", self._mode)
        try:
            await self._init_components_and_connect()
        except Exception as e:
            logger.error("Failed to connect transport: %s", e, exc_info=True)
            raise

    # ── Message loop ─────────────────────────────────────────────────

    async def _message_loop(self) -> None:
        try:
            async for msg in self._transport.receive():
                if not self._running:
                    break
                logger.info(
                    "Received IM message: request_id=%s, chat_id=%s, chat_type=%s, "
                    "sender_open_id=%s, content=%r",
                    msg.request_id, msg.chat_id, msg.chat_type,
                    msg.sender_open_id, msg.content[:100],
                )
                try:
                    await self._handle_message(msg)
                except Exception as e:
                    logger.error("Error handling message %s: %s", msg.request_id, e, exc_info=True)
                    try:
                        await self._card_sender.send_im(
                            msg.request_id, msg.chat_id,
                            f"❌ Agent execution failed: {format_exception_for_user(e)}",
                            content_type="text",
                        )
                    except Exception:
                        pass
                    if hasattr(self._transport, "send_ack"):
                        await self._transport.send_ack(msg.request_id)
        except asyncio.CancelledError:
            logger.info("Message loop cancelled")
        except Exception as e:
            logger.error("Message loop error: %s", e, exc_info=True)

    # ── Email bootstrap (override points) ─────────────────────────────

    def _get_lark_client(self):
        """Create a lark-oapi Client. Override in RelayLarkController."""
        import lark_oapi as lark

        lark_cfg = self._config.get("lark", {})
        direct_cfg = lark_cfg.get("direct", {})
        app_id = direct_cfg.get("app_id", "")
        app_secret = direct_cfg.get("app_secret", "")
        if not app_id or not app_secret:
            raise RuntimeError("app_id or app_secret not found in lark.direct config.")

        domain_str = direct_cfg.get("domain", "lark")
        if domain_str == "lark":
            domain = lark.LARK_DOMAIN
        elif domain_str in ("feishu", "lark_cn"):
            domain = lark.FEISHU_DOMAIN
        else:
            domain = domain_str.rstrip("/")

        return lark.Client.builder().app_id(app_id).app_secret(app_secret).domain(domain).build()

    async def _batch_get_user_open_id(self, email: str) -> Optional[str]:
        """Get user open_id from email via Lark contact API."""
        try:
            from lark_oapi.api.contact.v3 import (
                BatchGetIdUserRequest, BatchGetIdUserRequestBody, BatchGetIdUserResponse,
            )
            client = self._get_lark_client()
            request = (
                BatchGetIdUserRequest.builder()
                .user_id_type("open_id")
                .request_body(
                    BatchGetIdUserRequestBody.builder()
                    .emails([email]).include_resigned(False).build()
                ).build()
            )
            response: BatchGetIdUserResponse = await asyncio.to_thread(
                client.contact.v3.user.batch_get_id, request,
            )
            if not response.success():
                logger.error("batch_get_id failed: code=%s, msg=%s", response.code, response.msg)
                return None
            user_list = response.data.user_list if response.data else []
            if not user_list:
                return None
            open_id = user_list[0].user_id
            if open_id:
                logger.info("Resolved open_id=%s from email=%s", open_id, email)
            return open_id
        except Exception as e:
            logger.warning("Failed to resolve open_id from email=%s: %s", email, e)
            return None

    def _find_sessions_by_open_id(self, open_id: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        try:
            workspace = self._workspace or get_default_workspace()
            from siada.utils import DirectoryUtils
            sessions_dir = Path(DirectoryUtils.get_global_sessions_dir(workspace))
            if not sessions_dir.exists():
                return results
            prefix = f"feishu_direct_{open_id}_"
            for d in sessions_dir.iterdir():
                if d.is_dir() and d.name.startswith(prefix):
                    chat_id = d.name[len(prefix):]
                    if chat_id:
                        results.append((chat_id, d.name))
        except Exception as e:
            logger.debug("Error scanning session dirs for open_id=%s: %s", open_id, e)
        return results

    async def _bootstrap_routing_from_email(self) -> None:
        """Bootstrap open_id index from email -> open_id resolution."""
        if self._routing.open_ids:
            return
        email = self._resolve_notify_email()
        if not email:
            return
        open_id = await self._batch_get_user_open_id(email)
        if not open_id:
            return

        from siada.session.session_manager import RunningSessionManager
        from siada.foundation.id_generator import generate_session_id
        session_id = generate_session_id()
        running_config = self._build_running_config()
        session = RunningSessionManager.create_session(
            siada_config=running_config, session_id=session_id,
        )
        self._mark_session_source(session_id, running_config.workspace)
        self._session_cache[session_id] = session
        self._routing.set_open_id(open_id, session_id)
        self._persist_routing()
        logger.info(
            "Bootstrapped open_id from email: open_id=%s, session_id=%s",
            open_id, session_id,
        )

    def _resolve_notify_email(self) -> Optional[str]:
        """Override in subclass for different email resolution."""
        return self._config.get("lark", {}).get("notify_email")

    def _resolve_preferred_language(self) -> Optional[str]:
        """Resolve preferred language from global configuration."""
        try:
            from siada.config.config_loader import load_conf

            conf = load_conf()
            return conf.preferred_language if conf else None
        except Exception as exc:
            logger.debug("Failed to resolve preferred language for IPC card: %s", exc)
            return None

    # ── Config building ──────────────────────────────────────────────

    def _build_running_config(self) -> "RunningConfig":
        from siada.entrypoint.interaction.running_config import RunningConfig
        from siada.config.config_loader import load_conf
        from siada.entrypoint.helpers.model_setup import get_config_from_conf

        conf = load_conf()
        model_config = get_config_from_conf(self._lark_io, conf)
        workspace = self._workspace or get_default_workspace()

        return RunningConfig(
            llm_config=model_config, io=self._lark_io, workspace=workspace,
            agent_name=self._agent_name, interactive=True, console_output=False,
            mcp_config=conf.mcp_config if conf else None,
            compaction_strategy=conf.compaction_strategy if conf else None,
            memory_enabled=conf.memory_config.enabled if conf else True,
        )

    # ── Message handling ─────────────────────────────────────────────

    def _resolve_task_key(self, msg: IMMessage) -> str:
        return msg.chat_id

    async def _handle_message(self, msg: IMMessage) -> None:
        """Handle a single incoming message (full pipeline)."""
        # Step 1 & 2: access-control gate + group pre-processing
        if msg.chat_type == "p2p":
            if not await self._gate_p2p_message(msg):
                return
        elif msg.chat_type == "group":
            result = await self._group_handler.gate_group_message(
                msg, self._agent_executor.cancel_active_task,
            )
            if result is None:
                return
            msg = result
        else:
            logger.debug("Ignoring message with unknown chat_type=%s", msg.chat_type)
            return

        running_config = self._build_running_config()
        task_key = self._resolve_task_key(msg)
        logger.info(
            "_handle_message: task_key=%s, chat_type=%s, chat_id=%s",
            task_key, msg.chat_type, msg.chat_id,
        )

        # Step 3a: slash command interception
        if LarkSlashCommandHandler.is_slash_command(msg.content):
            # Slash commands (e.g. /resume) count as user activity: refresh the
            # idle clock so the next message isn't treated as a return-from-idle
            # and does not spuriously reset a session the user just switched to.
            self._last_activity_ts[msg.chat_id] = time.time()
            self._persist_last_activity()
            current_session = self._session_resolver.get_or_create(msg, running_config)
            if await self._handle_slash_command(msg, current_session, running_config, task_key):
                return

        # Step 3a+: group-specific enrichment (after slash check, before agent)
        if msg.chat_type == "group":
            msg = self._group_handler.enrich_for_agent(msg)
            logger.info(
                "Group message enriched: chat_id=%s, content_len=%d, content=%r",
                msg.chat_id, len(msg.content) if msg.content else 0, msg.content,
            )

        # Step 3b: cancel previous running task (P2P only)
        # Must happen before session resolution to ensure the old task stops
        # writing to session, so resolve_session reads a clean state.
        if msg.chat_type == "p2p":
            await self._agent_executor.cancel_active_task(task_key)

        # Step 3c: session resolution
        session, msg = await self._session_resolver.resolve_session(msg, running_config)
        logger.info(
            "_handle_message: session resolved, session_id=%s",
            session.session_id if session else None,
        )

        # Step 3d: final session guard
        if session is None:
            logger.error("Failed to resolve session for chat_id=%s", msg.chat_id)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "❌ Failed to resolve session. Please try again or use /clear.",
                content_type="text",
            )
            return

        # Step 4: dispatch agent task
        self._agent_executor.dispatch_task(msg, session, task_key)

    # ── P2P message gate ─────────────────────────────────────────────

    async def _gate_p2p_message(self, msg: IMMessage) -> bool:
        if not self._access_control.check_dm_access(msg):
            pair_key = LarkAccessControl.resolve_pair_key(msg)
            logger.warning("Blocked unauthorized DM: pair_key=%s, chat_id=%s", pair_key, msg.chat_id)
            await self._send_access_denied(msg)
            return False
        return True

    async def _send_access_denied(self, msg: IMMessage) -> None:
        pair_key = LarkAccessControl.resolve_pair_key(msg)
        text = f"⚠️ Access denied. Please contact the admin.\n\nYour pair key: {pair_key}"
        await self._card_sender.send_im(msg.request_id, msg.chat_id, text, content_type="text")

    # ── Slash command handling ────────────────────────────────────────

    async def _handle_slash_command(
        self, msg: IMMessage, session: Optional["RunningSession"],
        running_config: "RunningConfig", task_key: str,
    ) -> bool:
        # /btw is a read-only side question that must NOT interrupt the main
        # agent flow, so we deliberately skip cancelling the active task for it.
        # All other slash commands cancel the running task first (their effect
        # — clear/model/help/etc. — assumes the main turn is stopped).
        cmd_name = msg.content.strip().split(None, 1)[0].lstrip("/")
        if cmd_name != "btw":
            await self._agent_executor.cancel_active_task(task_key)
        try:
            self._lark_io.set_context(msg.request_id, msg.chat_id)
            if session is None:
                await self._card_sender.send_im(
                    msg.request_id, msg.chat_id,
                    "❌ No active session. Please send a message first.",
                    content_type="text",
                )
                return True
            return await self._slash_handler.handle(msg, session)
        except Exception as e:
            logger.error("Slash command error: %s", e, exc_info=True)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"❌ Command failed: {format_exception_for_user(e)}",
                content_type="text",
            )
            return True

    # ── Session disk operations ──────────────────────────────────────

    def _get_session_dir(self, session_id: str, workspace: str) -> Path:
        from siada.utils import DirectoryUtils
        return Path(DirectoryUtils.get_global_sessions_dir(workspace)) / session_id

    # ── IPC pending message queue ─────────────────────────────────────

    def _has_active_p2p_tasks(self) -> bool:
        """Check if any active P2P (single chat) tasks are running.

        Only P2P tasks are relevant for IPC drain gating, because IPC
        messages are delivered to P2P chats only (not group chats).
        """
        return any(
            self._is_single_chat(task_key) and entry.is_running
            for task_key, entry in self._active_entries.items()
        )

    async def enqueue_ipc_message(
        self, content: str, content_type: str = "markdown",
        source_session_id: str | None = None,
        *,
        header_title: str | None = None,
    ) -> dict:
        result = await self._ipc_handler.enqueue(
            content, content_type, source_session_id,
            header_title=header_title,
        )
        # Only gate on P2P tasks — group tasks don't affect IPC delivery
        if not self._has_active_p2p_tasks():
            await self._drain_pending_ipc_messages()
            result["status"] = "sent"
            result["queue_size"] = 0
        return result

    async def _drain_pending_ipc_messages(self) -> None:
        # Pass routing at drain time so targets are resolved with latest state.
        #
        # Concurrency note: multiple P2P agent tasks may finish near-simultaneously,
        # each triggering asyncio.ensure_future(_drain_pending_ipc_messages()) from
        # _on_task_done. This is safe under asyncio's single-threaded model because:
        #   - _pending_messages[:] + clear() is synchronous (no await in between)
        #   - Worst case: a redundant drain runs on an empty queue (no-op)
        #
        # If stricter control is desired, add an asyncio.Lock:
        #   self._drain_lock = asyncio.Lock()  # in __init__
        #   if self._drain_lock.locked():
        #       return  # skip redundant drain
        #   async with self._drain_lock:
        #       await self._ipc_handler.drain_pending(routing=self._routing)
        await self._ipc_handler.drain_pending(routing=self._routing)

    def _resolve_drain_chat_id(self) -> str | None:
        if self._ipc_handler:
            return self._ipc_handler._resolve_drain_chat_id(self._routing.chats)
        single_chats = [c for c in self._routing.chats if self._is_single_chat(c)]
        return single_chats[0] if len(single_chats) == 1 else None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def stop(self) -> None:
        logger.info("Stopping LarkController...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._transport:
            await self._transport.disconnect()
            self._transport = None
        logger.info("LarkController stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def owner_type(self) -> "SessionOwner":
        from siada.session.ownership import SessionOwner
        return SessionOwner.LARK

    @property
    def workspace(self) -> Optional[str]:
        return self._workspace

    @property
    def platform_name(self) -> str:
        return "lark"
