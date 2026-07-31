"""Session management and resolution component for LarkController.

Handles:
- Session cache operations (get, load, create, ensure)
- Startup preloading of routed sessions
- Runtime session resolution (P2P thread routing + group fallback)
- Cross-session switching with user notification
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from siada.im.feishu.notification_templates import (
    get_idle_session_reset_notification_template,
    get_session_switch_notification_template,
)

if TYPE_CHECKING:
    from siada.entrypoint.interaction.lark_controller import LarkController
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.im.models import IMMessage
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.controller")


class LarkSessionResolver:
    """Session management and resolution for LarkController.

    Encapsulates session cache operations, startup preloading, and
    runtime session resolution (P2P thread routing + group fallback).
    """

    def __init__(self, ctrl: "LarkController") -> None:
        self._ctrl = ctrl

    # ── Session cache operations ──────────────────────────────────────

    def get_or_load(self, session_id: str) -> Optional["RunningSession"]:
        """Get session from cache, or load from disk if not cached.

        Used by IpcMessageHandler to write IPC messages to session history
        even when the session isn't currently active in memory.
        """
        logger.debug(
            "[get_or_load] session_id=%s, in_cache=%s",
            session_id, session_id in self._ctrl._session_cache,
        )
        session = self._ctrl._session_cache.get(session_id)
        if session:
            return session

        try:
            running_config = self._ctrl._build_running_config()
            loaded = self._ctrl.switch_and_resume_session(
                "__ipc_load__", session_id, running_config,
            )
            if loaded:
                self._ctrl._session_cache[session_id] = loaded
                logger.info(
                    "Loaded session %s from disk for IPC history write",
                    session_id,
                )
                return loaded
        except Exception as e:
            logger.warning(
                "Failed to load session %s from disk: %s", session_id, e,
            )
        return None

    def get_or_create(
        self, msg: "IMMessage", running_config: "RunningConfig",
    ) -> "RunningSession":
        """Delegate to parent ImController.resolve_session()."""
        logger.debug(
            "[get_or_create] chat_id=%s, chat_type=%s, sender_open_id=%s",
            msg.chat_id, msg.chat_type, msg.sender_open_id,
        )
        return self._ctrl.resolve_session(
            msg.chat_id,
            running_config,
            is_single_chat=msg.chat_type == "p2p",
            open_id=msg.sender_open_id,
        )

    def load_or_create(
        self,
        session_id: str,
        msg: "IMMessage",
        running_config: "RunningConfig",
    ) -> "RunningSession":
        """Load a session by ID from cache or disk, falling back to create new.

        Resolution order:
        1. Return from _session_cache if already present
        2. Try switch_and_resume_session to restore from disk
        3. Fall back to get_or_create (creates brand new)

        The returned session is always present in _session_cache.
        """
        cached = self._ctrl._session_cache.get(session_id)
        if cached:
            return cached

        logger.info(
            "Session %s not in cache, loading from disk for chat_id=%s",
            session_id, msg.chat_id,
        )
        loaded = self._ctrl.switch_and_resume_session(
            msg.chat_id, session_id, running_config,
            is_single_chat=(msg.chat_type == "p2p"),
        )
        if loaded:
            self._ctrl._session_cache[session_id] = loaded
            return loaded

        logger.warning(
            "Failed to load session %s from disk, creating new session for chat_id=%s",
            session_id, msg.chat_id,
        )
        return self.get_or_create(msg, running_config)

    def ensure_in_cache(self, session: "RunningSession") -> None:
        """Guarantee a session object is present in _session_cache."""
        if session.session_id not in self._ctrl._session_cache:
            self._ctrl._session_cache[session.session_id] = session
            logger.info(
                "Synced session into _session_cache: session_id=%s",
                session.session_id,
            )

    # ── Startup preload ───────────────────────────────────────────────

    def preload_routed_sessions(self) -> None:
        """Eagerly pre-load all sessions from both P2P and group routing tables.

        Called at startup to ensure ThreadSessionRouter can always find
        session objects via _session_cache.get().
        """
        cache = self._ctrl._session_cache
        p2p_routing = self._ctrl._routing
        group_routing = self._ctrl._group_routing

        total_chats = len(p2p_routing.chats) + len(group_routing.chats)
        if total_chats == 0:
            logger.debug("[preload_routed_sessions] no routing chats, skipping")
            return

        logger.info(
            "[preload_routed_sessions] pre-loading: p2p_chats=%d, group_chats=%d, cache_size=%d",
            len(p2p_routing.chats), len(group_routing.chats), len(cache),
        )
        running_config = self._ctrl._build_running_config()

        seen: set[str] = set()
        # Preload P2P routing sessions
        for chat_id, entry in p2p_routing.chats.items():
            session_id = entry.get("session_id") if isinstance(entry, dict) else None
            if not session_id or session_id in seen:
                continue
            seen.add(session_id)
            if session_id in cache:
                continue
            self._preload_single(session_id, chat_id, running_config)

        # Preload group routing sessions
        for chat_id, entry in group_routing.chats.items():
            session_id = entry.get("session_id") if isinstance(entry, dict) else None
            if not session_id or session_id in seen:
                continue
            seen.add(session_id)
            if session_id in cache:
                continue
            self._preload_single(session_id, chat_id, running_config)

        logger.info(
            "[preload_routed_sessions] done: loaded=%d, total_routing_entries=%d",
            len(seen), total_chats,
        )

    def _preload_single(
        self, session_id: str, chat_id: str, running_config: "RunningConfig",
    ) -> None:
        """Load a single session into cache at startup (resume from disk or create fresh)."""
        try:
            session = self._ctrl.switch_and_resume_session(
                chat_id, session_id, running_config,
            )
            if not session:
                from siada.session.session_manager import RunningSessionManager
                session = RunningSessionManager.create_session(
                    siada_config=running_config,
                    session_id=session_id,
                )
                self._ctrl._mark_session_source(session_id, running_config.workspace)
                logger.info(
                    "Created fresh session for routing entry: session_id=%s",
                    session_id,
                )
            self._ctrl._session_cache[session_id] = session
        except Exception as e:
            logger.warning(
                "Failed to pre-load session %s for chat_id=%s: %s",
                session_id, chat_id, e,
            )

    # ── Runtime session resolution ────────────────────────────────────

    async def resolve_session(
        self, msg: "IMMessage", running_config: "RunningConfig",
    ) -> tuple[Optional["RunningSession"], "IMMessage"]:
        """Resolve the session for an incoming message.

        Dispatches by chat_type:
        - P2P: thread-based routing with cross-session switching support
        - Group: simple routing-table lookup or create

        Returns (session, msg) where msg may be rebuilt with injected context.
        """
        if msg.chat_type == "p2p":
            return await self._resolve_p2p_session(msg, running_config)
        return await self._resolve_group_session(msg, running_config)

    async def _switch_and_notify(
        self, msg: "IMMessage", target_session_id: str,
        running_config: "RunningConfig",
        *, is_single_chat: bool = True,
    ) -> Optional["RunningSession"]:
        """Resume a session from disk, update routing/cache, and notify user on success.

        Works for both P2P (``is_single_chat=True``) and group chats; the
        routing table is selected accordingly.

        ``is_single_chat`` is NOT cosmetic — it picks the correct routing
        table for BOTH reads and writes:
          - reading ``previous_sid`` via ``_get_routed_session_id`` (P2P
            ``_routing`` vs group ``_group_routing``) so the ``/resume
            <previous_sid>`` hint points at the right session;
          - writing the resumed binding back via
            ``switch_and_resume_session`` so it lands in the matching table.
        Group callers MUST pass ``is_single_chat=False``; otherwise a group
        ``/resume`` would read/write the P2P table, producing a wrong hint,
        corrupted routing, and an effectively no-op resume.

        Returns the resumed session, or None if resume failed.
        """
        logger.info(
            "[_switch_and_notify] chat_id=%s, target_session_id=%s, is_single_chat=%s",
            msg.chat_id, target_session_id, is_single_chat,
        )
        # Capture previous session_id before routing update
        previous_sid = self._ctrl._get_routed_session_id(
            msg.chat_id, is_group=not is_single_chat,
        ) or ""

        session = self._ctrl.switch_and_resume_session(
            msg.chat_id, target_session_id, running_config,
            is_single_chat=is_single_chat,
        )
        if session:
            # switch_and_resume_session() already updates routing + cache
            # via set_session_for_chat(), no need to duplicate here.
            tpl = get_session_switch_notification_template(
                self._ctrl._resolve_preferred_language(),
            )
            switch_back_hint = (
                tpl.switch_back_with_id.format(previous_sid=previous_sid)
                if previous_sid
                else tpl.switch_back_generic
            )
            await self._ctrl._card_sender.send_im(
                msg.request_id,
                msg.chat_id,
                f"{tpl.switched_message.format(session_id=target_session_id)}\n"
                f"{tpl.subsequent_hint}\n"
                f"{switch_back_hint}",
                content_type="text",
            )
        else:
            logger.warning(
                "Failed to resume session %s for chat_id=%s",
                target_session_id, msg.chat_id,
            )
        return session

    async def _maybe_reset_idle_session(
        self,
        msg: "IMMessage",
        last_activity: Optional[float],
        now: float,
        current_session_id: str,
        running_config: "RunningConfig",
        *,
        is_single_chat: bool = True,
    ) -> Optional["RunningSession"]:
        """Start a fresh session when the user returns after a long silence.

        When the elapsed time since the previous message exceeds the configured
        idle timeout, a brand new session is created and bound to the chat
        (P2P or group, selected via ``is_single_chat``). The user is notified
        that the previous session can be restored via ``/resume <session_id>``.

        Returns the new session when a reset is triggered, or None otherwise
        (so the caller continues on the existing session).
        """
        timeout = self._ctrl._resolve_idle_session_timeout()
        logger.info(
            "[idle_reset] chat_id=%s, idle_session_timeout=%.0fs (0 = disabled)",
            msg.chat_id, timeout,
        )
        if timeout <= 0:
            logger.info(
                "[idle_reset] chat_id=%s, idle reset disabled (timeout=%.0f), skipping",
                msg.chat_id, timeout,
            )
            return None

        import datetime

        if last_activity is None:
            # No previous activity recorded for this chat (first message ever,
            # or last_activity.json absent/not containing this chat_id).
            # Skip idle reset — there is no prior session to compare against.
            logger.info(
                "[idle_reset] chat_id=%s, no last_activity recorded, skipping idle reset",
                msg.chat_id,
            )
            return None

        logger.info(
            "[idle_reset] chat_id=%s, last_activity=%s (%.0fs ago)",
            msg.chat_id,
            datetime.datetime.fromtimestamp(last_activity).strftime("%Y-%m-%d %H:%M:%S"),
            now - last_activity,
        )

        idle_seconds = now - last_activity
        if idle_seconds <= timeout:
            return None

        logger.info(
            "Idle timeout reached for chat_id=%s (idle=%.0fs > %.0fs, is_single_chat=%s); "
            "starting a new session (previous=%s)",
            msg.chat_id, idle_seconds, timeout, is_single_chat, current_session_id,
        )
        new_session = self._ctrl.create_new_session(
            msg.chat_id, running_config,
            is_single_chat=is_single_chat, open_id=msg.sender_open_id,
        )

        tpl = get_idle_session_reset_notification_template(
            self._ctrl._resolve_preferred_language(),
        )
        idle_minutes = max(1, int(timeout // 60))
        resume_hint = (
            tpl.resume_hint.format(previous_sid=current_session_id)
            if current_session_id
            else tpl.resume_hint_generic
        )
        try:
            await self._ctrl._card_sender.send_im(
                msg.request_id,
                msg.chat_id,
                f"{tpl.reset_message.format(idle_minutes=idle_minutes)}\n{resume_hint}",
                content_type="text",
            )
        except Exception as e:
            logger.warning(
                "Failed to send idle-reset notification for chat_id=%s: %s",
                msg.chat_id, e,
            )
        return new_session

    async def _resolve_p2p_session(
        self, msg: "IMMessage", running_config: "RunningConfig",
    ) -> tuple[Optional["RunningSession"], "IMMessage"]:
        """Resolve session via thread-based routing for P2P messages."""
        logger.info(
            "[_resolve_p2p_session] chat_id=%s, sender_open_id=%s, content_len=%d",
            msg.chat_id, msg.sender_open_id, len(msg.content),
        )
        # Track per-chat activity for idle-based session resets. Capture the
        # previous activity time first, then record (and persist) the current
        # message time so the idle timer survives daemon restarts.
        now = time.time()
        last_activity = self._ctrl._last_activity_ts.get(msg.chat_id)
        self._ctrl._last_activity_ts[msg.chat_id] = now
        self._ctrl._persist_last_activity()

        resolved_session_id = await self._ctrl._thread_router.resolve_target_session(
            msg,
        )
        logger.info(
            "_resolve_p2p_session: chat_id=%s, resolved_session_id=%s",
            msg.chat_id, resolved_session_id,
        )

        current_session_id = self._ctrl._get_routed_session_id(
            msg.chat_id, open_id=msg.sender_open_id,
        )

        # Bind chat_id if resolved via open_id fallback
        if current_session_id and not self._ctrl._routing.get_session_id(msg.chat_id):
            logger.info(
                "Binding chat_id=%s to session=%s (resolved via open_id=%s)",
                msg.chat_id, current_session_id, msg.sender_open_id,
            )
            self._ctrl._set_routing_entry(
                msg.chat_id, current_session_id, is_single_chat=True,
            )
            self._ctrl._persist_routing()

        # No session at all — create new
        if not resolved_session_id and not current_session_id:
            logger.info(
                "No session resolved for chat_id=%s, creating new session",
                msg.chat_id,
            )
            return self.get_or_create(msg, running_config), msg

        # Same session — continue here, unless the user has been idle long
        # enough to warrant a fresh session (with a /resume hint).
        if resolved_session_id == current_session_id:
            idle_session = await self._maybe_reset_idle_session(
                msg, last_activity, now, current_session_id, running_config,
            )
            if idle_session is not None:
                return idle_session, msg
            return self.load_or_create(
                current_session_id, msg, running_config,
            ), msg

        # Different session — switch with notification
        logger.info(
            "Switching session for chat_id=%s: current=%s -> resolved=%s",
            msg.chat_id, current_session_id, resolved_session_id,
        )
        session = await self._switch_and_notify(
            msg, resolved_session_id, running_config,
        )
        if not session:
            logger.info(
                "Resume failed for session %s, creating new session for chat_id=%s",
                resolved_session_id, msg.chat_id,
            )
            session = self.get_or_create(msg, running_config)

        return session, msg

    async def _resolve_group_session(
        self, msg: "IMMessage", running_config: "RunningConfig",
    ) -> tuple[Optional["RunningSession"], "IMMessage"]:
        """Resolve session for a group chat, with idle-based reset support.

        Group chats do not use thread-based routing; they map a chat_id to a
        single group session. After a long idle period a fresh session is
        started (with a /resume hint), mirroring the P2P behavior.
        """
        logger.info(
            "[_resolve_group_session] chat_id=%s, content_len=%d",
            msg.chat_id, len(msg.content) if msg.content else 0,
        )
        # Track per-chat activity (persisted) for idle-based session resets.
        now = time.time()
        last_activity = self._ctrl._last_activity_ts.get(msg.chat_id)
        self._ctrl._last_activity_ts[msg.chat_id] = now
        self._ctrl._persist_last_activity()

        current_session_id = self._ctrl._get_routed_session_id(
            msg.chat_id, is_group=True,
        )

        # Existing group session present — reset it if idle long enough.
        if current_session_id:
            idle_session = await self._maybe_reset_idle_session(
                msg, last_activity, now, current_session_id, running_config,
                is_single_chat=False,
            )
            if idle_session is not None:
                return idle_session, msg

        # No session yet, or still within the idle window — get/create normally.
        return self.get_or_create(msg, running_config), msg
