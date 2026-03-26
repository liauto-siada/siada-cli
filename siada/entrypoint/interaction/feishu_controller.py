"""LarkController - Receives messages from transport and dispatches to SiadaRunner.

Supports both relay mode (RelayTransport) and direct mode (DirectTransport).
Runs as a background async loop inside the SiadaDaemon.

Stream event consumption mirrors ConversationTurn.output_stream_content:
- Thinking (reasoning summary) -> sent as a collapsed section
- Answer (text delta) -> sent as streaming markdown
- Tool calls -> sent with name + formatted arguments
- Tool results -> sent after each tool execution

OOP design:
- LarkController: base class for direct mode (open-source default)
- RelayLarkController: subclass with relay-specific logic (login polling, credential forwarding)
- create_if_configured(): factory method returning the appropriate subclass
"""

import ast
import asyncio
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from agents import RunResultStreaming

from siada.im.feishu.card_sender import LarkCardSender
from siada.im.feishu.stream_consumer import LarkStreamConsumer
from siada.entrypoint.interaction.im_controller import ImController
from siada.foundation.logging import setup_im_logger
from siada.im.models import IMMessage
from siada.im.transport.base import Transport
from siada.io.feishu_io import LarkIO
from siada.support.slash_commands import SlashCommands, SwitchEvent

if TYPE_CHECKING:
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.session.ownership import SessionOwner
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.controller")

# Match bytes literals like b'...' or b"..." in exception messages.
# Uses non-VERBOSE mode so spaces are matched literally.
_BYTES_LITERAL_PATTERN = re.compile(
    r"""(?<![\w])b(?P<quote>['"])(?P<body>(?:\\.|(?!(?P=quote)).)*)(?P=quote)"""
)


def create_if_configured() -> Optional["LarkController"]:
    """Factory: load lark config from conf.yaml and create the appropriate controller subclass.

    Returns:
        A LarkController (direct mode) or RelayLarkController (relay mode),
        based on the lark.mode setting in conf.yaml.

    Raises:
        RuntimeError: If config is missing or mode is invalid.
    """
    from siada.im.config import load_im_config

    lark_config = load_im_config()
    if not lark_config:
        # No lark section in conf.yaml - not configured, skip silently
        logger.debug("No lark config found in conf.yaml, skipping LarkController")
        lark_config = {}

    mode = lark_config.get("lark", {}).get("mode", "relay")
    if mode not in ("relay", "direct"):
        raise RuntimeError(
            f"Invalid lark mode '{mode}' in conf.yaml. "
            f"Expected 'relay' or 'direct'."
        )

    if mode == "relay":
        try:
            from siada.internal.controller.relay_feishu_controller import RelayLarkController
        except ImportError as e:
            raise RuntimeError(
                "Relay mode is not available: failed to import RelayLarkController. "
                "Currently only 'direct' mode is supported. "
                "Please set lark.mode to 'direct' in conf.yaml."
            ) from e
        return RelayLarkController(lark_config)

    # Validate required credentials for direct mode
    direct_cfg = lark_config.get("lark", {}).get("direct", {})
    app_id = direct_cfg.get("app_id", "")
    app_secret = direct_cfg.get("app_secret", "")
    if not app_id or not app_secret:
        raise RuntimeError(
            "Direct mode requires lark.direct.app_id and lark.direct.app_secret "
            "to be set in conf.yaml. Please configure them before starting."
        )

    return LarkController(lark_config)


class LarkController(ImController):
    """Controller that bridges Lark messages to SiadaRunner.

    Base implementation for direct mode (open-source default).
    Uses DirectTransport (Lark WS SDK) to connect directly to Lark.

    Session persistence: each chat_id maps to a persistent session.
    If a task is already running for a chat_id, it is cancelled before starting a new one.

    Subclass extension points:
    - _create_transport(): override to provide a different transport
    - _on_transport_connected(): hook called after transport.connect() succeeds
    """

    # Keep the legacy factory for backward compatibility
    @classmethod
    def create_if_configured(cls) -> Optional["LarkController"]:
        """Load lark config from conf.yaml and create controller if properly configured.

        Delegates to the module-level factory function which returns
        the appropriate subclass based on mode.
        """
        return create_if_configured()

    def __init__(self, config: dict):
        """Initialize with lark config dict loaded from conf.yaml."""
        # Setup IM logging to im.log file
        setup_im_logger()

        self._config = config
        self._transport: Optional[Transport] = None
        self._lark_io: Optional[LarkIO] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Per-chat persistent sessions and active task tracking
        self._active_tasks: dict[str, asyncio.Task] = {}  # chat_id -> running asyncio.Task
        self._active_results: dict[str, RunResultStreaming] = {}  # chat_id -> streaming result
        self._active_sessions: dict[str, "RunningSession"] = {}  # chat_id -> session for interrupt handling
        self._persistent_sessions: dict[str, "RunningSession"] = {}  # chat_id -> cached session with preserved state

        lark_cfg = config.get("lark", {})
        self._mode = lark_cfg.get("mode", "direct")
        # IM mode defaults to "coder" agent - no longer configurable via config
        self._agent_name = "coder"
        self._workspace = lark_cfg.get("workspace", None)

        # Delegated components (initialized in start())
        self._card_sender: Optional[LarkCardSender] = None
        self._stream_consumer: Optional[LarkStreamConsumer] = None

        # Slash command handler for IM mode
        self._slash_commands: Optional[SlashCommands] = None

    # ── Transport creation (override point) ──────────────────────────

    def _create_transport(self) -> Transport:
        """Create the transport for this controller mode.

        Base implementation creates a DirectTransport for Lark WS SDK.
        Override in subclasses for different transport types.
        """
        from siada.im.transport.direct import DirectTransport, DirectTransportConfig
        from siada.im.adapter.feishu import LarkDirectAdapter

        lark_cfg = self._config.get("lark", {})
        direct_cfg = lark_cfg.get("direct", {})
        config = DirectTransportConfig(
            app_id=direct_cfg.get("app_id", ""),
            app_secret=direct_cfg.get("app_secret", ""),
            domain=direct_cfg.get("domain", "lark"),
            encrypt_key=direct_cfg.get("encrypt_key"),
            http_timeout_ms=direct_cfg.get("http_timeout_ms", 30000),
            media_max_mb=direct_cfg.get("media_max_mb", 30),
            resolve_sender_names=direct_cfg.get("resolve_sender_names", True),
        )
        adapter = LarkDirectAdapter(config)
        return DirectTransport(config, adapter)

    # ── Connection hooks (override points) ───────────────────────────

    async def _on_transport_connected(self) -> None:
        """Hook called after transport.connect() succeeds.

        Override in subclasses to perform post-connection setup
        (e.g. forwarding credentials from gateway).
        """
        pass

    # ── Start / connect ──────────────────────────────────────────────

    async def _init_components_and_connect(self) -> None:
        """Create transport, initialize components, connect, and start message loop.

        Shared by start() and deferred-start paths (e.g. relay login polling).
        """
        self._transport = self._create_transport()
        self._lark_io = LarkIO(transport=self._transport)

        # Initialize delegated components
        self._card_sender = LarkCardSender(
            config=self._config, mode=self._mode, transport=self._transport,
        )
        self._card_sender.create_typing_indicator()
        self._stream_consumer = LarkStreamConsumer(
            card_sender=self._card_sender, mode=self._mode,
        )

        logger.info("Connecting transport...")
        await self._transport.connect()

        # Subclass hook for post-connection setup
        await self._on_transport_connected()

        self._running = True
        self._task = asyncio.create_task(self._message_loop())
        logger.info(f"LarkController started in {self._mode} mode")

    async def start(self) -> None:
        """Connect transport and start the message processing loop."""
        if self._running:
            logger.warning("LarkController already running")
            return

        logger.info(f"Starting LarkController (mode={self._mode})...")

        try:
            await self._init_components_and_connect()
        except Exception as e:
            logger.error(f"Failed to connect transport: {e}", exc_info=True)
            raise

    # ── Message loop ─────────────────────────────────────────────────

    async def _message_loop(self) -> None:
        """Main loop: consume messages from transport and execute agent."""
        try:
            async for msg in self._transport.receive():
                if not self._running:
                    break
                logger.info(
                    f"Received IM message: request_id={msg.request_id}, "
                    f"user_id={msg.user_id}, chat_id={msg.chat_id}, "
                    f"chat_type={msg.chat_type}, content_type={msg.content_type}, "
                    f"content={msg.content[:100]!r}"
                )
                try:
                    await self._handle_message(msg)
                except Exception as e:
                    logger.error(f"Error handling message {msg.request_id}: {e}", exc_info=True)
                    try:
                        await self._card_sender.send_im(
                            msg.request_id,
                            msg.chat_id,
                            f"❌ Agent execution failed: {_format_exception_for_user(e)}",
                            content_type="text",
                        )
                    except Exception:
                        pass
                    if hasattr(self._transport, "send_ack"):
                        await self._transport.send_ack(msg.request_id)
        except asyncio.CancelledError:
            logger.info("Message loop cancelled")
        except Exception as e:
            logger.error(f"Message loop error: {e}", exc_info=True)

    # ── Task cancellation & interrupt ────────────────────────────────

    async def _cancel_active_task(self, chat_id: str) -> None:
        """Cancel the currently running task for a chat_id, if any.

        Mirrors ConversationTurn interrupt handling:
        1. Cancel the RunResultStreaming
        2. Cancel the asyncio.Task
        3. Add interrupt marker to session history
        """
        # Remove typing indicator on cancel
        await self._card_sender.remove_typing(chat_id)

        # Cancel the streaming result first (like current_result.cancel() in ConversationTurn)
        result = self._active_results.pop(chat_id, None)
        if result:
            try:
                result.cancel()
                logger.info(f"Cancelled streaming result for chat_id={chat_id}")
            except Exception as e:
                logger.debug(f"Error cancelling streaming result: {e}")

        # Cancel the asyncio task
        task = self._active_tasks.pop(chat_id, None)
        if task and not task.done():
            logger.info(f"Cancelling active task for chat_id={chat_id}")
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            logger.info(f"Active task cancelled for chat_id={chat_id}")

        # Add interrupt marker to session history (mirrors ConversationTurn.handle_interrupt)
        session = self._active_sessions.pop(chat_id, None)
        if session and session.openai_session:
            try:
                await self._add_interrupt_marker(session)
            except Exception as e:
                logger.debug(f"Error adding interrupt marker: {e}")

    async def _add_interrupt_marker(self, session: "RunningSession") -> None:
        """Add interrupt note to session history, mirroring ConversationTurn.handle_interrupt."""
        from agents.models.chatcmpl_converter import Converter

        history = await session.openai_session.get_items()
        if not history:
            return

        last_item = history[-1]
        interrupt_note = {
            "role": "user",
            "content": "Note: This Conversation Was Interrupted By User",
        }

        should_add_note = any(
            [
                Converter.maybe_input_message(last_item),
                Converter.maybe_easy_input_message(last_item),
                Converter.maybe_function_tool_call_output(last_item),
            ]
        )

        if should_add_note:
            await session.openai_session.add_items([interrupt_note])
            logger.info(f"Added interrupt marker to session {session.session_id}")

    # ── Session management ───────────────────────────────────────────

    def _build_session_id(self, msg: "IMMessage") -> str:
        """Build session_id in format: lark_{mode}_{uid}_{chat_id}.

        Prefers open_id (ou_xxx) over user_id for consistent identity.
        """
        uid = msg.sender_open_id or msg.user_id or "unknown"
        return f"lark_{self._mode}_{uid}_{msg.chat_id}"

    def _get_or_create_session(
        self, msg: "IMMessage", running_config: "RunningConfig"
    ) -> "RunningSession":
        """Get existing persistent session for chat_id or create a new one.

        Session ID format: lark_{mode}_{en_name}_{chat_id}
        Each Lark chat has exactly one persistent conversation thread stored on disk.

        In Lark mode, the session's in-memory state (context_vars, current_agent,
        task_message_state, etc.) is preserved across messages by caching sessions
        in _persistent_sessions. Only the FileSession (openai_session) and config
        are refreshed; the SessionState is carried over.
        """
        from siada.session.session_manager import RunningSessionManager

        chat_id = msg.chat_id
        session_id = self._build_session_id(msg)

        # Check if we already have a cached session with preserved state
        cached_session = self._persistent_sessions.get(chat_id)
        if cached_session is not None:
            logger.info(f"Reusing cached session with preserved state for chat_id={chat_id}, session_id={session_id}")
            cached_session.siada_config = running_config
            new_session = RunningSessionManager.create_session(
                siada_config=running_config,
                session_id=session_id,
            )
            cached_session.state.openai_session = new_session.state.openai_session
            return cached_session

        # No cached session - create brand new one
        logger.info(f"Creating new session for chat_id={chat_id}, session_id={session_id}")
        session = RunningSessionManager.create_session(
            siada_config=running_config,
            session_id=session_id,
        )
        self._persistent_sessions[chat_id] = session
        return session

    # ── Access control ───────────────────────────────────────────────

    def _resolve_pair_key(self, msg: IMMessage) -> str:
        """Resolve the pair key for access control matching.

        Prefer open_id (ou_xxx), fallback to user_id.
        """
        return msg.sender_open_id or msg.user_id or ""

    def _check_dm_access(self, msg: IMMessage) -> bool:
        """Check if a DM sender is allowed based on access.dm_policy config.

        In relay mode, access control is handled by the Gateway server,
        so this always returns True.

        Returns True if allowed, False if blocked.
        """
        # Relay mode: access control is handled server-side by the Gateway
        if self._mode == "relay":
            return True

        access_cfg = self._config.get("lark", {}).get("access", {})
        dm_policy = access_cfg.get("dm_policy", "open")

        if dm_policy == "open":
            return True

        # allowlist mode
        allow_from = set(access_cfg.get("allow_from", []))
        if not allow_from:
            logger.warning("dm_policy=allowlist but allow_from is empty, blocking all DMs")
            return False

        if msg.user_id in allow_from:
            return True
        if msg.sender_open_id and msg.sender_open_id in allow_from:
            return True

        return False

    async def _send_access_denied(self, msg: IMMessage) -> None:
        """Send access denied reply showing the user's pair key."""
        pair_key = self._resolve_pair_key(msg)
        text = (
            "⚠️ Access denied. Please contact the admin to grant access.\n\n"
            f"Your pair key: {pair_key}"
        )
        await self._card_sender.send_im(msg.request_id, msg.chat_id, text, content_type="text")

    # ── Slash commands ───────────────────────────────────────────────

    # Blacklist of commands not supported in Lark IM mode.
    # These are CLI-only commands (interactive editors, terminal UI, process lifecycle, etc.)
    # that don't make sense in IM context.
    # Allowed commands are dynamically derived: all registered commands minus this blacklist.
    _IM_BLOCKED_COMMANDS = {
        "agent", "compare", "configure",
        "edit", "editor", "exit", "init", "issue-fix",
        "lark-auth", "logout",
        "map", "map-refresh",
        "migrate-detect", "migrate-import",
        "models", "multiline-mode",
        "plugin", "quit",
        "restore", "resume", "run",
        "shell", "task-list", "undo",
    }

    def _is_slash_command(self, content: str) -> bool:
        """Check if message content is a slash command."""
        return content.strip().startswith("/")

    def _get_slash_commands(self) -> SlashCommands:
        """Lazily create SlashCommands instance for IM mode."""
        if self._slash_commands is None:
            self._slash_commands = SlashCommands(io=self._lark_io)
        return self._slash_commands

    def _get_im_allowed_commands(self) -> set[str]:
        """Dynamically compute IM-allowed commands by excluding blocked ones.

        Fetches all registered commands from SlashCommands.get_commands()
        and removes those in the _IM_BLOCKED_COMMANDS blacklist.
        """
        slash_cmds = self._get_slash_commands()
        # get_commands returns ["/cmd-name", ...], strip the leading "/"
        all_commands = {cmd.lstrip("/") for cmd in slash_cmds.get_commands()}
        return all_commands - self._IM_BLOCKED_COMMANDS

    def _build_im_help(self) -> str:
        """Build help text showing only IM-allowed commands with descriptions."""
        slash_cmds = self._get_slash_commands()
        allowed = self._get_im_allowed_commands()
        commands = sorted(f"/{name}" for name in allowed)
        pad = max(len(cmd) for cmd in commands)
        fmt = "{cmd:" + str(pad) + "}"

        help_lines = []
        for cmd in commands:
            cmd_method_name = f"cmd_{cmd[1:]}".replace("-", "_")
            cmd_method = getattr(slash_cmds, cmd_method_name, None)
            padded = fmt.format(cmd=cmd)
            if cmd_method and cmd_method.__doc__:
                help_lines.append(f"{padded} {cmd_method.__doc__}")
            else:
                help_lines.append(f"{padded} No description available.")

        return "\n".join(help_lines)

    async def _handle_slash_command(self, msg: IMMessage, session: "RunningSession") -> bool:
        """Handle a slash command message. Returns True if handled, False otherwise.

        Intercepts /xxx messages, runs the command via SlashCommands, and sends
        the result back to the user. Handles SwitchEvent for /clear, /model, /init etc.
        """
        content = msg.content.strip()
        if not content.startswith("/"):
            return False

        parts = content.split(None, 1)
        cmd_word = parts[0]
        cmd_name = cmd_word.lstrip("/")

        if cmd_name not in self._get_im_allowed_commands():
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"⚠️ Command `/{cmd_name}` is not supported in IM mode.\n\n"
                f"Type `/help` to see available commands.",
                content_type="text",
            )
            return True

        # Intercept /help to only show IM-allowed commands
        if cmd_name == "help":
            help_text = self._build_im_help()
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id, help_text, content_type="text",
            )
            return True

        slash_cmds = self._get_slash_commands()

        # Capture IO output by temporarily buffering print_info/print_error
        output_lines: list[str] = []
        original_print_info = self._lark_io.print_info
        original_print_error = self._lark_io.print_error

        def _capture_info(text, *args, **kwargs):
            output_lines.append(text)

        def _capture_error(text, *args, **kwargs):
            output_lines.append(f"❌ {text}")

        self._lark_io.print_info = _capture_info
        self._lark_io.print_error = _capture_error

        try:
            result = slash_cmds.run(session, content)
        except Exception as e:
            logger.error(f"Slash command error: {e}", exc_info=True)
            output_lines.append(f"❌ Command failed: {_format_exception_for_user(e)}")
            result = None
        finally:
            self._lark_io.print_info = original_print_info
            self._lark_io.print_error = original_print_error

        if output_lines:
            combined = "\n".join(output_lines)
            if len(combined) > 4000:
                combined = combined[:3997] + "..."
            await self._card_sender.send_im(msg.request_id, msg.chat_id, combined, content_type="text")

        if isinstance(result, SwitchEvent):
            await self._handle_switch_event(result, msg, session)

        return True

    async def _handle_switch_event(
        self, event: SwitchEvent, msg: IMMessage, session: "RunningSession"
    ) -> None:
        """Handle SwitchEvent returned from slash commands."""
        kwargs = event.kwargs

        if kwargs.get("clear"):
            # Clear in-memory cached session
            self._persistent_sessions.pop(msg.chat_id, None)
            # Clear disk history so FileSession won't restore old conversation
            self._clear_session_disk_history(msg, session)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "✅ Session cleared. Starting fresh.",
                content_type="text",
            )

        elif kwargs.get("model"):
            model_name = kwargs["model"]
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"✅ Model switched to: {model_name}",
                content_type="text",
            )

        elif kwargs.get("ai_analysis_prompt"):
            prompt = kwargs["ai_analysis_prompt"]
            analysis_msg = IMMessage(
                request_id=msg.request_id,
                platform=msg.platform,
                user_id=msg.user_id,
                chat_id=msg.chat_id,
                chat_type=msg.chat_type,
                content_type="text",
                content=prompt,
                timestamp=msg.timestamp,
                raw=msg.raw,
                message_id=msg.message_id,
                sender_name=msg.sender_name,
                sender_open_id=msg.sender_open_id,
            )
            await self._run_agent_for_message(analysis_msg)

    # ── Config building ──────────────────────────────────────────────

    def _build_running_config(self) -> "RunningConfig":
        """Build a RunningConfig for slash command or agent execution."""
        from siada.entrypoint.interaction.running_config import RunningConfig
        from siada.config.config_loader import load_conf
        from siada.entrypoint.helpers.model_setup import get_config_from_conf

        conf = load_conf()
        model_config = get_config_from_conf(self._lark_io, conf)

        workspace = self._workspace or _get_default_workspace()

        return RunningConfig(
            llm_config=model_config,
            io=self._lark_io,
            workspace=workspace,
            agent_name=self._agent_name,
            interactive=True,
            console_output=False,
            mcp_config=conf.mcp_config if conf else None,
            compaction_strategy=conf.compaction_strategy if conf else None,
        )

    # ── Message handling ─────────────────────────────────────────────

    async def _handle_message(self, msg: IMMessage) -> None:
        """Handle a single incoming message by running the agent.

        - Checks DM access control (only p2p supported)
        - Intercepts slash commands (e.g. /status, /clear, /model)
        - Cancels any running task for the same chat_id
        - Loads or creates a persistent session keyed by chat_id
        - Runs the agent and consumes stream events
        """
        # Only support DM (p2p); ignore group messages
        if msg.chat_type != "p2p":
            logger.debug(f"Ignoring non-DM message: chat_type={msg.chat_type}")
            return

        # DM access control
        if not self._check_dm_access(msg):
            pair_key = self._resolve_pair_key(msg)
            logger.warning(f"Blocked unauthorized DM: pair_key={pair_key}, chat_id={msg.chat_id}")
            await self._send_access_denied(msg)
            return

        # Intercept slash commands before agent dispatch
        if self._is_slash_command(msg.content):
            await self._cancel_active_task(msg.chat_id)
            try:
                self._lark_io.set_context(msg.request_id, msg.chat_id)
                running_config = self._build_running_config()
                session = self._get_or_create_session(msg, running_config)
                handled = await self._handle_slash_command(msg, session)
                if handled:
                    return
            except Exception as e:
                logger.error(f"Slash command handling error: {e}", exc_info=True)
                await self._card_sender.send_im(
                    msg.request_id,
                    msg.chat_id,
                    f"❌ Command failed: {_format_exception_for_user(e)}",
                    content_type="text",
                )
                return

        # Cancel previous running task for this chat if any
        await self._cancel_active_task(msg.chat_id)

        # Fire-and-forget: create task but do NOT await it
        task = asyncio.create_task(self._run_agent_for_message(msg))
        self._active_tasks[msg.chat_id] = task

        def _on_task_done(t: asyncio.Task, _chat_id=msg.chat_id, _msg=msg):
            """Callback to handle task completion, cancellation, or error."""
            if self._active_tasks.get(_chat_id) is t:
                self._active_tasks.pop(_chat_id, None)

            if t.cancelled():
                logger.info(f"Task for chat_id={_chat_id} was interrupted by user")
                asyncio.ensure_future(self._card_sender.send_im(
                    _msg.request_id, _msg.chat_id,
                    "⏹️ Previous task interrupted by user.",
                    content_type="text",
                ))
            elif t.exception():
                exc = t.exception()
                logger.error(f"Task for chat_id={_chat_id} failed: {exc}", exc_info=exc)
                asyncio.ensure_future(self._card_sender.send_im(
                    _msg.request_id,
                    _msg.chat_id,
                    f"❌ Agent execution failed: {_format_exception_for_user(exc)}",
                    content_type="text",
                ))

        task.add_done_callback(_on_task_done)

    def _get_session_dir(self, session_id: str, workspace: str) -> "Path":
        """Get the session directory path for ownership management."""
        from pathlib import Path
        from siada.utils import DirectoryUtils
        sessions_dir = DirectoryUtils.get_global_sessions_dir(workspace)
        return Path(sessions_dir) / session_id

    def _clear_session_disk_history(self, msg: IMMessage, session: "RunningSession") -> None:
        """Clear all files in the session directory on disk.

        Removes the entire session directory contents so that the next
        FileSession created with the same deterministic session_id starts fresh.
        """
        import shutil

        try:
            workspace = self._workspace or _get_default_workspace()
            session_dir = self._get_session_dir(session.session_id, workspace)
            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.info(f"Cleared session directory: {session_dir}")
        except Exception as e:
            logger.warning(f"Failed to clear session disk history: {e}")

    # ── Agent execution ──────────────────────────────────────────────

    async def _run_agent_for_message(self, msg: IMMessage) -> None:
        """Core agent execution logic, runs inside a cancellable Task."""
        start_time = time.time()
        logger.info(
            f"Processing message: request_id={msg.request_id}, "
            f"user={msg.user_id}, content={msg.content[:50]}..."
        )

        self._lark_io.set_context(msg.request_id, msg.chat_id)

        # Add typing indicator (Typing emoji) on the user's message
        await self._card_sender.add_typing(msg)

        session_dir = None  # track for ownership release in finally

        try:
            from siada.services.siada_runner import SiadaRunner

            running_config = self._build_running_config()
            workspace = self._workspace or _get_default_workspace()

            # Get or create persistent session for this chat
            session = self._get_or_create_session(msg, running_config)

            # Check and acquire session ownership for Lark
            from siada.session.ownership import (
                SessionOwnershipManager, SessionOwner, OwnershipError,
            )
            session_dir = self._get_session_dir(session.session_id, workspace)
            try:
                SessionOwnershipManager.acquire_ownership(session_dir, SessionOwner.LARK)
            except OwnershipError:
                logger.warning(
                    f"Session {session.session_id} is currently owned by CLI, cannot acquire for Lark"
                )
                await self._card_sender.send_im(
                    msg.request_id,
                    msg.chat_id,
                    "⚠️ This session is currently being used by CLI. "
                    "Please wait for the current turn to finish.",
                    content_type="text",
                )
                return

            # Mark session source as lark
            SessionOwnershipManager.set_session_source(session_dir, SessionOwner.LARK)

            # Store session for interrupt handling
            self._active_sessions[msg.chat_id] = session

            result: RunResultStreaming = await SiadaRunner.run_agent(
                agent_name=self._agent_name,
                user_input=msg.content,
                workspace=workspace,
                session=session,
                stream=True,
            )
            # Store result for cancellation (like ConversationTurn.current_result)
            self._active_results[msg.chat_id] = result

            # Consume stream events via delegated consumer
            await self._stream_consumer.consume_stream(
                result, msg.request_id, msg.chat_id, workspace,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"Message processed: request_id={msg.request_id}, "
                f"duration={elapsed_ms}ms"
            )

        finally:
            # Release Lark ownership when task completes
            if session_dir:
                from siada.session.ownership import SessionOwnershipManager, SessionOwner
                SessionOwnershipManager.release_ownership(session_dir, SessionOwner.LARK)

            # Remove typing indicator when done
            await self._card_sender.remove_typing(msg.chat_id)

            if hasattr(self._transport, "send_ack"):
                await self._transport.send_ack(msg.request_id)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def stop(self) -> None:
        """Stop the controller and disconnect transport."""
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Utilities
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _get_default_workspace() -> str:
    """Get default workspace path."""
    from siada.foundation.constants import SIADA_HOME

    workspace = SIADA_HOME / "workspace" / "lark"
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


def _format_exception_for_user(
    exc: BaseException | None, max_length: int = 200
) -> str:
    """Format an exception into a user-friendly message for IM delivery."""
    if exc is None:
        return "Unknown error"
    message = str(exc).strip() or exc.__class__.__name__
    message = _decode_embedded_bytes_literals(message)
    if len(message) > max_length:
        return message[: max_length - 3] + "..."
    return message


def _decode_embedded_bytes_literals(text: str) -> str:
    """Decode bytes literals embedded in exception strings.

    Example:
        ``AnthropicException - b'{"message":"\\xe4\\xbe..."}'``
        becomes a readable UTF-8 string before sending to IM users.
    """

    def _replace(match: re.Match[str]) -> str:
        literal = match.group(0)
        # Guard against extremely large literals that could consume excessive resources
        if len(literal) > 2000:
            return literal
        try:
            value = ast.literal_eval(literal)
        except Exception:
            return literal

        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace")
        return literal

    try:
        return _BYTES_LITERAL_PATTERN.sub(_replace, text)
    except Exception:
        logger.debug("Failed to decode embedded bytes literals", exc_info=True)
        return text
