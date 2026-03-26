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


def _build_lark_client(app_id: str, app_secret: str, domain: str):
    """Create a lark-oapi Client instance with auto token management."""
    import lark_oapi as lark

    if domain == "lark":
        resolved_domain = lark.LARK_DOMAIN
    elif domain == "lark_cn":
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

    # ── Basic IM message ─────────────────────────────────────────────

    async def send_im(
        self,
        request_id: str,
        chat_id: str,
        content: str,
        content_type: str = "markdown",
        is_streaming: bool = False,
    ) -> None:
        """Send a message through the transport."""
        if not content:
            return
        resp = IMResponse(
            request_id=request_id,
            content_type=content_type,
            content=content,
            chat_id=chat_id,
            is_streaming=is_streaming,
        )
        await self._transport.send(resp)

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
