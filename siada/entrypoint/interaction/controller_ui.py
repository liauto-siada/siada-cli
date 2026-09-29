"""
ControllerUI — ACP presentation sidecar for the interaction Controller.

Extracts the ACP-only UI logic (session titles, banner_info,
frontend notification plumbing and deferred-rendering history sync) out of
Controller so the main interaction loop stays focused on turn/session flow.

Scope rules:
- ACP only. Non-ACP configurations render nothing through this class — the
  interactive Controller requires ACP. No Rich, no prompt_toolkit, no
  terminal clear, no traditional banner.
- Wire payloads (JSON-RPC messages built via ACPMessageBuilder) are kept
  byte-for-byte identical to the previous Controller implementation.
"""

import asyncio
import json
import threading
from typing import Any, Callable, Optional

from siada.foundation.logging import logger as logging
from siada.session.session_models import RunningSession
from siada.support.slash_commands import get_argument_hint


class ControllerUI:
    """ACP presentation logic for a Controller.

    Args:
        config: RunningConfig (acp_mode, io with acp_adapter, llm_config, ...).
        slash_commands: SlashCommands instance used to enumerate banner commands.
        get_session: zero-argument callback returning the *current*
            RunningSession. Resolved on every use so that after a /clear swap
            all notifications/history syncs automatically target the new
            session (never a stale one).
    """

    def __init__(
        self,
        config: Any,
        slash_commands: Any,
        get_session: Callable[[], Optional[RunningSession]],
    ):
        self.config = config
        self.slash_commands = slash_commands
        self._get_session = get_session

        # One-shot title generation guard for the current session.
        self._session_title_sent: bool = False

        # Deferred-rendering history state: this process's last confirmed
        # transcript signature and native item count for the current session.
        # Fully owned by ControllerUI (see sync_history_state/reset_history_state).
        self._known_sig: str = ""
        self._known_count: int = 0

        # Set by close() to make all sends no-ops during shutdown.
        self._exiting: bool = False

    # ------------------------------------------------------------------ #
    # Low-level ACP send helper
    def set_processing(self, processing: bool) -> None:
        from siada.io.acp.message_builder import ACPMessageBuilder

        self._send_if_acp(ACPMessageBuilder().build_session_update(
            reason="processing_started" if processing else "input_ready",
            content="",
            metadata={"animation_control": "start" if processing else "stop"},
        ))

    def send_cancelled(self, message: str) -> None:
        from siada.io.acp.message_builder import ACPMessageBuilder

        self._send_if_acp(ACPMessageBuilder().build_cancelled(message))

    def remember_history_state(self, session: RunningSession) -> None:
        """Record our own completed turn without replaying it to the UI."""
        if session.openai_session:
            self._known_sig = session.openai_session.last_signature
            self._known_count = session.openai_session.native_item_count

    # ------------------------------------------------------------------ #
    def _send_if_acp(self, message: Any) -> Any:
        """Send one built ACP message through the adapter when ACP is active.

        Mirrors the previous Controller call pattern
        ``io.acp_adapter._send_if_acp(lambda m=msg: m)``.
        """
        if self._exiting or not self.config.acp_mode:
            return None
        adapter = getattr(getattr(self.config, "io", None), "acp_adapter", None)
        if adapter is None:
            return None
        try:
            return adapter._send_if_acp(lambda m=message: m)
        except Exception as e:
            logging.warning(f"[ControllerUI] Failed to send ACP message: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Session title
    # ------------------------------------------------------------------ #
    def send_session_title_async(self, user_text: str) -> None:
        """Generate a session title on a background thread and push it via ACP.

        Fire-and-forget: never blocks the main turn. Guarded by
        ``self._session_title_sent`` so it runs at most once per controller
        session; the guard is re-armed on failure or when the session was
        swapped (e.g. /clear) mid-generation, so the next user message can
        produce a title for the new session.

        The session is captured when the worker starts; if a /clear replaces
        it while the fast-LLM call is still running, the stale title is
        dropped instead of being pushed to the new session.
        """
        if self._exiting or not self.config.acp_mode or self._session_title_sent:
            return
        self._session_title_sent = True

        session = self._get_session()
        if session is None:
            self._session_title_sent = False
            return

        def _generate_and_send():
            try:
                from siada.services.session_title import generate_session_title

                title = asyncio.run(generate_session_title(user_text))
                if not title:
                    if self._get_session() is session:
                        self._session_title_sent = False
                    return

                # After /clear the controller holds a fresh session; never
                # attach the old session's title to it.
                if self._get_session() is not session:
                    logging.debug(
                        "[ControllerUI] Session changed during title generation; "
                        "dropping stale title"
                    )
                    return

                # Persist alongside the terminal title so completion
                # notifications can reference the same value.
                session.state.session_title = title

                from siada.io.acp.message_builder import ACPMessageBuilder

                builder = ACPMessageBuilder()
                msg = builder.build_session_update(
                    reason="session_title",
                    content=title,
                )
                self._send_if_acp(msg)
                logging.debug(f"[ControllerUI] Session title sent: {title}")
            except Exception as e:
                logging.debug(f"[ControllerUI] Session title generation failed: {e}")
                if self._get_session() is session:
                    self._session_title_sent = False

        t = threading.Thread(target=_generate_and_send, daemon=True)
        t.start()

    # ------------------------------------------------------------------ #
    # Custom notifications + frontend → backend plumbing
    # ------------------------------------------------------------------ #
    def send_notification(self, method: str, params: dict) -> None:
        """Send a custom JSON-RPC ACP notification to the frontend."""
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder

            notification = ACPMessageBuilder().build_custom_notification(
                method=method,
                params=params,
            )
            self._send_if_acp(notification)
        except Exception as e:
            logging.warning(
                f"[ControllerUI] Failed to send ACP notification {method}: {e}"
            )

    def register_notification_handler(self) -> None:
        """Register the IO callback dispatching frontend JSON-RPC notifications.

        The handler always resolves the session through ``_get_session()``, so
        after a /clear the very same callback targets the new session.
        """
        if not self.config.acp_mode or not self.config.io:
            return

        def notification_handler(method: str, params: dict):
            if method == "session/pullHistory":
                self.sync_history_state(self._get_session())
            else:
                logging.debug(f"[ControllerUI] Unhandled notification: {method}")

        self.config.io._notification_handler = notification_handler
        logging.info("[ControllerUI] Registered ACP notification handler on IO")

    # ------------------------------------------------------------------ #
    # Deferred-rendering history sync
    # ------------------------------------------------------------------ #
    def sync_history_state(self, session: Optional[RunningSession]) -> None:
        """Handle a frontend session/pullHistory request.

        Compares this process's known transcript state (signature + count)
        against the on-disk FileSession and pushes any diverged messages to
        the frontend in a single atomic pullHistoryDone notification.
        """
        if not session or not session.openai_session:
            logging.info("[ControllerUI] pullHistory: no session, sending done immediately")
            self.send_notification("session/pullHistoryDone", {})
            return

        file_session = session.openai_session
        try:
            # This process's saved known state (set after each turn / sync).
            known_sig = self._known_sig
            known_count = self._known_count

            # Read current disk state (may have been updated by another process).
            loop = asyncio.new_event_loop()
            try:
                disk_items = loop.run_until_complete(file_session.get_items())
            finally:
                loop.close()

            # Compare disk signature (from signature.json, written by any
            # writer) with this process's known signature.
            disk_sig = file_session.last_signature

            logging.info(
                f"[ControllerUI] pullHistory: known_sig={known_sig[:8] if known_sig else '(empty)'}, "
                f"disk_sig={disk_sig[:8] if disk_sig else '(empty)'}, "
                f"known_count={known_count}, disk_count={len(disk_items)}"
            )

            # First time (empty sig) or no change — sync state, no messages.
            if known_sig == "" or disk_sig == known_sig:
                self._known_sig = disk_sig
                self._known_count = len(disk_items)
                logging.info(
                    f"[ControllerUI] pullHistory: no divergence "
                    f"(first_time={known_sig == ''}, same_sig={disk_sig == known_sig}), "
                    f"synced to sig={disk_sig[:8] if disk_sig else '(empty)'}, count={len(disk_items)}"
                )
                self.send_notification("session/pullHistoryDone", {})
                return

            # Session diverged — extract new items via incremental slicing.
            new_items = (
                disk_items[known_count:] if len(disk_items) > known_count else disk_items
            )

            from siada.support.message_classifier import format_native_items_for_display

            messages = format_native_items_for_display(new_items) if new_items else []

            # Update local state after handling divergence.
            self._known_sig = disk_sig
            self._known_count = len(disk_items)

            # Send history + done as a single atomic notification to prevent
            # race conditions.
            self.send_notification(
                "session/pullHistoryDone",
                {"messages": messages if messages else []},
            )

            logging.info(
                f"[ControllerUI] pullHistory: DIVERGED, sent {len(messages)} messages "
                f"(new_items={len(new_items)}, known_count={known_count}, "
                f"disk_count={len(disk_items)}, new_sig={disk_sig[:8] if disk_sig else '(empty)'})"
            )

        except Exception as e:
            logging.warning(f"[ControllerUI] Failed to handle pullHistory: {e}")
            self.send_notification("session/pullHistoryDone", {})

    def reset_history_state(self) -> None:
        """Forget the known transcript state (called after /clear or resume)."""
        self._known_sig = ""
        self._known_count = 0
        self._session_title_sent = False

    # ------------------------------------------------------------------ #
    # Banner info
    # ------------------------------------------------------------------ #
    def show_announcements(self) -> None:
        """Push the banner_info payload over ACP (no-op outside ACP mode).

        Also triggers the immediate quota fetch and the (single) periodic
        quota refresh timer. No terminal clear / Rich banner.
        """
        if not self.config.acp_mode:
            return

        import os

        from siada import __version__
        from siada.io.acp.message_builder import ACPMessageBuilder

        logging.info(
            f"[ControllerUI] show_announcements called, acp_mode={self.config.acp_mode}"
        )

        # Slash commands with descriptions + argument hints.
        slash_commands = []
        if self.slash_commands:
            try:
                session = self._get_session()
                commands = self.slash_commands.get_commands(session)
                for cmd in commands:
                    cmd_name = cmd[1:]  # strip leading '/'
                    cmd_method_name = f"cmd_{cmd_name}".replace("-", "_")
                    cmd_method = getattr(self.slash_commands, cmd_method_name, None)
                    description = ""
                    if cmd_method and cmd_method.__doc__:
                        description = cmd_method.__doc__.strip()
                    slash_commands.append(
                        {
                            "name": cmd_name,
                            "description": description,
                            "argument_hint": get_argument_hint(cmd_name),
                        }
                    )
            except Exception as e:
                logging.warning(f"[ControllerUI] Failed to get slash commands: {e}")

        # Checkpoint files (most recent 50).
        checkpoints = []
        session = self._get_session()
        try:
            if session and getattr(session, "checkpoint_service", None):
                checkpoint_files = session.checkpoint_service.list_checkpoint_files(
                    session.session_id
                )
                for cp_file in checkpoint_files[:50]:
                    checkpoints.append(
                        {
                            "file_name": cp_file.file_name,
                            "timestamp": cp_file.timestamp_str,
                            "tool": cp_file.tool_placeholder,
                            "modified_files": cp_file.modified_files_placeholder,
                        }
                    )
                logging.info(f"[ControllerUI] Found {len(checkpoints)} checkpoint files")
        except Exception as e:
            logging.warning(f"[ControllerUI] Failed to get checkpoint files: {e}")

        # Session identity + project hash for the frontend.
        session_id = None
        project_hash = None
        if session:
            session_id = getattr(session, "session_id", None)
            workspace = getattr(self.config, "workspace", None)
            if workspace:
                from siada.utils import DirectoryUtils

                project_hash = DirectoryUtils.get_file_path_hash(workspace)

        # Memory master switch, mirrored from conf.yaml at startup.
        _memory_enabled = getattr(self.config, "memory_enabled", True)

        banner_info = {
            "version": __version__,
            "working_dir": os.getcwd(),
            "agent": self.config.agent_name,
            "provider": self.config.llm_config.provider,
            "model": self.config.llm_config.model_name,
            "thinking_tokens": self.config.llm_config.get_thinking_tokens(),
            "reasoning_effort": self.config.llm_config.get_reasoning_effort(),
            "thinking_enabled": self.config.llm_config.enable_thinking,
            "parallel_tool_calls": self.config.llm_config.parallel_tool_calls,
            "slash_commands": slash_commands,
            "checkpoints": checkpoints,
            "session_id": session_id,
            "project_hash": project_hash,
            "memory_enabled": _memory_enabled,
            "theme": self._resolve_ui_theme(),
        }

        logging.info(
            f"[ControllerUI] Sending banner_info in ACP mode with {len(slash_commands)} commands"
        )

        try:
            builder = ACPMessageBuilder()
            result = self._send_if_acp(
                builder.build_session_update(
                    reason="banner_info",
                    content=json.dumps(banner_info),
                    metadata={"type": "banner"},
                )
            )
            logging.info(f"[ControllerUI] Banner info sent via _send_if_acp, result={result}")
        except Exception as e:
            logging.error(f"[ControllerUI] Failed to send banner_info: {e}", exc_info=True)

    def _resolve_ui_theme(self) -> str:
        """Resolve the configured UI theme to a concrete 'dark'|'light' value.

        Reads ``ui.theme`` from conf.yaml ('auto' is the default) and resolves
        non-concrete values through the terminal/system theme detector, which
        returns a platform-dependent theme. The frontend only
        understands dark|light.
        """
        from siada.config.conf_store import get_conf_value

        theme = get_conf_value("ui.theme", "auto")
        if theme in ("dark", "light"):
            return theme
        from siada.io.system_theme_detector import SystemThemeDetector

        resolved = SystemThemeDetector.get_theme_for_config(theme)
        return resolved if resolved in ("dark", "light") else "dark"

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """Mark the UI as exiting (idempotent)."""
        self._exiting = True
        self.config.io._notification_handler = None
