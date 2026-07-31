"""Lark adapters for relay and direct modes.

- LarkRelayAdapter: Lark event parsing + HTTP API sending via lark-oapi SDK (relay mode)
- LarkDirectAdapter: Lark event parsing + HTTP API sending via lark-oapi SDK (direct mode)

Both adapters share the same send logic (im.v1.message.create via lark-oapi).
LarkRelayAdapter receives credentials dynamically from Gateway auth,
while LarkDirectAdapter reads them from DirectTransportConfig.
"""

import asyncio
import json
import logging
import uuid
from abc import abstractmethod
from typing import Optional

from siada.im.adapter.base import IMAdapter
from siada.im.feishu.mention import (
    check_bot_mentioned,
    extract_mention_targets,
    normalize_mentions,
)
from siada.im.feishu.card_sender import build_markdown_card
from siada.im.models import IMMessage, IMResponse, FeishuMediaKey

logger = logging.getLogger("siada.im.lark")
logger.setLevel(logging.DEBUG)


# ── Shared base for Lark adapters ─────────────────────────────────────────────


class _LarkAdapterBase(IMAdapter):
    """Shared logic for all Lark adapters (relay & direct).

    Consolidates content parsing, post text extraction, send payload
    building, and the lark-oapi send_message flow that are identical
    across relay / direct modes.

    Subclasses must implement:
    - _get_lark_client()
    - parse_event()
    """

    @property
    def platform_name(self) -> str:
        return "lark"

    @abstractmethod
    def _get_lark_client(self):
        """Return a lark-oapi Client instance (lazy-created by subclass)."""
        ...

    # ── Content parsing ───────────────────────────────────────────────

    def _parse_content(self, raw_content: str, msg_type: str) -> str:
        """Parse message content based on message type."""
        try:
            if msg_type == "text":
                data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                return data.get("text", str(raw_content)) if isinstance(data, dict) else str(raw_content)

            elif msg_type == "post":
                data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                return self._extract_post_text(data)

            elif msg_type in ("image", "file", "audio", "video", "sticker"):
                data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                file_key = data.get("image_key") or data.get("file_key") or ""
                return f"[{msg_type}: {file_key}]"

            elif msg_type == "interactive":
                return "[interactive card]"

            else:
                return str(raw_content)

        except (json.JSONDecodeError, TypeError):
            return str(raw_content)

    def _extract_post_text(self, data: dict) -> str:
        """Extract plain text from Lark post (rich text) content.

        Supports both formats:
          locale-wrapped: {"zh_cn": {"title": "", "content": [[...]]}}
          direct (no locale): {"title": "", "content": [[...]]}
        """
        parts = []
        # Detect format: if "content" is a list at top level, it's the direct format
        if isinstance(data.get("content"), list):
            locale_items = [data]
        else:
            locale_items = [v for v in data.values() if isinstance(v, dict)]

        for locale_data in locale_items:
            title = locale_data.get("title", "")
            if title:
                parts.append(title)
            for line in locale_data.get("content", []):
                for element in line:
                    tag = element.get("tag", "")
                    if tag == "text":
                        parts.append(element.get("text", ""))
                    elif tag == "a":
                        parts.append(element.get("text", element.get("href", "")))
                    elif tag == "at":
                        parts.append(f"@{element.get('user_name', element.get('user_id', ''))}")
            break  # Use first locale only
        return "\n".join(parts) if parts else str(data)

    def _extract_feishu_media_keys(
        self, raw_content: str, msg_type: str
    ) -> list[FeishuMediaKey]:
        """Extract FeishuMediaKey objects from raw Feishu message content.

        Delegates to siada.im.feishu.media.extract_media_keys_from_message
        and wraps each (key, resource_type) pair into a FeishuMediaKey.
        Videos, audio and media message types are skipped automatically.
        """
        try:
            from siada.im.feishu.media import extract_media_keys_from_message

            pairs = extract_media_keys_from_message(raw_content, msg_type)
            return [
                FeishuMediaKey(key=k, resource_type=rt, msg_type=msg_type)
                for k, rt in pairs
            ]
        except Exception as exc:
            logger.info(
                "Failed to extract media keys from message (type=%s): %s",
                msg_type, exc,
            )
            return []

    # ── Send logic ────────────────────────────────────────────────────

    def _build_send_payload(self, msg: IMResponse) -> tuple[str, str]:
        """Build Lark API send payload from IMResponse.

        Returns:
            (msg_type, content_json_string)
        """
        if msg.content_type == "markdown":
            card_json = build_markdown_card(
                msg.content,
                header_title=msg.header_title,
                header_template=msg.header_template or "blue",
            )
            return "interactive", json.dumps(card_json)
        elif msg.content_type == "interactive":
            return "interactive", msg.content
        else:
            return "text", json.dumps({"text": msg.content})

    async def send_message(self, chat_id: str, msg: IMResponse) -> Optional[str]:
        """Send message via lark-oapi SDK (im.v1.message.create).

        Returns the message_id on success, None on failure.
        """
        if not chat_id:
            logger.warning(f"Cannot send message: no chat_id for {msg.request_id}")
            return None

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )

            client = self._get_lark_client()
            content_type, content_body = self._build_send_payload(msg)

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(content_type)
                    .content(content_body)
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)

            if not response.success():
                logger.error(
                    f"Lark send failed: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return None

            msg_id = response.data.message_id if response.data else None
            logger.debug(f"Message sent to {chat_id}, message_id={msg_id}")
            return msg_id

        except ImportError:
            logger.error("lark-oapi is required for send_message")
            return None
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return None

    # ── Sender name resolution (shared by relay & direct) ─────────────

    async def _resolve_sender_name(self, open_id: str) -> tuple[Optional[str], Optional[str]]:
        """Resolve user display name and en_name via lark-oapi SDK with TTL cache.

        Uses client.contact.v3.user.get() for type-safe API access.
        Requires subclass to initialize _sender_cache and _sender_cache_ttl.

        Negative caching: on failure, stores (None, None, timestamp) so that
        the same open_id won't be retried until TTL expires.

        Returns:
            (display_name, en_name) tuple
        """
        if not open_id:
            return None, None

        # Check cache: stored as (name, en_name, timestamp)
        # Negative cache entries have name=None, en_name=None
        import time
        now = time.time()
        cached = self._sender_cache.get(open_id)
        if cached and len(cached) >= 3 and now - cached[2] < self._sender_cache_ttl:
            return cached[0], cached[1]

        try:
            from lark_oapi.api.contact.v3 import GetUserRequest

            client = self._get_lark_client()
            id_type = "open_id" if open_id.startswith("ou_") else (
                "union_id" if open_id.startswith("on_") else "user_id"
            )

            request = GetUserRequest.builder() \
                .user_id(open_id) \
                .user_id_type(id_type) \
                .build()

            response = await asyncio.to_thread(client.contact.v3.user.get, request)

            if response.success() and response.data and response.data.user:
                user = response.data.user
                name = getattr(user, "name", None) or getattr(user, "en_name", None)
                en_name = getattr(user, "en_name", None)
                logger.info(
                    f"Lark contact/v3/users resolved for {open_id}: "
                    f"name={name}, en_name={en_name}"
                )
                self._sender_cache[open_id] = (name, en_name, now)
                return name, en_name
            else:
                logger.info(
                    f"Lark contact/v3/users for {open_id}: "
                    f"code={response.code}, msg={response.msg}"
                )
                # Negative cache: avoid retrying within TTL
                self._sender_cache[open_id] = (None, None, now)
                return None, None

        except Exception as e:
            logger.debug(f"Failed to resolve sender name for {open_id}: {e}")
            # Negative cache: avoid retrying within TTL
            self._sender_cache[open_id] = (None, None, now)
            return None, None


# ── Relay adapter ─────────────────────────────────────────────────────────────


class LarkRelayAdapter(_LarkAdapterBase):
    """Lark adapter for relay mode - parses raw Lark event v2 dicts.

    In the new Gateway protocol, the Gateway forwards raw Lark events
    without pre-parsing. This adapter parses them the same way as
    LarkDirectAdapter. After Gateway auth, app_id/app_secret are set
    to enable sending messages via Lark HTTP API (lark-oapi SDK).
    """

    def __init__(
        self,
        bot_open_id: Optional[str] = None,
        resolve_sender_names: bool = True,
    ):
        """Initialize with optional bot open_id for mention detection.

        Args:
            bot_open_id: Bot's open_id (ou_xxx), set after Gateway auth.
            resolve_sender_names: Whether to resolve sender display names
                via Lark contact API (same behavior as direct mode).
        """
        self._bot_open_id = bot_open_id
        self._resolve_sender_names = resolve_sender_names
        self._app_id: Optional[str] = None
        self._app_secret: Optional[str] = None
        # Sender name cache: {open_id: (name, en_name, timestamp)}
        self._sender_cache: dict[str, tuple[str, str, float]] = {}
        self._sender_cache_ttl: float = 600  # 10 min
        # Lazy-initialized lark SDK client
        self._lark_client = None

    def set_bot_open_id(self, bot_open_id: str) -> None:
        """Set bot open_id after Gateway auth returns credentials.

        Only overwrites the stored value when a non-empty id is provided.
        This protects against a reconnect whose auth_ok transiently omits
        bot_open_id from wiping out a previously valid value (which would
        silently break group @bot detection).
        """
        if not bot_open_id:
            logger.warning(
                "set_bot_open_id called with empty bot_open_id; "
                "keeping existing value (%s). Group @bot detection requires "
                "the Gateway to return bot_open_id in auth_ok.",
                self._bot_open_id,
            )
            return
        self._bot_open_id = bot_open_id


    def set_lark_credentials(self, app_id: str, app_secret: str) -> None:
        """Set Lark app credentials after Gateway auth.

        This enables send_message() to call Lark HTTP API via lark-oapi SDK.
        """
        self._app_id = app_id
        self._app_secret = app_secret
        # Reset cached client so it rebuilds with new credentials
        self._lark_client = None
        logger.info(f"LarkRelayAdapter credentials set, app_id={app_id}")

    def _get_lark_client(self):
        """Get or create a cached lark-oapi Client instance."""
        if self._lark_client is not None:
            return self._lark_client

        if not self._app_id or not self._app_secret:
            raise RuntimeError(
                "Lark credentials not set. "
                "Call set_lark_credentials() after Gateway auth."
            )

        import lark_oapi as lark

        self._lark_client = lark.Client.builder() \
            .app_id(self._app_id) \
            .app_secret(self._app_secret) \
            .domain(lark.FEISHU_DOMAIN) \
            .build()
        return self._lark_client

    async def parse_event(self, raw: dict) -> Optional[IMMessage]:
        """Parse raw Lark event v2 dict into IMMessage.

        The raw dict has the same structure as DirectTransport events:
        {
            "header": {"event_id": ..., "event_type": "im.message.receive_v1", ...},
            "event": {"message": {...}, "sender": {...}}
        }
        """
        header = raw.get("header", {})
        event = raw.get("event", {})
        event_type = header.get("event_type", "")

        if event_type != "im.message.receive_v1":
            return None

        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})

        # Parse message content based on type
        msg_type = message.get("message_type", "text")
        raw_content = message.get("content", "")
        content = self._parse_content(raw_content, msg_type)

        # Handle mentions - use centralized mention module
        raw_mentions = message.get("mentions", [])
        bot_open_id = self._bot_open_id or ""

        # 1. Check if bot is mentioned (@_all also counts)
        mentioned_bot = check_bot_mentioned(raw_mentions, bot_open_id) if bot_open_id else False

        # 2. Normalize text: replace @_user_N placeholders, strip bot @
        content = normalize_mentions(content, raw_mentions, bot_open_id) if bot_open_id else content.strip()

        # 3. Extract non-bot mention targets
        mention_targets = extract_mention_targets(raw_mentions, bot_open_id) if bot_open_id else []

        # Resolve sender name (best-effort)
        sender_open_id = sender.get("open_id", "")
        sender_name = None
        sender_en_name = None
        if self._resolve_sender_names and sender_open_id:
            sender_name, sender_en_name = await self._resolve_sender_name(sender_open_id)

        # Extract media keys for image/file/post messages (video/audio are skipped)
        feishu_media_keys = self._extract_feishu_media_keys(raw_content, msg_type)

        return IMMessage(
            request_id=header.get("event_id", str(uuid.uuid4())),
            platform="lark",
            user_id=sender.get("user_id", ""),
            chat_id=message.get("chat_id", ""),
            chat_type="p2p" if message.get("chat_type") == "p2p" else "group",
            content_type=msg_type,
            content=content,
            timestamp=float(message.get("create_time", 0)) / 1000,
            raw=raw,
            message_id=message.get("message_id", ""),
            sender_name=sender_name,
            root_id=message.get("root_id") or None,
            thread_id=message.get("thread_id") if hasattr(message, "get") else None,
            parent_id=message.get("parent_id") or None,
            mentioned_bot=mentioned_bot,
            sender_en_name=sender_en_name,
            sender_open_id=sender_open_id,
            mentions=mention_targets,
            has_any_mention=len(raw_mentions) > 0,
            feishu_media_keys=feishu_media_keys,
        )


# ── Direct adapter ────────────────────────────────────────────────────────────


class LarkDirectAdapter(_LarkAdapterBase):
    """Lark adapter for direct mode with full Lark API interaction.

    Uses lark-oapi SDK for all API calls (auto token management).

    Handles:
    - Parsing raw Lark event v2 payloads into IMMessage
    - Sending replies via lark-oapi SDK (im.v1.message)
    - Sender name resolution with TTL cache
    - Bot mention detection
    """

    def __init__(self, config):
        """Initialize with DirectTransportConfig.

        Args:
            config: DirectTransportConfig instance
        """
        self._config = config
        self._bot_open_id: Optional[str] = None
        self._bot_name: Optional[str] = None
        # Sender name cache: {open_id: (name, en_name, timestamp)}
        self._sender_cache: dict[str, tuple[str, str, float]] = {}
        self._sender_cache_ttl: float = 600  # 10 min
        # Lazy-initialized lark SDK client
        self._lark_client = None

    def _get_lark_client(self):
        """Get or create a cached lark-oapi Client instance.

        The SDK handles tenant_access_token refresh internally.
        """
        if self._lark_client is not None:
            return self._lark_client

        import lark_oapi as lark

        domain = self._resolve_domain()
        self._lark_client = lark.Client.builder() \
            .app_id(self._config.app_id) \
            .app_secret(self._config.app_secret) \
            .domain(domain) \
            .timeout(self._config.http_timeout_ms / 1000) \
            .build()
        return self._lark_client

    def _resolve_domain(self) -> str:
        """Resolve Lark API domain for SDK."""
        import lark_oapi as lark
        if self._config.domain == "lark":
            return lark.LARK_DOMAIN
        elif self._config.domain in ("feishu", "lark_cn"):
            return lark.FEISHU_DOMAIN
        else:
            return self._config.domain.rstrip("/")

    def set_bot_info(self, bot_open_id: Optional[str], bot_name: Optional[str]) -> None:
        """Set bot identity info (called by DirectTransport after probe)."""
        self._bot_open_id = bot_open_id
        self._bot_name = bot_name

    async def parse_event(self, raw: dict) -> Optional[IMMessage]:
        """Parse Lark event v2 format into IMMessage.

        Handles text, post, image, file message types.
        Detects bot mentions and normalizes content.
        """
        header = raw.get("header", {})
        event = raw.get("event", {})
        event_type = header.get("event_type", "")

        if event_type != "im.message.receive_v1":
            return None

        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})

        # Parse message content based on type
        msg_type = message.get("message_type", "text")
        raw_content = message.get("content", "")
        content = self._parse_content(raw_content, msg_type)

        # Handle mentions - use centralized mention module
        raw_mentions = message.get("mentions", [])
        bot_open_id = self._bot_open_id or ""

        # 1. Check if bot is mentioned (@_all also counts)
        mentioned_bot = check_bot_mentioned(raw_mentions, bot_open_id) if bot_open_id else False

        # 2. Normalize text: replace @_user_N placeholders, strip bot @
        content = normalize_mentions(content, raw_mentions, bot_open_id) if bot_open_id else content.strip()

        # 3. Extract non-bot mention targets
        mention_targets = extract_mention_targets(raw_mentions, bot_open_id) if bot_open_id else []

        # Resolve sender name (best-effort)
        sender_open_id = sender.get("open_id", "")
        sender_name = None
        sender_en_name = None
        if self._config.resolve_sender_names and sender_open_id:
            sender_name, sender_en_name = await self._resolve_sender_name(sender_open_id)

        # Extract media keys for image/file/post messages (video/audio are skipped)
        feishu_media_keys = self._extract_feishu_media_keys(raw_content, msg_type)

        return IMMessage(
            request_id=header.get("event_id", str(uuid.uuid4())),
            platform="lark",
            user_id=sender.get("user_id", ""),
            chat_id=message.get("chat_id", ""),
            chat_type="p2p" if message.get("chat_type") == "p2p" else "group",
            content_type=msg_type,
            content=content,
            timestamp=float(message.get("create_time", 0)) / 1000,
            raw=raw,
            message_id=message.get("message_id", ""),
            sender_name=sender_name,
            root_id=message.get("root_id") or None,
            thread_id=message.get("thread_id") if hasattr(message, "get") else None,
            parent_id=message.get("parent_id") or None,
            mentioned_bot=mentioned_bot,
            sender_en_name=sender_en_name,
            sender_open_id=sender_open_id,
            mentions=mention_targets,
            has_any_mention=len(raw_mentions) > 0,
            feishu_media_keys=feishu_media_keys,
        )

# ── Convenience alias ─────────────────────────────────────────────────────────
# For backward compatibility with existing imports
LarkAdapter = LarkRelayAdapter


__all__ = ["LarkRelayAdapter", "LarkDirectAdapter", "LarkAdapter"]