"""DirectTransport - Direct WebSocket connection to Lark platform.

Uses Lark's long-connection SDK (lark-oapi WSClient), no public URL needed.
The SDK handles authentication, reconnection, and heartbeat internally.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, TYPE_CHECKING

from siada.im.models import IMMessage, IMResponse
from siada.im.transport.base import LRUDedup, Transport, is_stale_event

if TYPE_CHECKING:
    from siada.im.adapter.feishu import LarkDirectAdapter

logger = logging.getLogger("siada.im.direct")


@dataclass
class DirectTransportConfig:
    """Configuration for direct Lark WebSocket connection."""

    app_id: str
    app_secret: str
    domain: str = "lark"  # lark | lark_cn | custom URL
    encrypt_key: Optional[str] = None
    http_timeout_ms: int = 30000
    media_max_mb: int = 30
    resolve_sender_names: bool = True


class DirectTransport(Transport):
    """Direct WebSocket connection to Lark platform.

    Uses lark-oapi SDK's WSClient for persistent WS connection.
    The SDK manages authentication, heartbeat, and reconnection internally.

    Lifecycle:
      1. connect() -> fetch bot identity, start WS via SDK
      2. SDK dispatches events to _on_event callback
      3. receive() -> async iterator yielding IMMessage from queue
      4. send() -> delegate to adapter.send_message (Lark HTTP API)
      5. disconnect() -> stop WS client
    """

    def __init__(self, config: DirectTransportConfig, adapter: "LarkDirectAdapter"):
        self._config = config
        self._adapter = adapter
        self._message_queue: asyncio.Queue[IMMessage] = asyncio.Queue()
        self._dedup = LRUDedup(maxsize=2048, ttl=300)
        self._bot_open_id: Optional[str] = None
        self._bot_name: Optional[str] = None
        self._ws_client = None
        self._connected: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> None:
        """Establish direct connection to Lark platform."""
        self._loop = asyncio.get_running_loop()

        # Fetch bot identity first
        await self._fetch_bot_identity()

        # Share bot info with adapter
        self._adapter.set_bot_info(self._bot_open_id, self._bot_name)

        # Start WebSocket long connection via SDK
        await self._start_websocket()

        self._connected = True
        logger.info(
            f"DirectTransport connected, bot={self._bot_name} "
            f"(open_id={self._bot_open_id})"
        )

    async def _fetch_bot_identity(self) -> None:
        """Fetch bot info via Lark API to get open_id and name.

        Uses raw HTTP request since lark_oapi may not include the bot module.
        """
        try:
            import lark_oapi as lark

            client = self._get_lark_client()

            # Use BaseRequest (raw mode) since lark_oapi may not include the bot module
            request: lark.BaseRequest = lark.BaseRequest.builder() \
                .http_method(lark.HttpMethod.GET) \
                .uri("/open-apis/bot/v3/info") \
                .token_types({lark.AccessTokenType.TENANT}) \
                .build()

            response: lark.BaseResponse = await asyncio.to_thread(client.request, request)

            if response.success():
                import json
                data = json.loads(str(response.raw.content, lark.UTF_8))
                bot = data.get("bot", {})
                self._bot_open_id = bot.get("open_id", "")
                self._bot_name = bot.get("app_name", "")
                logger.info(f"Bot identity: {self._bot_name} ({self._bot_open_id})")
            else:
                logger.warning(
                    f"Failed to fetch bot info: {response.code} {response.msg}"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch bot identity: {e}")

    def _get_lark_client(self):
        """Create a lark-oapi Client instance."""
        import lark_oapi as lark

        domain = self._resolve_domain()
        return lark.Client.builder() \
            .app_id(self._config.app_id) \
            .app_secret(self._config.app_secret) \
            .domain(domain) \
            .timeout(self._config.http_timeout_ms / 1000) \
            .build()

    async def _start_websocket(self) -> None:
        """Start Lark WebSocket long connection via lark-oapi WSClient.

        The SDK handles:
        - Authentication with app_id/app_secret
        - Persistent WebSocket connection
        - Automatic reconnection
        - Internal heartbeat/ping-pong

        Note: The SDK's Client.start() uses a module-level event loop and blocks,
        so we must run it in a dedicated daemon thread with its own event loop
        to avoid conflicts with the main asyncio loop.
        """
        try:
            import lark_oapi as lark
            import lark_oapi.ws as lark_ws
            import threading

            event_handler = self._build_event_handler()

            self._ws_client = lark_ws.Client(
                self._config.app_id,
                self._config.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.DEBUG,
            )

            def _run_ws_client():
                """Run SDK WS client in a dedicated thread with its own event loop.

                The SDK uses a module-level asyncio loop internally.
                We patch it to use a fresh loop for this thread to avoid
                conflicts with the main application's event loop.
                """
                try:
                    import lark_oapi.ws.client as ws_module
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    # Patch the SDK's module-level loop reference
                    ws_module.loop = new_loop
                    logger.info("Starting Lark WS client in dedicated thread")
                    self._ws_client.start()
                except Exception as e:
                    logger.error(f"Lark WS client thread exited with error: {e}", exc_info=True)

            ws_thread = threading.Thread(
                target=_run_ws_client,
                name="lark-ws-client",
                daemon=True,
            )
            ws_thread.start()
            logger.info("Lark WS client thread started")

        except ImportError:
            raise ImportError(
                "lark-oapi package is required for DirectTransport. "
                "Install with: pip install lark-oapi"
            )

    def _build_event_handler(self):
        """Build the lark-oapi event handler for WS events."""
        import lark_oapi as lark

        handler = lark.EventDispatcherHandler.builder(
            encrypt_key=self._config.encrypt_key or "",
            verification_token="",
        ).register_p2_im_message_receive_v1(
            self._on_message_event
        ).build()

        return handler

    def _on_message_event(self, data) -> None:
        """Callback invoked by lark-oapi SDK when a message event arrives.

        This runs in the SDK's thread, so we schedule async work on our loop.
        The SDK callback signature is Callable[[P2ImMessageReceiveV1], None].
        """
        try:
            logger.debug(f"Received message event: {type(data)}")
            if self._loop and not self._loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    self._process_event(data), self._loop
                )
                # Add callback to catch errors from the scheduled coroutine
                def _on_done(f):
                    try:
                        exc = f.exception()
                        if exc:
                            logger.error(f"_process_event failed: {exc}", exc_info=exc)
                    except Exception as e:
                        logger.error(f"Error checking future result: {e}")
                future.add_done_callback(_on_done)
            else:
                logger.error(f"Cannot schedule event: loop={self._loop}, closed={self._loop.is_closed() if self._loop else 'N/A'}")
        except Exception as e:
            logger.error(f"Error scheduling event processing: {e}", exc_info=True)

    async def _process_event(self, event) -> None:
        """Process a Lark message event with dedup."""
        try:
            logger.info(f"_process_event started, event type: {type(event)}")

            # Extract event data - lark-oapi provides structured objects
            header = event.header if hasattr(event, "header") else None
            event_id = header.event_id if header else str(uuid.uuid4())
            logger.info(f"Event ID: {event_id}")

            if not self._dedup.check_and_add(event_id):
                logger.debug(f"Duplicate event skipped: {event_id}")
                return

            # Convert SDK event object to raw dict for adapter parsing
            raw_event = self._event_to_dict(event)

            # Drop stale messages to avoid processing outdated events
            if is_stale_event(raw_event):
                return

            msg = await self._adapter.parse_event(raw_event)
            if msg:
                await self._message_queue.put(msg)
                logger.info(f"Message enqueued: {msg.request_id}")
            else:
                logger.warning("parse_event returned None")

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)

    def _event_to_dict(self, event) -> dict:
        """Convert lark-oapi event object to dict for adapter parsing."""
        try:
            # Try to use the SDK's serialization
            if hasattr(event, "dict"):
                return event.dict()
            if hasattr(event, "to_dict"):
                return event.to_dict()

            # Manual extraction from SDK event structure
            header = event.header
            ev = event.event

            result = {
                "header": {
                    "event_id": header.event_id if header else "",
                    "event_type": header.event_type if header else "",
                    "create_time": header.create_time if header else "",
                    "token": header.token if header else "",
                    "app_id": header.app_id if header else "",
                    "tenant_key": header.tenant_key if header else "",
                },
                "event": {},
            }

            if ev:
                message = ev.message if hasattr(ev, "message") else None
                sender = ev.sender if hasattr(ev, "sender") else None

                if message:
                    msg_dict = {
                        "message_id": getattr(message, "message_id", ""),
                        "root_id": getattr(message, "root_id", ""),
                        "parent_id": getattr(message, "parent_id", ""),
                        "create_time": getattr(message, "create_time", ""),
                        "chat_id": getattr(message, "chat_id", ""),
                        "chat_type": getattr(message, "chat_type", ""),
                        "message_type": getattr(message, "message_type", ""),
                        "content": getattr(message, "content", ""),
                    }
                    # Extract mentions
                    mentions = getattr(message, "mentions", None)
                    if mentions:
                        msg_dict["mentions"] = [
                            {
                                "key": getattr(m, "key", ""),
                                "id": {
                                    "open_id": getattr(getattr(m, "id", None), "open_id", "")
                                    if hasattr(m, "id") else "",
                                    "user_id": getattr(getattr(m, "id", None), "user_id", "")
                                    if hasattr(m, "id") else "",
                                },
                                "name": getattr(m, "name", ""),
                            }
                            for m in mentions
                        ]
                    result["event"]["message"] = msg_dict

                if sender:
                    sender_id = getattr(sender, "sender_id", None)
                    result["event"]["sender"] = {
                        "sender_id": {
                            "open_id": getattr(sender_id, "open_id", "") if sender_id else "",
                            "user_id": getattr(sender_id, "user_id", "") if sender_id else "",
                            "union_id": getattr(sender_id, "union_id", "") if sender_id else "",
                        },
                        "sender_type": getattr(sender, "sender_type", ""),
                    }

            return result

        except Exception as e:
            logger.error(f"Error converting event to dict: {e}")
            return {"header": {}, "event": {}}

    async def receive(self) -> AsyncIterator[IMMessage]:
        """Async iterator that yields incoming IM messages."""
        while True:
            msg = await self._message_queue.get()
            yield msg

    async def send(self, response: IMResponse) -> None:
        """Send a response via Lark HTTP API (delegated to adapter)."""
        chat_id = response.chat_id or ""
        await self._adapter.send_message(chat_id, response)

    async def disconnect(self) -> None:
        """Stop WS client and cleanup."""
        logger.info("DirectTransport disconnecting...")
        self._connected = False
        if self._ws_client:
            try:
                # lark-oapi WS client stop
                if hasattr(self._ws_client, "stop"):
                    self._ws_client.stop()
            except Exception as e:
                logger.warning(f"Error stopping WS client: {e}")
            self._ws_client = None
        logger.info("DirectTransport disconnected")

    async def health_check(self) -> bool:
        """Check if transport is connected and healthy."""
        return self._connected and self._bot_open_id is not None

    def _resolve_domain(self) -> str:
        """Resolve Lark API domain."""
        import lark_oapi as lark
        if self._config.domain == "lark":
            return lark.LARK_DOMAIN
        elif self._config.domain == "lark_cn":
            return lark.FEISHU_DOMAIN
        else:
            return self._config.domain.rstrip("/")
