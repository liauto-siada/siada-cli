"""Lark CardKit Streaming Card - real-time text output via card element updates.

Mirrors openclaw's streaming-card.ts implementation using CardKit v1 API:
  1. POST /cardkit/v1/cards                                    -> create card with streaming_mode=true
  2. POST /im/v1/messages                                      -> send card to chat
  3. PUT  /cardkit/v1/cards/{card_id}/elements/{element_id}/content -> update element text
  4. PATCH /cardkit/v1/cards/{card_id}/settings                -> close streaming mode

References:
  - https://open.feishu.cn/document/cardkit-v1/streaming-updates-openapi-overview
  - openclaw/extensions/lark/src/streaming-card.ts
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("siada.im.streaming_card")

# Throttle: max 10 updates/sec per card (Lark rate-limit)
DEFAULT_THROTTLE_MS = 100


def _truncate_summary(text: str, max_len: int = 50) -> str:
    """Truncate text for card summary display."""
    if not text:
        return ""
    clean = text.replace("\n", " ").strip()
    return clean if len(clean) <= max_len else clean[: max_len - 3] + "..."


def _resolve_api_base(domain: str) -> str:
    if domain == "lark":
        return "https://open.larksuite.com"
    elif domain in ("feishu", "lark_cn"):
        return "https://open.feishu.cn"
    else:
        return domain.rstrip("/")


def merge_streaming_text(previous: str, next_text: str) -> str:
    """Merge two text chunks, handling partial overlaps.

    Ported from openclaw's mergeStreamingText():
    - If next starts with previous, return next
    - If previous starts with next, return previous
    - Detect suffix/prefix overlap and merge
    - Fallback: concatenate
    """
    if not next_text:
        return previous
    if not previous or next_text == previous:
        return next_text
    if next_text.startswith(previous):
        return next_text
    if previous.startswith(next_text):
        return previous
    if next_text in previous:
        return previous
    if previous in next_text:
        return next_text

    # Merge partial overlaps, e.g. "这" + "这是" => "这是"
    max_overlap = min(len(previous), len(next_text))
    for overlap in range(max_overlap, 0, -1):
        if previous[-overlap:] == next_text[:overlap]:
            return previous + next_text[overlap:]

    # Fallback: append to avoid losing tokens
    return previous + next_text


@dataclass
class StreamingCardState:
    """Internal state for an active streaming card."""

    card_id: str
    message_id: str
    sequence: int
    current_text: str


class LarkStreamingCard:
    """Manages a single Lark streaming card session.

    Mirrors openclaw's LarkStreamingSession. Uses CardKit element-level API
    for fine-grained control over card content updates.

    Lifecycle:
      1. start()  -> create card entity (streaming_mode=true) + send to chat
      2. update() -> PUT element content (throttled, with text merging)
      3. close()  -> flush pending + close streaming_mode
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "lark",
        throttle_ms: int = DEFAULT_THROTTLE_MS,
        log_fn: Optional[callable] = None,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._throttle_ms = throttle_ms
        self._log = log_fn or logger.info

        self._state: Optional[StreamingCardState] = None
        self._closed = False
        self._last_update_time: float = 0.0
        self._pending_text: Optional[str] = None
        # Background task for fire-and-forget card updates
        self._inflight_task: Optional[asyncio.Task] = None

        # Token cache
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

        # Shared aiohttp session for connection reuse
        self._http_session = None

    # ── public API ──────────────────────────────────────────────────

    async def start(
        self,
        chat_id: str,
        initial_text: str = "⏳ Thinking...",
        header_title: Optional[str] = None,
        header_template: str = "blue",
    ) -> None:
        """Create a streaming card and send it to the chat."""
        if self._state:
            return

        import aiohttp

        self._http_session = aiohttp.ClientSession()

        api_base = _resolve_api_base(self._domain)
        token = await self._refresh_token()

        # Build card JSON with streaming_mode enabled
        card_json: dict = {
            "schema": "2.0",
            "config": {
                "streaming_mode": True,
                "summary": {"content": "[生成中...]"},
                "streaming_config": {
                    "print_frequency_ms": {"default": 50},
                    "print_step": {"default": 1},
                },
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": initial_text,
                        "element_id": "content",
                    }
                ],
            },
        }
        if header_title:
            card_json["header"] = {
                "title": {"tag": "plain_text", "content": header_title},
                "template": header_template,
            }

        # Step 1: Create card entity
        create_url = f"{api_base}/open-apis/cardkit/v1/cards"
        create_body = {
            "type": "card_json",
            "data": json.dumps(card_json),
        }
        async with self._http_session.post(
            create_url,
            json=create_body,
            headers=self._auth_headers(token),
        ) as resp:
            result = await resp.json()
            if result.get("code") != 0 or not result.get("data", {}).get("card_id"):
                raise RuntimeError(
                    f"Create streaming card failed: {result.get('code')} {result.get('msg')}"
                )
            card_id = result["data"]["card_id"]

        # Step 2: Send card message to chat
        card_content = json.dumps({"type": "card", "data": {"card_id": card_id}})
        send_url = f"{api_base}/open-apis/im/v1/messages"
        send_body = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": card_content,
        }
        async with self._http_session.post(
            send_url,
            json=send_body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"receive_id_type": "chat_id"},
        ) as resp:
            result = await resp.json()
            if result.get("code") != 0 or not result.get("data", {}).get("message_id"):
                raise RuntimeError(
                    f"Send streaming card failed: {result.get('code')} {result.get('msg')}"
                )
            message_id = result["data"]["message_id"]

        self._state = StreamingCardState(
            card_id=card_id,
            message_id=message_id,
            sequence=1,
            current_text="",
        )
        self._log(f"Streaming card started: card_id={card_id}, message_id={message_id}")

    async def update(self, text: str) -> None:
        """Incrementally update the card content (throttled, with text merging).

        Mirrors openclaw's LarkStreamingSession.update().
        """
        if not self._state or self._closed:
            return

        merged_input = merge_streaming_text(
            self._pending_text if self._pending_text is not None else self._state.current_text,
            text,
        )
        if not merged_input or merged_input == self._state.current_text:
            return

        # Throttle: skip if updated recently, but remember pending text
        now = time.time()
        if (now - self._last_update_time) * 1000 < self._throttle_ms:
            self._pending_text = merged_input
            return

        self._pending_text = None
        self._last_update_time = now

        # Serialize updates to preserve ordering
        merged_text = merge_streaming_text(self._state.current_text, merged_input)
        if not merged_text or merged_text == self._state.current_text:
            return
        self._state.current_text = merged_text

        # Fire-and-forget: don't block the stream consumer loop on HTTP I/O.
        # Cancel the previous inflight request since the new content supersedes it.
        if self._inflight_task and not self._inflight_task.done():
            self._inflight_task.cancel()
        self._inflight_task = asyncio.create_task(
            self._update_card_content(
                merged_text,
                on_error=lambda e: self._log(f"Update failed: {e}"),
            )
        )

    async def close(self, final_text: Optional[str] = None) -> None:
        """Flush pending text and close streaming mode.

        Mirrors openclaw's LarkStreamingSession.close().
        """
        if not self._state or self._closed:
            return
        self._closed = True

        # When final_text is explicitly provided, use it directly as the
        # authoritative final content instead of merging.  Merging can
        # cause duplication when the thinking prefix is included in both
        # pending and final texts but the answer portion differs.
        if final_text:
            text = final_text
        else:
            pending_merged = merge_streaming_text(
                self._state.current_text,
                self._pending_text if self._pending_text is not None else "",
            )
            text = pending_merged or self._state.current_text

        try:
            # Drain any inflight update before final flush
            if self._inflight_task and not self._inflight_task.done():
                try:
                    await self._inflight_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._inflight_task = None

            # Final content update if different from what's displayed
            if text and text != self._state.current_text:
                await self._update_card_content(text)
                self._state.current_text = text

            # Close streaming mode
            await self._close_streaming_mode(text)
        except Exception as e:
            logger.warning(f"Error during streaming card close: {e}")
        finally:
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()
                self._http_session = None

        self._log(f"Streaming card closed: card_id={self._state.card_id}")

    def is_active(self) -> bool:
        """Check if this streaming session is still active."""
        return self._state is not None and not self._closed

    @property
    def message_id(self) -> Optional[str]:
        return self._state.message_id if self._state else None

    # ── internal ────────────────────────────────────────────────────

    async def _update_card_content(
        self,
        text: str,
        on_error: Optional[callable] = None,
    ) -> None:
        """PUT /cardkit/v1/cards/{card_id}/elements/{element_id}/content

        Updates the markdown element content. Lark client auto-computes
        the diff and renders new characters with typewriter effect.
        """
        if not self._state or not self._http_session:
            return

        api_base = _resolve_api_base(self._domain)
        token = await self._refresh_token()
        self._state.sequence += 1

        url = (
            f"{api_base}/open-apis/cardkit/v1/cards/"
            f"{self._state.card_id}/elements/content/content"
        )
        body = {
            "content": text,
            "sequence": self._state.sequence,
            "uuid": f"s_{self._state.card_id}_{self._state.sequence}",
        }

        try:
            async with self._http_session.put(
                url,
                json=body,
                headers=self._auth_headers(token),
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    msg = f"Card update warning: {result.get('code')} {result.get('msg')}"
                    if on_error:
                        on_error(msg)
                    else:
                        logger.debug(msg)
        except Exception as e:
            if on_error:
                on_error(str(e))
            else:
                logger.debug(f"Card content update failed: {e}")

    async def _close_streaming_mode(self, text: str) -> None:
        """PATCH /cardkit/v1/cards/{card_id}/settings to close streaming mode.

        Matches openclaw's LarkStreamingSession.close() format:
        settings is a JSON-stringified config object, plus sequence and uuid.
        """
        if not self._state or not self._http_session:
            return

        api_base = _resolve_api_base(self._domain)
        token = await self._refresh_token()
        self._state.sequence += 1

        url = f"{api_base}/open-apis/cardkit/v1/cards/{self._state.card_id}/settings"
        body = {
            "settings": json.dumps({
                "config": {
                    "streaming_mode": False,
                    "summary": {"content": _truncate_summary(text)},
                },
            }),
            "sequence": self._state.sequence,
            "uuid": f"c_{self._state.card_id}_{self._state.sequence}",
        }

        try:
            async with self._http_session.patch(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logger.warning(
                        f"Close streaming mode warning: {result.get('code')} {result.get('msg')}"
                    )
        except Exception as e:
            logger.warning(f"Failed to close streaming mode: {e}")

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _refresh_token(self) -> str:
        """Refresh tenant_access_token with caching."""
        now = time.time()
        if self._token and now < self._token_expires_at - 600:
            return self._token

        api_base = _resolve_api_base(self._domain)

        import aiohttp

        session = self._http_session
        own_session = False
        if not session or session.closed:
            session = aiohttp.ClientSession()
            own_session = True

        try:
            url = f"{api_base}/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": self._app_id, "app_secret": self._app_secret}

            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    raise RuntimeError(
                        f"Token refresh failed: {result.get('code')} {result.get('msg')}"
                    )
                self._token = result["tenant_access_token"]
                self._token_expires_at = now + result.get("expire", 7200)
                return self._token
        finally:
            if own_session:
                await session.close()
