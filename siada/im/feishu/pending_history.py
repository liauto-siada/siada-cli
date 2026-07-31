"""PendingHistoryBuffer - Bounded in-memory buffer for non-triggered group messages.

Two-layer eviction strategy (reference: OpenClaw history.ts):
- Layer 1 (per-key FIFO): Each group keeps at most `limit` entries via deque(maxlen).
- Layer 2 (cross-key LRU): When tracked group count exceeds `max_keys`,
  evict least recently active groups entirely via OrderedDict.

Thread-safety: NOT thread-safe. Expected to be called from the
single asyncio event loop in LarkController.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

logger = logging.getLogger("siada.im.lark.pending_history")

# ── Constants ──────────────────────────────────────────────────────
# Siada uses smaller defaults than OpenClaw (50/1000) because
# agent context window is more limited than chat UI.

DEFAULT_HISTORY_LIMIT = 30  # Max pending entries per group (FIFO)
MAX_HISTORY_KEYS = 300  # Max tracked groups (LRU eviction)

HISTORY_CONTEXT_HEADER = "[Recent group chat context (not directed at you)]"
CURRENT_MESSAGE_HEADER = "[Current message (directed at you)]"


@dataclass
class PendingHistoryEntry:
    """A single pending history entry for a group chat message."""

    sender: str  # Display name or user_id fallback
    content: str  # Original message content
    timestamp: float  # Unix timestamp (seconds)
    message_id: str  # Feishu message_id, for dedup if needed


class PendingHistoryBuffer:
    """Bounded in-memory buffer for non-triggered group messages.

    Two-layer eviction strategy (reference: OpenClaw history.ts):
    - Layer 1 (per-key FIFO): Each group keeps at most ``limit`` entries.
      When full, oldest entries are auto-discarded by deque(maxlen).
    - Layer 2 (cross-key LRU): When tracked group count exceeds
      ``max_keys``, evict least recently active groups entirely.
    """

    def __init__(
        self,
        limit: int = DEFAULT_HISTORY_LIMIT,
        max_keys: int = MAX_HISTORY_KEYS,
    ):
        self._limit = limit
        self._max_keys = max_keys
        # OrderedDict preserves insertion order for LRU eviction.
        # Key = peer_id (chat_id for GROUP scope)
        # Value = deque of PendingHistoryEntry with maxlen=limit
        self._store: OrderedDict[str, deque[PendingHistoryEntry]] = OrderedDict()

    @property
    def disabled(self) -> bool:
        return self._limit <= 0

    def record(self, peer_id: str, entry: PendingHistoryEntry) -> None:
        """Record a pending history entry for a group.

        Layer 1: FIFO eviction via deque(maxlen).
        Layer 2: LRU eviction via OrderedDict when keys exceed max.
        """
        if self.disabled:
            return

        if peer_id in self._store:
            # Refresh LRU order: move to end (most recently active)
            self._store.move_to_end(peer_id)
            self._store[peer_id].append(entry)
        else:
            dq: deque[PendingHistoryEntry] = deque(maxlen=self._limit)
            dq.append(entry)
            self._store[peer_id] = dq

        logger.info(
            "record: peer_id=%s, sender=%s, content=%r, buffer_size=%d, tracked_groups=%d",
            peer_id, entry.sender, entry.content, len(self._store[peer_id]), len(self._store),
        )

        # Layer 2: evict oldest keys if exceeding max_keys
        while len(self._store) > self._max_keys:
            evicted_key, _ = self._store.popitem(last=False)  # Remove least recently used
            logger.info("LRU eviction: evicted peer_id=%s", evicted_key)

    def consume(self, peer_id: str) -> list[PendingHistoryEntry]:
        """Consume and clear all pending entries for a group.

        Returns the entries (may be empty). After this call,
        the group's history is removed from the buffer.
        """
        dq = self._store.pop(peer_id, None)
        if not dq:
            logger.info("consume: peer_id=%s, no pending entries", peer_id)
            return []
        entries = list(dq)
        logger.info(
            "consume: peer_id=%s, consumed %d entries, senders=%s",
            peer_id, len(entries), [e.sender for e in entries],
        )
        return entries

    def build_context(self, peer_id: str, current_message: str) -> str:
        """Build the full context string for agent injection.

        If there are pending entries, format as:
          [Recent group chat context (not directed at you)]
          [Alice]: some message
          [Bob]: another message

          [Current message (directed at you)]
          @bot help me with this

        If no pending entries, return current_message as-is.
        """
        entries = self.consume(peer_id)
        if not entries:
            logger.info("build_context: peer_id=%s, no pending history, returning current_message as-is", peer_id)
            return current_message

        lines = [f"[{e.sender}]: {e.content}" for e in entries]
        history_block = "\n".join(lines)

        result = (
            f"{HISTORY_CONTEXT_HEADER}\n"
            f"{history_block}\n\n"
            f"{CURRENT_MESSAGE_HEADER}\n"
            f"{current_message}"
        )
        logger.info(
            "build_context: peer_id=%s, injected %d pending entries, result_len=%d, result=%r",
            peer_id, len(entries), len(result), result,
        )
        return result

    def peek_count(self, peer_id: str) -> int:
        """Return the number of pending entries for a group (without consuming)."""
        dq = self._store.get(peer_id)
        return len(dq) if dq else 0

    def __len__(self) -> int:
        """Return number of tracked groups."""
        return len(self._store)