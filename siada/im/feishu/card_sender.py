"""LarkCardSender - Handles all Lark card API operations.

Provides methods to send, patch, and stream interactive cards,
as well as typing indicator management and basic IM message sending.
Uses lark-oapi SDK for direct mode API calls (auto token management).
"""

import asyncio
import json
import logging
from typing import Optional

from siada.im.models import IMMessage, IMResponse
from siada.im.streaming_card import LarkStreamingCard
from siada.im.transport.base import Transport
from siada.im.typing_indicator import LarkTypingIndicator, TypingState  # noqa: F401 (TypingState used by type hints)

logger = logging.getLogger("siada.im.lark.card_sender")


def build_markdown_card(
    content: str,
    *,
    header_title: str | None = None,
    header_template: str = "blue",
) -> dict:
    """Build a Feishu v2 interactive card containing markdown content.

    When ``header_title`` is provided, the card carries a header whose
    title becomes Lark's chat-list preview text. When ``header_title``
    is None, the card is built without a header — callers may pass a
    fallback title themselves if they want to preserve a legacy preview.
    """
    card: dict = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "body": {
            "elements": [{"tag": "markdown", "content": content}],
        },
    }
    if header_title:
        card["header"] = {
            "title": {"tag": "plain_text", "content": header_title},
            "template": header_template,
        }
    return card


def _build_lark_client(app_id: str, app_secret: str, domain: str):
    """Create a lark-oapi Client instance with auto token management."""
    import lark_oapi as lark

    if domain == "lark":
        resolved_domain = lark.LARK_DOMAIN
    elif domain in ("feishu", "lark_cn"):
        resolved_domain = lark.FEISHU_DOMAIN
    else:
        resolved_domain = domain.rstrip("/")

    return lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .domain(resolved_domain) \
        .build()


class LarkCardSender:
    """Encapsulates all Lark card/message sending and typing indicator logic."""

    def __init__(
        self,
        config: dict,
        mode: str,
        transport: Optional[Transport] = None,
    ):
        self._config = config
        self._mode = mode
        self._transport = transport

        # Typing indicator state
        self._typing_indicator: Optional[LarkTypingIndicator] = None
        self._typing_states: dict[str, TypingState] = {}

        # Cached lark SDK client (works for both direct and relay modes)
        self._lark_client = None

        # Dynamic credentials set externally (e.g. from relay Gateway auth)
        self._dynamic_app_id: Optional[str] = None
        self._dynamic_app_secret: Optional[str] = None
        self._dynamic_domain: str = "lark"

    def set_credentials(self, app_id: str, app_secret: str, domain: str = "lark") -> None:
        """Set Lark app credentials dynamically (e.g. from relay Gateway auth).

        This allows relay mode to use the same Lark API features as direct mode.
        Invalidates the cached lark client so it will be rebuilt with new credentials.
        """
        self._dynamic_app_id = app_id
        self._dynamic_app_secret = app_secret
        self._dynamic_domain = domain
        # Invalidate cached client so next call rebuilds with new credentials
        self._lark_client = None
        logger.info("LarkCardSender credentials set dynamically")

    def _get_lark_client(self):
        """Get or create a cached lark-oapi Client.

        Works for both direct and relay modes. The SDK handles
        tenant_access_token refresh internally.
        """
        if self._lark_client is not None:
            return self._lark_client

        app_id, app_secret, domain = self._resolve_credentials()
        if not app_id or not app_secret:
            return None

        self._lark_client = _build_lark_client(app_id, app_secret, domain)
        return self._lark_client

    def _resolve_credentials(self) -> tuple[str, str, str]:
        """Resolve (app_id, app_secret, domain) from dynamic or direct config.

        Prefers dynamic credentials (set via set_credentials from relay Gateway),
        falls back to direct config section.
        """
        if self._dynamic_app_id and self._dynamic_app_secret:
            return self._dynamic_app_id, self._dynamic_app_secret, self._dynamic_domain

        # Fallback: read from config["lark"]["direct"]
        lark_cfg = self._config.get("lark", {})
        direct_cfg = lark_cfg.get("direct", {})
        app_id = direct_cfg.get("app_id", "")
        app_secret = direct_cfg.get("app_secret", "")
        domain = direct_cfg.get("domain", "lark")
        return app_id, app_secret, domain

    def _has_credentials(self) -> bool:
        """Check if valid Lark credentials are available (from any source)."""
        app_id, app_secret, _ = self._resolve_credentials()
        return bool(app_id and app_secret)

    @property
    def transport(self) -> Optional[Transport]:
        return self._transport

    @transport.setter
    def transport(self, value: Transport) -> None:
        self._transport = value

    # ── Typing indicator ─────────────────────────────────────────────

    def create_typing_indicator(self) -> Optional[LarkTypingIndicator]:
        """Create a LarkTypingIndicator using the shared lark client."""
        client = self._get_lark_client()
        if not client:
            return None

        self._typing_indicator = LarkTypingIndicator(client=client)
        return self._typing_indicator

    async def add_typing(self, msg: IMMessage) -> None:
        """Add typing indicator to the user's message (direct mode only)."""
        if not self._typing_indicator or not msg.message_id:
            return
        try:
            create_time_ms = msg.timestamp * 1000 if msg.timestamp else None
            state = await self._typing_indicator.add(
                message_id=msg.message_id,
                message_create_time_ms=create_time_ms,
            )
            if state.reaction_id:
                self._typing_states[msg.chat_id] = state
        except Exception as e:
            logger.debug(f"Failed to add typing indicator: {e}")

    async def remove_typing(self, chat_id: str) -> None:
        """Remove typing indicator for a chat (direct mode only)."""
        state = self._typing_states.pop(chat_id, None)
        if not state or not self._typing_indicator:
            return
        try:
            await self._typing_indicator.remove(state)
        except Exception as e:
            logger.debug(f"Failed to remove typing indicator: {e}")

    async def add_reaction(self, message_id: str):
        """Add a typing/loading emoji reaction to a specific message.

        Unlike ``add_typing`` (which stores state in the shared per-chat dict),
        this returns the reaction state directly so the caller owns it. Use it
        for flows that run concurrently with the main agent turn (e.g. ``/btw``)
        and must not clobber the main turn's per-chat typing state. Returns the
        reaction state, or None if reactions are unavailable.
        """
        if not self._typing_indicator or not message_id:
            return None
        try:
            return await self._typing_indicator.add(message_id)
        except Exception as e:
            logger.debug(f"Failed to add reaction: {e}")
            return None

    async def remove_reaction(self, state) -> None:
        """Remove a reaction previously added via ``add_reaction``."""
        if not self._typing_indicator or not state:
            return
        try:
            await self._typing_indicator.remove(state)
        except Exception as e:
            logger.debug(f"Failed to remove reaction: {e}")

    # ── Basic IM message ─────────────────────────────────────────────

    async def send_im(
        self,
        request_id: str,
        chat_id: str,
        content: str,
        content_type: str = "markdown",
        is_streaming: bool = False,
        *,
        header_title: str | None = None,
        header_template: str | None = None,
    ) -> Optional[str]:
        """Send a message through the transport.

        Returns the platform message_id on success, None on failure or empty content.
        """
        if not content:
            return None
        resp = IMResponse(
            request_id=request_id,
            content_type=content_type,
            content=content,
            chat_id=chat_id,
            is_streaming=is_streaming,
            header_title=header_title,
            header_template=header_template,
        )
        return await self._transport.send(resp)

    # ── Card message operations (SDK-based) ──────────────────────────

    async def send_card_message(
        self,
        chat_id: str,
        title: str,
        content: str,
        header_template: str = "blue",
        icon: str = "",
    ) -> None:
        """Send a static interactive card message to Lark.

        Uses lark-oapi SDK when credentials are available.
        Falls back to plain markdown if no credentials.
        """

        client = self._get_lark_client()
        if not client:
            text = f"{icon} **{title}**\n\n{content}" if icon else f"**{title}**\n\n{content}"
            await self.send_im("", chat_id, text, content_type="markdown")
            return

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            header_title = f"{icon} {title}" if icon else title
            card_json = {
                "schema": "2.0",
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": header_title},
                    "template": header_template,
                },
                "body": {
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_json))
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    f"Send card failed: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
            else:
                logger.debug(f"Card message sent to {chat_id}: {title}")

        except Exception as e:
            logger.error(f"Failed to send card message: {e}")
            # Fallback to plain text
            text = f"{icon} **{title}**\n\n{content}" if icon else f"**{title}**\n\n{content}"
            await self.send_im("", chat_id, text, content_type="markdown")

    async def reply_card_message(
        self,
        message_id: str,
        title: str,
        content: str,
        header_template: str = "blue",
        icon: str = "",
        *,
        reply_in_thread: bool = False,
    ) -> Optional[str]:
        """Reply to an existing message with a static interactive card.

        Uses lark-oapi SDK's ``message.reply`` API so the card is threaded
        under the original message (e.g. the user's ``/btw`` command) instead
        of being posted as a standalone message. Falls back to a plain markdown
        reply when no credentials are available.

        Returns the platform message_id on success, None on failure.
        """
        client = self._get_lark_client()
        if not client:
            # Fallback: post as a standalone markdown message (no threading).
            text = f"{icon} **{title}**\n\n{content}" if icon else f"**{title}**\n\n{content}"
            return await self.send_im("", "", text, content_type="markdown")

        try:
            from lark_oapi.api.im.v1 import (
                ReplyMessageRequest,
                ReplyMessageRequestBody,
            )

            header_title = f"{icon} {title}" if icon else title
            card_json = {
                "schema": "2.0",
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": header_title},
                    "template": header_template,
                },
                "body": {
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }

            request = ReplyMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(json.dumps(card_json))
                    .msg_type("interactive")
                    .reply_in_thread(reply_in_thread)
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.reply, request)

            if not response.success():
                logger.error(
                    "reply_card_message failed: code=%s, msg=%s, log_id=%s",
                    response.code, response.msg, response.get_log_id(),
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.debug("Card reply sent to message %s (msg_id=%s)", message_id, msg_id)
            return msg_id

        except Exception as e:
            logger.error("Failed to reply with card message: %s", e)
            return None

    async def send_card_json(
        self, chat_id: str, card_json: dict,
    ) -> Optional[str]:
        """Send a pre-built card JSON to a chat and return its message_id.

        Uses lark-oapi SDK. Falls back to plain markdown extraction if
        no credentials are available.
        """
        client = self._get_lark_client()
        if not client:
            # Fallback: extract markdown content from card body
            elements = card_json.get("body", {}).get("elements", [])
            md_parts = [e["content"] for e in elements if e.get("tag") == "markdown"]
            fallback_text = "\n\n".join(md_parts) if md_parts else str(card_json)
            return await self.send_im("", chat_id, fallback_text, content_type="markdown")

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_json))
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    "send_card_json failed: code=%s, msg=%s, log_id=%s",
                    response.code, response.msg, response.get_log_id(),
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.info("Card JSON sent to %s (msg_id=%s)", chat_id, msg_id)
            return msg_id

        except Exception as e:
            logger.error("Failed to send card JSON: %s", e)
            return None

    async def send_card_get_id(
        self, chat_id: str, content: str, header_template: str = "blue",
    ) -> Optional[str]:
        """Send a static card and return its message_id for later PATCH updates.

        Uses lark-oapi SDK. Returns message_id on success, None on failure.
        Works for both direct and relay modes when credentials are available.
        """

        client = self._get_lark_client()
        if not client:
            return None

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            card_json = {
                "schema": "2.0",
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "🔧 Tool Execution"},
                    "template": header_template,
                },
                "body": {
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_json))
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    f"Send card failed: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.debug(f"Tool card sent: message_id={msg_id}")
            return msg_id

        except Exception as e:
            logger.error(f"Failed to send tool card: {e}")
            return None

    async def patch_card_content(
        self, message_id: str, content: str, header_template: str = "blue",
    ) -> None:
        """Update an existing card message content via lark-oapi SDK PATCH API."""
        client = self._get_lark_client()
        if not client:
            return

        try:
            from lark_oapi.api.im.v1 import (
                PatchMessageRequest,
                PatchMessageRequestBody,
            )

            card_json = {
                "schema": "2.0",
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "🔧 Tool Execution"},
                    "template": header_template,
                },
                "body": {
                    "elements": [
                        {"tag": "markdown", "content": content},
                    ],
                },
            }

            request = PatchMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(json.dumps(card_json))
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.patch, request)

            if not response.success():
                logger.debug(
                    f"Patch card failed: code={response.code}, "
                    f"msg={response.msg}"
                )

        except Exception as e:
            logger.debug(f"Failed to patch tool card: {e}")

    # ── Email-based message sending ──────────────────────────────────

    async def send_by_email(
        self,
        email: str,
        content: str,
        content_type: str = "text",
        *,
        card_json: dict | None = None,
        header_title: str | None = None,
    ) -> Optional[str]:
        """Send a message to a user by email address.

        Uses receive_id_type("email") instead of "chat_id".
        Supports text, markdown, and pre-built card JSON content types.

        Args:
            email: Recipient email address.
            content: Text or markdown content (ignored when card_json is provided).
            content_type: "text" or "markdown".
            card_json: Pre-built Feishu card JSON v2 dict. When provided,
                       sent as interactive card directly, ignoring content/content_type.

        Returns the platform message_id on success, None on failure.

        Note: RelayTransport._send_lark_notification() provides a similar
        capability for connection event notifications; this method is the
        shared card_sender equivalent for general-purpose email delivery.
        """
        client = self._get_lark_client()
        if not client:
            logger.warning(
                "Cannot send email notification: no Lark credentials available"
            )
            return None

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            # Pre-built card takes priority
            if card_json is not None:
                msg_type = "interactive"
                msg_content = json.dumps(card_json)
            elif content_type == "markdown":
                built_card = build_markdown_card(
                    content,
                    header_title=header_title or "📬 Siada Notification",
                    header_template="blue",
                )
                msg_type = "interactive"
                msg_content = json.dumps(built_card)
            else:
                msg_type = "text"
                msg_content = json.dumps({"text": content})

            request = CreateMessageRequest.builder() \
                .receive_id_type("email") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(email)
                    .msg_type(msg_type)
                    .content(msg_content)
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    f"Send email notification failed: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.info("Email notification sent to %s (msg_id=%s)", email, msg_id)
            return msg_id

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return None

    async def send_by_open_id(
        self,
        open_id: str,
        content: str,
        content_type: str = "text",
        *,
        card_json: dict | None = None,
        header_title: str | None = None,
    ) -> Optional[str]:
        """Send a message to a user by open_id.

        Uses receive_id_type("open_id") to deliver directly to a user's
        Lark chat. Supports text, markdown, and pre-built card JSON.

        Args:
            open_id: Recipient Lark open_id.
            content: Text or markdown content (ignored when card_json is provided).
            content_type: "text" or "markdown".
            card_json: Pre-built Feishu card JSON v2 dict. When provided,
                       sent as interactive card directly, ignoring content/content_type.

        Returns the platform message_id on success, None on failure.
        """
        client = self._get_lark_client()
        if not client:
            logger.warning(
                "Cannot send open_id notification: no Lark credentials available"
            )
            return None

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            # Pre-built card takes priority
            if card_json is not None:
                msg_type = "interactive"
                msg_content = json.dumps(card_json)
            elif content_type == "markdown":
                built_card = build_markdown_card(
                    content,
                    header_title=header_title or "📬 Siada Notification",
                    header_template="blue",
                )
                msg_type = "interactive"
                msg_content = json.dumps(built_card)
            else:
                msg_type = "text"
                msg_content = json.dumps({"text": content})

            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(open_id)
                    .msg_type(msg_type)
                    .content(msg_content)
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    f"Send open_id notification failed: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.info("Open_id notification sent to %s (msg_id=%s)", open_id, msg_id)
            return msg_id

        except Exception as e:
            logger.error(f"Failed to send open_id notification: {e}")
            return None

    # ── Streaming card factory ───────────────────────────────────────

    def create_streaming_card(self, chat_id: str) -> Optional[LarkStreamingCard]:
        """Create a LarkStreamingCard if credentials are available."""
        app_id, app_secret, domain = self._resolve_credentials()
        if not app_id or not app_secret:
            logger.warning("Cannot create streaming card: missing app_id/app_secret")
            return None

        return LarkStreamingCard(
            app_id=app_id,
            app_secret=app_secret,
            domain=domain,
            throttle_ms=200,
        )
