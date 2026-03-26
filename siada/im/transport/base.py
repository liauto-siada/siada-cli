"""Abstract base class for IM transport connections."""

import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator

from siada.im.models import IMMessage, IMResponse

logger = logging.getLogger("siada.im.transport")

# Max age (in seconds) for incoming messages. Messages older than this are dropped.
DEFAULT_MAX_MESSAGE_AGE = 300  # 5 minutes


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
    async def send(self, response: IMResponse) -> None:
        """Send a response message back through the transport."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the transport connection is healthy."""
        ...
