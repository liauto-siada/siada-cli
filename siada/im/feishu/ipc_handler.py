"""IpcMessageHandler - IPC message queue management for Lark IM.

Handles enqueuing, draining, and delivering IPC (inter-process communication)
messages to Lark chats or default sessions. Supports email notification fallback
when no chat_id is available.

Extracted from LarkController to isolate the IPC concern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from siada.im.feishu.notification_templates import (
    get_ipc_notification_card_template,
)

if TYPE_CHECKING:
    from siada.entrypoint.interaction.im_controller import RoutingTable
    from siada.im.feishu.card_sender import LarkCardSender
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.ipc_handler")


class IpcMessageHandler:
    """Manages the IPC message queue: enqueue, drain, and deliver.

    Dependencies are injected via constructor to avoid tight coupling
    with LarkController state.
    """

    def __init__(
        self,
        *,
        card_sender: "LarkCardSender",
        get_routed_session_id: Callable[..., Optional[str]],
        get_session: Callable[[str], Optional["RunningSession"]],
        is_single_chat: Callable[[str], bool],
        resolve_notify_email: Callable[[], Optional[str]],
        resolve_preferred_language: Callable[[], Optional[str]],
    ) -> None:
        self._card_sender = card_sender
        self._get_routed_session_id = get_routed_session_id
        self._get_session = get_session
        self._is_single_chat = is_single_chat
        self._resolve_notify_email = resolve_notify_email
        self._resolve_preferred_language = resolve_preferred_language

        # Pending message queue (stores pre-resolved delivery items)
        self._pending_messages: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────

    async def enqueue(
        self,
        content: str,
        content_type: str = "markdown",
        source_session_id: str | None = None,
        *,
        routing: Optional["RoutingTable"] = None,
        header_title: str | None = None,
    ) -> dict:
        """Enqueue an IPC message for later delivery.

        Only stores the raw message payload. Target resolution (chat_id,
        open_id, session_id) and card building are deferred to drain time,
        because the routing table may change between enqueue and drain
        (e.g. user does /clear or /resume).
        """
        self._pending_messages.append({
            "content": content,
            "content_type": content_type,
            "source_session_id": source_session_id,
            "header_title": header_title,
        })

        queue_size = len(self._pending_messages)
        logger.info(
            "IPC message enqueued (queue_size=%d, source=%s)",
            queue_size, source_session_id,
        )
        return {"sent": True, "status": "queued", "queue_size": queue_size}

    async def drain_pending(
        self,
        routing: Optional["RoutingTable"] = None,
    ) -> None:
        """Send all queued IPC messages.

        Target resolution happens at drain time to use the latest routing state.
        """
        if not self._pending_messages:
            return

        messages = self._pending_messages[:]
        self._pending_messages.clear()

        logger.info("Draining %d pending IPC message(s)", len(messages))
        for idx, msg_info in enumerate(messages):
            try:
                await self._deliver_single_message(
                    idx, len(messages), msg_info, routing=routing,
                )
            except Exception as e:
                logger.error(
                    "Failed to drain IPC message [%d]: %s", idx + 1, e, exc_info=True,
                )

    # ── Resolution helpers (called at drain time) ─────────────────────

    def _resolve_drain_chat_id(self, chats: dict) -> str | None:
        """Resolve the target chat_id for draining IPC messages.

        Only returns a chat_id when exactly one single-chat exists.
        Returns None if there are zero or multiple single chats (ambiguous).
        """
        single_chats = [
            chat_id for chat_id in chats
            if self._is_single_chat(chat_id)
        ]

        if len(single_chats) > 1:
            logger.warning(
                "Multiple single chats found (%d), cannot determine IPC drain target: %s",
                len(single_chats), single_chats,
            )
            return None

        if len(single_chats) == 1:
            return single_chats[0]

        return None

    def _resolve_first_open_id(
        self, open_ids: dict[str, str],
    ) -> tuple[str | None, str | None]:
        """Resolve the first open_id that has a non-empty session_id.

        Returns (open_id, session_id) or (None, None) if none found.
        """
        if not open_ids:
            return None, None

        for oid, sid in open_ids.items():
            if sid:
                return oid, sid

        logger.info(
            "_resolve_first_open_id: open_ids has %d entries but none with session_id",
            len(open_ids),
        )
        return None, None

    # ── Delivery helpers (called at drain time) ───────────────────────

    async def _deliver_single_message(
        self, idx: int, total: int, msg_info: dict,
        *, routing: Optional["RoutingTable"] = None,
    ) -> None:
        """Deliver a single IPC message with drain-time target resolution.

        Resolves the delivery target (chat_id, open_id) and builds the card
        at drain time using the latest routing state, ensuring correctness
        even if the routing table changed since enqueue.
        """
        content = msg_info["content"]
        content_type = msg_info["content_type"]
        source_session_id = msg_info.get("source_session_id")
        header_title = msg_info.get("header_title")

        # Resolve delivery target at drain time (latest routing state)
        chats = routing.chats if routing else {}
        open_ids = routing.open_ids if routing else {}

        chat_id = self._resolve_drain_chat_id(chats)
        open_id, _ = self._resolve_first_open_id(open_ids)

        target_id = chat_id or open_id or ""
        is_open_id = bool(open_id and not chat_id)

        # Resolve current_session_id for card footer
        current_session_id = ""
        if target_id:
            if is_open_id:
                current_session_id = self._get_routed_session_id(
                    "", open_id=target_id,
                ) or ""
            else:
                current_session_id = self._get_routed_session_id(target_id) or ""

        # Build card at drain time if cross-session notification
        card_json = None
        if source_session_id:
            card_json = build_ipc_notification_card(
                content,
                source_session_id,
                current_session_id,
                preferred_language=self._resolve_preferred_language(),
            )

        logger.info(
            "Draining IPC message [%d/%d]: target=%s, is_open_id=%s, "
            "source_session_id=%s, content_type=%s, content_preview=%r",
            idx + 1, total, target_id or "email_fallback",
            is_open_id, source_session_id, content_type, content[:80],
        )

        # Send via resolved target (chat_id or open_id)
        if target_id:
            msg_id = await self._send_message(
                target_id, content, content_type,
                card_json=card_json, header_title=header_title,
                is_open_id=is_open_id,
            )
            await self._write_to_session_history(
                target_id, content, source_session_id,
                message_id=msg_id, is_open_id=is_open_id,
            )
            return

        # Fallback: email notification when no target was resolved
        logger.info("No target resolved at drain time, falling back to email notification")
        await self._send_notification_by_email(
            content, content_type, source_session_id,
            current_session_id=current_session_id,
            header_title=header_title,
        )

    async def _send_message(
        self,
        target_id: str,
        content: str,
        content_type: str,
        *,
        card_json: dict | None = None,
        header_title: str | None = None,
        is_open_id: bool = False,
    ) -> str | None:
        """Send an IPC message to target_id (chat_id or open_id).

        Dispatches to the appropriate card_sender method based on target type.
        Returns the platform message_id on success, None on failure.
        """
        try:
            if is_open_id:
                logger.info("Sending IPC message to open_id=%s", target_id)
                msg_id = await self._card_sender.send_by_open_id(
                    target_id, content, "markdown",
                    card_json=card_json, header_title=header_title,
                )
            elif card_json:
                # Cross-session card already carries its own header; ignore header_title.
                logger.info("Sending IPC card to chat_id=%s", target_id)
                msg_id = await self._card_sender.send_card_json(target_id, card_json)
            else:
                logger.info("Sending IPC message to chat_id=%s (type=%s)", target_id, content_type)
                msg_id = await self._card_sender.send_im(
                    "", target_id, content, content_type=content_type,
                    header_title=header_title,
                )

            if msg_id:
                logger.info("Sent IPC message to %s (msg_id=%s)", target_id, msg_id)
            else:
                logger.warning("Failed to send IPC message to %s", target_id)
            return msg_id
        except Exception as e:
            logger.warning("Error sending IPC message to %s: %s", target_id, e)
            return None

    async def _inject_ipc_note(
        self,
        session: "RunningSession",
        content: str,
        source_session_id: str | None,
        *,
        label: str = "System Notification",
        message_id: str | None = None,
    ) -> None:
        """Build an IPC note and write it into a session's history.

        Common logic shared by chat-based, open_id-based, and default-session
        delivery paths. Uses inject_items for cross-session context and
        add_items for native IPC notifications.
        """
        prefix = (
            f"[Context from session {source_session_id}]"
            if source_session_id
            else f"[Siada Scheduled Notification — {label}]"
        )
        ipc_note: dict = {"role": "user", "content": f"{prefix}\n{content}"}

        if source_session_id:
            # Only attach message_id for cross-session context injection
            if message_id:
                ipc_note["message_id"] = message_id
            session.openai_session.inject_items(
                [ipc_note], source_session_id=source_session_id,
            )
        else:
            await session.openai_session.add_items([ipc_note])

    async def _send_notification_by_email(
        self, content: str, content_type: str,
        source_session_id: str | None = None,
        current_session_id: str = "",
        *,
        header_title: str | None = None,
    ) -> None:
        """Send IPC notification to configured email via Lark API.

        When source_session_id is provided, sends as a Feishu card with:
        1. Header title indicating cross-session notification
        2. Tip note explaining session routing behaviour
        3. Body with the actual message content
        """
        email = self._resolve_notify_email()
        if not email:
            logger.warning(
                "No target or notify_email configured, IPC message not delivered",
            )
            return

        try:
            card_json = None
            if source_session_id:
                card_json = build_ipc_notification_card(
                    content,
                    source_session_id,
                    current_session_id,
                    preferred_language=self._resolve_preferred_language(),
                )

            msg_id = await self._card_sender.send_by_email(
                email, content, content_type,
                card_json=card_json, header_title=header_title,
            )
            if msg_id:
                logger.info("IPC notification sent via email to %s (msg_id=%s)", email, msg_id)
            else:
                logger.warning("Failed to send IPC notification via email to %s", email)
        except Exception as e:
            logger.error("Error sending IPC notification by email: %s", e)

    async def _write_to_session_history(
        self, target_id: str, content: str, source_session_id: str | None,
        *, message_id: str | None = None, is_open_id: bool = False,
    ) -> None:
        """Write an IPC message into the current active session's history.

        Args:
            target_id: A chat_id or open_id used to resolve the session via routing.
            is_open_id: Whether target_id is an open_id (vs chat_id).
        """
        if is_open_id:
            session_id = self._get_routed_session_id("", open_id=target_id)
        else:
            session_id = self._get_routed_session_id(target_id)
        if not session_id:
            logger.debug("No session routed for target_id=%s, skipping history write", target_id)
            return

        session = self._get_session(session_id)
        if session is None or session.openai_session is None:
            logger.debug("No cached session for session_id=%s, skipping history write", session_id)
            return

        try:
            await self._inject_ipc_note(
                session, content, source_session_id, message_id=message_id,
            )
            logger.info(
                "Wrote IPC message to session %s (source=%s, message_id=%s)",
                session_id, source_session_id, message_id,
            )
        except Exception as e:
            logger.warning("Failed to write IPC message to session history: %s", e)


# ── Module-level helpers ──────────────────────────────────────────────


def build_ipc_notification_card(
    content: str,
    source_session_id: str,
    current_session_id: str = "",
    preferred_language: str | None = None,
) -> dict:
    """Build a Feishu card JSON v2 for cross-session IPC notification.

    Card layout:
    - Header: orange title "Cross-Session Message"
    - Body: message content (main focus)
    - Divider
    - Footer: session info + tip note (notation size, grey)
    """
    template = get_ipc_notification_card_template(preferred_language)

    # Build footer lines - all wrapped in blockquote for uniform background.
    # Keep the warning concise and explicit about reply behavior.
    footer_lines = [
        f"> <font color='purple'>**{template.switch_tip}**</font>",
        f"> <font color='purple'>**{template.stay_tip}**</font>",
        f"> **{template.source_label}:** `{source_session_id}`",
    ]
    if current_session_id:
        footer_lines.append(
            f"> **{template.current_label}:** `{current_session_id}`",
        )

    return {
        "schema": "2.0",
        "header": {
            "title": {
                "tag": "plain_text",
                "content": template.header_title,
            },
            "template": "orange",
        },
        "body": {
            "elements": [
                {"tag": "markdown", "content": content},
                {"tag": "hr"},
                {
                    "tag": "markdown",
                    "content": "\n".join(footer_lines),
                    "text_size": "notation",
                },
            ],
        },
    }
