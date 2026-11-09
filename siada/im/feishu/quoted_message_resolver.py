"""Quoted/replied message content resolver for Feishu IM.

Fetches the content of the message being replied to (parent_id) and provides
it as context for the agent. Follows the OpenClaw pattern:
  1. Check local session history (zero API cost)
  2. Fallback: call Feishu im.v1.message.get API

Only resolves ONE level up (the immediate parent message).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("siada.im.lark.quoted_message")

# Maximum length for quoted message body (truncate beyond this)
MAX_QUOTED_LENGTH = 2000


@dataclass
class QuotedMessage:
    """Resolved quoted/replied message content."""

    message_id: str
    sender_id: Optional[str] = None  # open_id of the sender
    sender_name: Optional[str] = None  # display name if resolvable
    content: str = ""  # parsed plain-text content
    msg_type: str = "text"  # original message type
    # Raw JSON string from the Feishu API body.content field.
    # Populated only when resolved via API (not local history).
    # Allows callers to extract media keys (images, files) from the
    # quoted message without a second API round-trip.
    raw_content_json: Optional[str] = None


class QuotedMessageResolver:
    """Resolve quoted/replied message content for agent context.

    Uses a two-level strategy:
      Level 1: Search local session history (no API call)
      Level 2: Fetch via Feishu im.v1.message.get API (fallback)
    """

    def __init__(self, lark_client=None) -> None:
        """Initialize with an optional lark-oapi Client instance.

        Args:
            lark_client: A lark_oapi.Client instance for API calls.
                         If None, only local history lookup is available.
        """
        self._client = lark_client

    async def resolve(
        self,
        parent_id: Optional[str],
        *,
        session_history: Optional[list] = None,
    ) -> Optional[QuotedMessage]:
        """Resolve the quoted message content.

        Args:
            parent_id: The message_id of the parent (replied-to) message.
            session_history: Optional list of session history items to search locally.

        Returns:
            QuotedMessage with parsed content, or None if not resolvable.
        """
        if not parent_id:
            return None

        # Level 1: local session history lookup (zero API cost)
        if session_history:
            local = self._find_in_history(parent_id, session_history)
            if local:
                logger.debug(
                    "Quoted message resolved from local history: message_id=%s",
                    parent_id,
                )
                return local

        # Level 2: Feishu API fetch
        if self._client:
            result = await self._fetch_from_api(parent_id)
            if result:
                logger.debug(
                    "Quoted message resolved from API: message_id=%s, type=%s",
                    parent_id, result.msg_type,
                )
            return result

        logger.debug(
            "Cannot resolve quoted message: no client and not in history, "
            "message_id=%s",
            parent_id,
        )
        return None

    def _find_in_history(
        self, message_id: str, history: list,
    ) -> Optional[QuotedMessage]:
        """Search session history for a message matching the given message_id.

        NOTE: In the current architecture, only IPC-injected messages
        (cross-session context) have `message_id` stored in session history.
        Regular user/bot messages use standard OpenAI format without message_id.
        Therefore this lookup primarily serves IPC messages; normal reply
        resolution falls through to Level 2 (API fetch).

        Iterates backwards (most recent first) to find matching messages.
        """
        for item in reversed(history):
            item_msg_id = None
            content = None

            if isinstance(item, dict):
                # Check for message_id in metadata
                item_msg_id = item.get("message_id") or item.get("_message_id")
                if item_msg_id == message_id:
                    content = item.get("content", "")
                    if isinstance(content, list):
                        # Multi-part content: extract text parts
                        content = " ".join(
                            p.get("text", "") for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    return QuotedMessage(
                        message_id=message_id,
                        content=_sanitize_and_truncate(str(content)),
                        sender_name=item.get("sender_name"),
                    )

        return None

    async def _fetch_from_api(self, message_id: str) -> Optional[QuotedMessage]:
        """Call Feishu im.v1.message.get to fetch message content.

        Uses the lark-oapi SDK synchronous API in a thread pool to avoid
        blocking the event loop.
        """
        import asyncio

        try:
            result = await asyncio.to_thread(
                self._sync_fetch_message, message_id,
            )
            return result
        except Exception as e:
            logger.warning(
                "Failed to fetch quoted message via API: message_id=%s, error=%s",
                message_id, e,
            )
            return None

    def _sync_fetch_message(self, message_id: str) -> Optional[QuotedMessage]:
        """Synchronous Feishu API call to get message by ID."""
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import GetMessageRequest

        request = GetMessageRequest.builder() \
            .message_id(message_id) \
            .user_id_type("open_id") \
            .build()
        request.add_query("card_msg_content_type", "user_card_content")

        response = self._client.im.v1.message.get(request)

        if not response.success():
            logger.warning(
                "Feishu im.message.get failed: code=%s, msg=%s, message_id=%s",
                response.code, response.msg, message_id,
            )
            return None

        # Parse response - handle both single object and list response shapes
        data = response.data
        if data is None:
            return None

        items = getattr(data, "items", None)
        item = items[0] if items else data

        # Extract message fields
        msg_type = getattr(item, "msg_type", "text") or "text"
        body = getattr(item, "body", None)
        content_json = getattr(body, "content", "{}") if body else "{}"
        sender = getattr(item, "sender", None)
        sender_id = getattr(sender, "id", None) if sender else None

        # Parse content based on msg_type
        parsed_content = parse_message_content(msg_type, content_json)

        return QuotedMessage(
            message_id=message_id,
            sender_id=sender_id,
            content=_sanitize_and_truncate(parsed_content),
            msg_type=msg_type,
            # Preserve raw JSON so callers can extract media keys (images, files)
            # from the quoted message without a second API round-trip.
            raw_content_json=content_json,
        )


def parse_message_content(msg_type: str, content_json: str) -> str:
    """Parse Feishu message content JSON into plain text.

    Supports:
      - text: direct text extraction
      - post: rich text → plain text concatenation
      - image/file/audio/video/media: placeholder descriptions
      - interactive: card title/summary extraction
      - system/merge_forward: ignored
    """
    try:
        content = json.loads(content_json) if isinstance(content_json, str) else content_json
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(content, dict):
        return str(content) if content else ""

    if msg_type == "text":
        return content.get("text", "")

    if msg_type == "post":
        return _parse_post_content(content)

    if msg_type == "interactive":
        return _parse_interactive_content(content)

    if msg_type == "image":
        return "[图片]"

    if msg_type in ("file", "media"):
        file_name = content.get("file_name", "")
        return f"[文件: {file_name}]" if file_name else "[文件]"

    if msg_type == "audio":
        return "[语音消息]"

    if msg_type == "video":
        return "[视频]"

    if msg_type == "sticker":
        return "[表情包]"

    if msg_type in ("share_chat", "share_user"):
        return "[分享卡片]"

    if msg_type in ("system", "merge_forward"):
        return ""

    # Unknown type: try to extract any text field
    return content.get("text", "")


def _parse_post_content(content: dict) -> str:
    """Parse Feishu post (rich text) content into plain text.

    Post format: { "zh_cn": { "title": "...", "content": [[{tag, text}, ...]] } }
    or flat: { "title": "...", "content": [[...]] }
    """
    # Try localized content first (zh_cn > en_us > first available)
    post_body = None
    for locale in ("zh_cn", "en_us"):
        if locale in content:
            post_body = content[locale]
            break
    if post_body is None:
        # Try flat format
        if "content" in content:
            post_body = content
        else:
            # Try first available locale key
            for key, val in content.items():
                if isinstance(val, dict) and "content" in val:
                    post_body = val
                    break

    if not post_body:
        return content.get("title", "")

    parts: list[str] = []
    title = post_body.get("title", "")
    if title:
        parts.append(title)

    paragraphs = post_body.get("content", [])
    for paragraph in paragraphs:
        if not isinstance(paragraph, list):
            continue
        line_parts: list[str] = []
        for element in paragraph:
            if not isinstance(element, dict):
                continue
            tag = element.get("tag", "")
            if tag == "text":
                line_parts.append(element.get("text", ""))
            elif tag == "a":
                text = element.get("text", "")
                href = element.get("href", "")
                line_parts.append(f"{text}({href})" if href else text)
            elif tag == "at":
                line_parts.append(f"@{element.get('user_name', '用户')}")
            elif tag == "img":
                line_parts.append("[图片]")
            elif tag == "media":
                line_parts.append("[媒体]")
            elif tag == "emotion":
                line_parts.append(f"[{element.get('emoji_type', '表情')}]")
        if line_parts:
            parts.append("".join(line_parts))

    return "\n".join(parts)


def _extract_text_from_element(el: dict) -> str:
    """Extract plain text or markdown content from a card element dict."""
    if not isinstance(el, dict):
        return ""
    tag = el.get("tag")
    if tag == "markdown":
        return el.get("content", "")
    elif tag == "div":
        text_obj = el.get("text", {})
        if isinstance(text_obj, dict):
            return text_obj.get("content", "")
        elif isinstance(text_obj, str):
            return text_obj
    elif tag in ("text", "plain_text"):
        text_obj = el.get("text", el.get("content", ""))
        if isinstance(text_obj, str):
            return text_obj
        elif isinstance(text_obj, dict):
            return text_obj.get("content", "") or text_obj.get("text", "")
    else:
        # Fallback to check any standard text or content fields
        for field in ("text", "content"):
            val = el.get(field)
            if isinstance(val, str) and val:
                return val
            elif isinstance(val, dict):
                sub_val = val.get("content") or val.get("text")
                if isinstance(sub_val, str) and sub_val:
                    return sub_val
    return ""


def _parse_interactive_content(content: dict) -> str:
    """Parse interactive card content into a brief summary."""
    # Temporary log for debugging interactive card content
    logger.info("Parsing interactive card content: %s", content)

    # Try to extract title from top-level or header
    title = ""
    title_val = content.get("title")
    if isinstance(title_val, str):
        title = title_val
    elif isinstance(title_val, dict):
        title = title_val.get("content") or title_val.get("text", "")
    else:
        header = content.get("header", {})
        title_obj = header.get("title", {})
        title = title_obj.get("content", "") if isinstance(title_obj, dict) else ""

    # Try to extract elements from body or top-level elements list
    elements = []
    body = content.get("body")
    if isinstance(body, dict):
        elements = body.get("elements", [])
    elif isinstance(body, list):
        elements = body
    else:
        elements_val = content.get("elements")
        if isinstance(elements_val, list):
            elements = elements_val

    # Flatten nested elements lists recursively
    flat_elements = []
    def flatten(items):
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, list):
                flatten(item)
            elif isinstance(item, dict):
                flat_elements.append(item)
    flatten(elements)

    # Extract all non-empty text content from elements and join them with newlines
    body_parts = []
    for el in flat_elements:
        txt = _extract_text_from_element(el)
        if txt:
            txt_stripped = txt.strip()
            if txt_stripped and txt_stripped not in body_parts:  # Avoid duplicate text parts
                body_parts.append(txt_stripped)

    body_text = "\n".join(body_parts)

    if title and body_text:
        result = f"[卡片: {title}] {body_text}"
    elif title:
        result = f"[卡片: {title}]"
    elif body_text:
        result = f"[卡片] {body_text}"
    else:
        result = "[互动卡片]"

    # Temporary log for parsed result
    logger.info("Parsed interactive card content result: %s", result)
    return result


def _sanitize_and_truncate(text: str, max_len: int = MAX_QUOTED_LENGTH) -> str:
    """Sanitize and truncate quoted message content.

    Safety measures (following OpenClaw's sanitizeUntrustedJsonValue pattern):
      - Strip null bytes
      - Neutralize markdown code block fences (``` → ` ` `)
      - Truncate to max_len with indicator
    """
    if not text:
        return ""

    # Strip null bytes
    text = text.replace("\x00", "")

    # Neutralize markdown triple-backtick fences to prevent injection
    text = text.replace("```", "` ` `")

    # Truncate with indicator
    if len(text) > max_len:
        text = text[:max_len] + f"... [truncated, {len(text)} chars total]"

    return text
