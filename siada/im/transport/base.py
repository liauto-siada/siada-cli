"""Abstract base class for IM transport connections."""

import asyncio
import json
import logging
import platform
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from siada.im.models import IMMessage, IMResponse

logger = logging.getLogger("siada.im.transport")

# Max age (in seconds) for incoming messages. Messages older than this are dropped.
DEFAULT_MAX_MESSAGE_AGE = 180  # 3 minutes


def is_stale_event(raw_event: dict, max_age: float = DEFAULT_MAX_MESSAGE_AGE) -> bool:
    """Check if a raw Lark event is too old to process.

    Uses message.create_time (millisecond timestamp) to determine staleness.
    Returns True if the message is older than max_age seconds.
    """
    try:
        create_time_ms = raw_event.get("event", {}).get("message", {}).get("create_time", "")
        if not create_time_ms:
            return False  # no timestamp, allow through
        age = time.time() - float(create_time_ms) / 1000
        if age > max_age:
            event_id = raw_event.get("header", {}).get("event_id", "unknown")
            logger.warning(
                f"Stale message dropped (age={age:.0f}s, max={max_age:.0f}s): "
                f"event_id={event_id}"
            )
            return True
    except (ValueError, TypeError):
        pass  # invalid timestamp format, allow through
    return False


class LRUDedup:
    """Simple LRU-based deduplication cache with TTL.

    Shared by both DirectTransport and RelayTransport.
    """

    def __init__(self, maxsize: int = 2048, ttl: float = 300.0):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: dict[str, float] = {}

    def check_and_add(self, key: str) -> bool:
        """Return True if key is new (not duplicate), False if duplicate."""
        now = time.time()
        # Evict expired entries lazily
        if len(self._cache) >= self._maxsize:
            expired = [k for k, t in self._cache.items() if now - t > self._ttl]
            for k in expired:
                del self._cache[k]
        # Check if still over max
        if len(self._cache) >= self._maxsize:
            oldest_key = min(self._cache, key=self._cache.get)
            del self._cache[oldest_key]

        if key in self._cache and now - self._cache[key] < self._ttl:
            return False  # duplicate
        self._cache[key] = now
        return True  # new


class LarkNotificationMixin:
    """Mixin providing Lark notification with device/version info.

    Subclasses must implement:
      - _get_notify_email() -> email address or None
      - _get_notification_lark_client() -> lark_oapi.Client instance
    """

    @staticmethod
    def _get_siada_version() -> str:
        """Get the current siada-cli version string."""
        try:
            from siada import __version__
            return __version__
        except Exception:
            return "unknown"

    def _get_notify_email(self) -> Optional[str]:
        """Return email for Lark notification, or None to skip."""
        raise NotImplementedError

    def _get_notification_lark_client(self):
        """Return a lark_oapi.Client for sending notifications."""
        raise NotImplementedError

    def _get_notify_language(self) -> Optional[str]:
        """Return preferred language for notifications, or None for default."""
        return None

    async def _send_lark_notification(self, message: str) -> None:
        """Send a Lark text message to the user via email.

        Appends a localized device/version footer to the message.
        Skipped silently if no email is configured.
        """
        email = self._get_notify_email()
        if not email:
            logger.debug("No notify email configured, skipping notification")
            return
        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
            from siada.im.feishu.notification_templates import get_notification_footer

            client = self._get_notification_lark_client()
            version = self._get_siada_version()
            device_info = f"{platform.node()} ({platform.system()} {platform.release()})"
            footer = get_notification_footer(
                self._get_notify_language(), device_info, version
            )
            full_message = f"{message}\n{footer}"
            content = json.dumps({"text": full_message})

            request = CreateMessageRequest.builder() \
                .receive_id_type("email") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(email)
                    .msg_type("text")
                    .content(content)
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(client.im.v1.message.create, request)
            if not response.success():
                logger.error(
                    f"Failed to send Lark notification: code={response.code}, "
                    f"msg={response.msg}"
                )
            else:
                logger.debug("Lark notification sent to user")
        except Exception as e:
            logger.error(f"Failed to send Lark notification: {e}")


class Transport(ABC):
    """Connection transport abstraction for IM platforms.

    Provides a unified interface for different connection modes:
    - RelayTransport: connects to siada relay server via WebSocket
    - DirectTransport: connects directly to IM platform (e.g. Lark WS SDK)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the server."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection and cleanup resources."""
        ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[IMMessage]:
        """Async iterator that yields incoming messages."""
        ...

    @abstractmethod
    async def send(self, response: IMResponse) -> Optional[str]:
        """Send a response message back through the transport.

        Returns the platform message_id on success, None on failure.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the transport connection is healthy."""
        ...
