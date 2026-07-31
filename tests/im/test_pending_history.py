"""Tests for PendingHistoryBuffer - two-layer eviction strategy."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from siada.im.feishu.pending_history import (
    DEFAULT_HISTORY_LIMIT,
    HISTORY_CONTEXT_HEADER,
    CURRENT_MESSAGE_HEADER,
    MAX_HISTORY_KEYS,
    PendingHistoryBuffer,
    PendingHistoryEntry,
)


def _entry(sender: str = "Alice", content: str = "hello", msg_id: str = "m1") -> PendingHistoryEntry:
    return PendingHistoryEntry(sender=sender, content=content, timestamp=time.time(), message_id=msg_id)


class TestPendingHistoryBuffer:
    """Unit tests for PendingHistoryBuffer."""

    def test_record_and_consume(self) -> None:
        buf = PendingHistoryBuffer(limit=5)
        buf.record("g1", _entry("Alice", "hi", "m1"))
        buf.record("g1", _entry("Bob", "hey", "m2"))

        entries = buf.consume("g1")
        assert len(entries) == 2
        assert entries[0].sender == "Alice"
        assert entries[1].sender == "Bob"
        # After consume, should be empty
        assert buf.consume("g1") == []

    def test_fifo_eviction_per_key(self) -> None:
        buf = PendingHistoryBuffer(limit=3)
        for i in range(5):
            buf.record("g1", _entry("User", f"msg{i}", f"m{i}"))

        entries = buf.consume("g1")
        assert len(entries) == 3
        # Should keep last 3 (FIFO eviction)
        assert entries[0].content == "msg2"
        assert entries[1].content == "msg3"
        assert entries[2].content == "msg4"

    def test_lru_eviction_cross_key(self) -> None:
        buf = PendingHistoryBuffer(limit=10, max_keys=3)
        buf.record("g1", _entry("A", "a", "m1"))
        buf.record("g2", _entry("B", "b", "m2"))
        buf.record("g3", _entry("C", "c", "m3"))
        # Adding g4 should evict g1 (LRU)
        buf.record("g4", _entry("D", "d", "m4"))

        assert len(buf) == 3
        assert buf.peek_count("g1") == 0  # evicted
        assert buf.peek_count("g2") == 1
        assert buf.peek_count("g4") == 1

    def test_lru_refresh_on_record(self) -> None:
        buf = PendingHistoryBuffer(limit=10, max_keys=3)
        buf.record("g1", _entry("A", "a", "m1"))
        buf.record("g2", _entry("B", "b", "m2"))
        buf.record("g3", _entry("C", "c", "m3"))
        # Touch g1 again to refresh its LRU position
        buf.record("g1", _entry("A", "a2", "m4"))
        # Adding g4 should evict g2 (now oldest)
        buf.record("g4", _entry("D", "d", "m5"))

        assert buf.peek_count("g1") == 2  # refreshed, not evicted
        assert buf.peek_count("g2") == 0  # evicted
        assert buf.peek_count("g3") == 1
        assert buf.peek_count("g4") == 1

    def test_build_context_with_history(self) -> None:
        buf = PendingHistoryBuffer(limit=10)
        buf.record("g1", _entry("Alice", "what's up", "m1"))
        buf.record("g1", _entry("Bob", "not much", "m2"))

        result = buf.build_context("g1", "@bot help me")
        assert HISTORY_CONTEXT_HEADER in result
        assert CURRENT_MESSAGE_HEADER in result
        assert "[Alice]: what's up" in result
        assert "[Bob]: not much" in result
        assert "@bot help me" in result

    def test_build_context_without_history(self) -> None:
        buf = PendingHistoryBuffer(limit=10)
        result = buf.build_context("g1", "@bot help me")
        assert result == "@bot help me"

    def test_peek_count(self) -> None:
        buf = PendingHistoryBuffer(limit=10)
        assert buf.peek_count("g1") == 0
        buf.record("g1", _entry())
        buf.record("g1", _entry())
        assert buf.peek_count("g1") == 2

    def test_disabled_when_limit_zero(self) -> None:
        buf = PendingHistoryBuffer(limit=0)
        assert buf.disabled is True
        buf.record("g1", _entry())
        assert buf.peek_count("g1") == 0

    def test_consume_empty_group(self) -> None:
        buf = PendingHistoryBuffer(limit=10)
        assert buf.consume("nonexistent") == []

    def test_len(self) -> None:
        buf = PendingHistoryBuffer(limit=10)
        assert len(buf) == 0
        buf.record("g1", _entry())
        buf.record("g2", _entry())
        assert len(buf) == 2


class TestAccessControl:
    """Tests for LarkAccessControl group methods."""

    def test_per_group_config_with_wildcard(self) -> None:
        from siada.im.feishu.access_control import LarkAccessControl
        config = {"lark": {
            "access": {"group_policy": "open"},
            "groups": {
                "oc_special": {"require_mention": False, "history_limit": 50},
                "*": {"require_mention": True, "history_limit": 10},
            },
        }}
        ac = LarkAccessControl(config, "direct")
        assert ac.get_group_config("oc_special")["history_limit"] == 50
        assert ac.get_group_config("oc_other")["history_limit"] == 10
        # Non-matching without wildcard
        config2 = {"lark": {"access": {"group_policy": "open"}, "groups": {}}}
        ac2 = LarkAccessControl(config2, "direct")
        assert ac2.get_group_config("oc_any") is None



if TYPE_CHECKING:
    from siada.im.models import IMMessage


def _make_group_msg(
    chat_id: str = "oc_group1",
    user_id: str = "u1",
    content: str = "hello",
    sender_open_id: str | None = None,
) -> IMMessage:
    from siada.im.models import IMMessage
    return IMMessage(
        request_id="req1",
        platform="lark",
        user_id=user_id,
        chat_id=chat_id,
        chat_type="group",
        content_type="text",
        content=content,
        timestamp=time.time(),
        sender_open_id=sender_open_id,
    )