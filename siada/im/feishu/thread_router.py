"""ThreadSessionRouter - Session routing for Lark IM P2P messages.

Resolves target session_id based on reply-chain (parent_id)
or injected IPC content in the current session.

Extracted from LarkController to isolate the routing concern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from siada.im.models import IMMessage
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.thread_router")


class ThreadSessionRouter:
    """Resolves session routing based on reply context and IPC injection.

    Dependencies are injected via constructor to avoid tight coupling
    with LarkController state.
    """

    def __init__(
        self,
        *,
        get_session: Callable[[str], Optional["RunningSession"]],
        get_routed_session_id: Callable[..., Optional[str]],
    ) -> None:
        self._get_session = get_session
        self._get_routed_session_id = get_routed_session_id

    # ── Public API ────────────────────────────────────────────────────

    async def resolve_target_session(
        self,
        msg: "IMMessage",
    ) -> Optional[str]:
        """Resolve target session_id for a P2P message.

        Tries two strategies in order:
        1. Reply chain: parent_id -> search current session for injected IPC item
        2. Current session: check for pending IPC injection (last item)

        When an IPC-injected message is found, its content is populated into 
        msg.quoted_content and msg.quoted_sender for unified injection via 
        build_quoted_message_block(). Normal replies (non-IPC) are left for 
        the later QuotedMessageResolver (API) to handle.

        Returns:
            resolved session_id, or None if no routing match.
        """
        logger.info(
            "resolve_target_session: chat_id=%s, parent_id=%s",
            msg.chat_id, msg.parent_id,
        )

        current_session_id = self._get_routed_session_id(
            msg.chat_id, open_id=msg.sender_open_id,
        )

        # Strategy 1: reply to a message in current session
        # _resolve_via_reply_chain handles both cases:
        # - IPC-injected parent -> route to source session + populate quoted_content
        # - Normal parent -> stay on current session (quoted resolved later via API)
        if msg.parent_id and current_session_id:
            session_id, injected_content = await self._resolve_via_reply_chain(
                current_session_id, msg.parent_id,
            )
            # Populate quoted_content from IPC injection (if found).
            if injected_content:
                msg.quoted_content = injected_content
                msg.quoted_sender = "[cross-session notification]"
            return session_id

        # Strategy 2: current routed session (with IPC injection check)
        if current_session_id:
            session_id, injected_content = await self._resolve_via_current_session(current_session_id)
            if injected_content:
                msg.quoted_content = injected_content
                msg.quoted_sender = "[cross-session notification]"
            return session_id

        logger.info("resolve_target_session: no routing match, returning None")
        return None

    # ── Strategy implementations ──────────────────────────────────────

    async def _resolve_via_reply_chain(
        self, current_session_id: str, parent_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Strategy 1: search current session for the parent message.

        If the parent message is an IPC-injected item, extract its
        _source_session_id and route to that session.
        Otherwise the user is replying to a normal message — stay on
        the current session (no fall-through to Strategy 2).

        Returns:
            (source_session_id, injected_content) if parent is IPC-injected,
            (current_session_id, None) otherwise.
        """
        current_session = self._get_session(current_session_id)
        result = await self._find_injected_by_message_id(
            current_session, parent_id,
        )
        if result is None:
            # Not an IPC injection — normal reply, stay on current session
            logger.info(
                "reply_chain: parent_id=%s is not cross-session IPC, "
                "staying on current session=%s",
                parent_id, current_session_id,
            )
            return current_session_id, None

        source_session_id, injected_content = result
        logger.info(
            "reply_chain: parent_id=%s is injected, routing to source=%s",
            parent_id, source_session_id,
        )
        return source_session_id, injected_content

    async def _resolve_via_current_session(
        self, current_session_id: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Strategy 2: check current routed session for pending IPC injection.

        Always returns a tuple — either (source_session_id, content) if
        injection found, or (current_session_id, None) to keep current session.
        """
        current_session = self._get_session(current_session_id)
        result = await self._check_session_injected_content(current_session)
        if result:
            source_session_id, injected_content = result
            logger.info(
                "current_session: IPC injection found, switching to source=%s",
                source_session_id,
            )
            return source_session_id, injected_content

        logger.info(
            "current_session: no injection, keeping session=%s",
            current_session_id,
        )
        return current_session_id, None

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    async def _check_session_injected_content(
        session: Optional["RunningSession"],
    ) -> Optional[tuple[str, Optional[str]]]:
        """Check whether a session has a pending IPC injection.

        Reads inject_info.json (small, fast) then verifies that the injection
        is still the last item in api_history.  If the history has moved on
        (e.g. add_items was called after the injection), inject_info.json is
        cleared immediately so stale data never accumulates.

        Returns (source_session_id, content) if a live injection is found,
        None otherwise.
        """
        if session is None or session.openai_session is None:
            return None
        try:
            file_session = session.openai_session
            if not hasattr(file_session, "get_inject_info"):
                return None

            info = file_session.get_inject_info()
            if info is None:
                return None

            source_session_id, content = info

            # Verify the injection is still the last item in history.
            all_items = await file_session.get_all_items()
            if not all_items:
                file_session.clear_inject_info()
                return None

            last_item = all_items[-1]
            if (
                isinstance(last_item, dict)
                and last_item.get("_injected") is True
                and last_item.get("_source_session_id") == source_session_id
            ):
                # Injection is about to be consumed by routing — clear the
                # pending marker immediately so it cannot be replayed on
                # subsequent messages (e.g. resume + reply pattern).
                file_session.clear_inject_info()
                return source_session_id, content

            # History has moved past the injection — stale, self-correct.
            file_session.clear_inject_info()
        except Exception as e:
            logger.debug("Failed to check session injected content: %s", e)
        return None

    @staticmethod
    async def _find_injected_by_message_id(
        session: Optional["RunningSession"], target_message_id: str,
    ) -> Optional[tuple[str, Optional[str]]]:
        """Find a specific message by message_id in session history.

        If the message is an injected IPC item, return its source session
        and content for cross-session routing.

        Scans items in reverse order (parent message is likely near the end).
        Returns (source_session_id, content) if found as injected, None otherwise.
        """
        if session is None or session.openai_session is None:
            return None
        try:
            all_items = await session.openai_session.get_all_items()
            if not all_items:
                return None

            for item in reversed(all_items):
                if not isinstance(item, dict):
                    continue
                if item.get("message_id") == target_message_id:
                    if item.get("_injected") is True:
                        source_session_id = item.get("_source_session_id")
                        if source_session_id:
                            return source_session_id, item.get("content")
                    return None  # found but not injected
        except Exception as e:
            logger.debug("Failed to find injected by message_id=%s: %s", target_message_id, e)
        return None
