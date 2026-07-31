"""Tests for resolve_sender_names in LarkRelayAdapter.

Verifies:
- Sender name resolution is triggered when resolve_sender_names=True
- Resolution is skipped when resolve_sender_names=False
- Positive cache: successful results are cached within TTL
- Negative cache: failed results are cached to avoid repeated requests
- Cache expiry: entries are refreshed after TTL expires
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from siada.im.adapter.feishu import LarkRelayAdapter


def _make_raw_event(
    sender_open_id: str = "ou_test123",
    text: str = "hello",
    chat_id: str = "oc_chat1",
    event_id: str = "ev_001",
) -> dict:
    """Build a minimal raw Lark event v2 dict for testing."""
    return {
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "create_time": str(int(time.time() * 1000)),
        },
        "event": {
            "message": {
                "message_id": "msg_001",
                "message_type": "text",
                "content": '{"text": "' + text + '"}',
                "chat_id": chat_id,
                "chat_type": "p2p",
                "create_time": str(int(time.time() * 1000)),
            },
            "sender": {
                "sender_id": {
                    "open_id": sender_open_id,
                    "user_id": "user_abc",
                    "union_id": "on_union1",
                },
                "sender_type": "user",
            },
        },
    }


class TestResolveSenderNames:
    """Test resolve_sender_names feature in relay adapter."""

    @pytest.mark.asyncio
    async def test_resolve_sender_names_enabled(self):
        """When enabled, adapter calls _resolve_sender_name and populates fields."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        with patch.object(
            adapter, "_resolve_sender_name", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = ("张三", "Zhang San")

            raw = _make_raw_event(sender_open_id="ou_sender1")
            msg = await adapter.parse_event(raw)

            assert msg is not None
            assert msg.sender_name == "张三"
            assert msg.sender_en_name == "Zhang San"
            mock_resolve.assert_called_once_with("ou_sender1")

    @pytest.mark.asyncio
    async def test_resolve_sender_names_disabled(self):
        """When disabled, adapter skips _resolve_sender_name entirely."""
        adapter = LarkRelayAdapter(resolve_sender_names=False)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        with patch.object(
            adapter, "_resolve_sender_name", new_callable=AsyncMock
        ) as mock_resolve:
            raw = _make_raw_event(sender_open_id="ou_sender1")
            msg = await adapter.parse_event(raw)

            assert msg is not None
            assert msg.sender_name is None
            assert msg.sender_en_name is None
            mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_positive_cache_hit(self):
        """Successful resolution result is served from cache on next call."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        # Pre-populate the cache with a positive entry
        adapter._sender_cache["ou_cached"] = ("李四", "Li Si", time.time())

        with patch.object(
            adapter, "_get_lark_client"
        ) as mock_client:
            raw = _make_raw_event(sender_open_id="ou_cached")
            msg = await adapter.parse_event(raw)

            assert msg.sender_name == "李四"
            assert msg.sender_en_name == "Li Si"
            # Should not have called the API since cache is valid
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_negative_cache_prevents_retry(self):
        """After a failure, negative cache prevents API call within TTL."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        # Pre-populate with a negative cache entry (None, None, recent timestamp)
        adapter._sender_cache["ou_failed"] = (None, None, time.time())

        with patch.object(
            adapter, "_get_lark_client"
        ) as mock_client:
            raw = _make_raw_event(sender_open_id="ou_failed")
            msg = await adapter.parse_event(raw)

            assert msg.sender_name is None
            assert msg.sender_en_name is None
            # API should NOT be called because negative cache is still valid
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_negative_cache_expires_and_retries(self):
        """After TTL expires, a previously failed open_id is retried."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"
        adapter._sender_cache_ttl = 1  # 1 second for fast test

        # Expired negative cache entry
        adapter._sender_cache["ou_retry"] = (None, None, time.time() - 2)

        with patch.object(
            adapter, "_resolve_sender_name", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = ("王五", "Wang Wu")

            raw = _make_raw_event(sender_open_id="ou_retry")
            msg = await adapter.parse_event(raw)

            assert msg.sender_name == "王五"
            assert msg.sender_en_name == "Wang Wu"
            mock_resolve.assert_called_once_with("ou_retry")

    @pytest.mark.asyncio
    async def test_resolve_failure_caches_negative_entry(self):
        """When API call fails, a negative entry is cached."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        # Mock _get_lark_client to raise an exception
        with patch.object(
            adapter, "_get_lark_client", side_effect=RuntimeError("no creds")
        ):
            name, en_name = await adapter._resolve_sender_name("ou_error")

            assert name is None
            assert en_name is None
            # Negative cache entry should have been written
            cached = adapter._sender_cache.get("ou_error")
            assert cached is not None
            assert cached[0] is None  # name
            assert cached[1] is None  # en_name
            assert cached[2] > 0  # timestamp

    @pytest.mark.asyncio
    async def test_empty_open_id_returns_none(self):
        """Empty open_id should return (None, None) without cache write."""
        adapter = LarkRelayAdapter(resolve_sender_names=True)
        adapter._app_id = "app_id"
        adapter._app_secret = "app_secret"

        name, en_name = await adapter._resolve_sender_name("")
        assert name is None
        assert en_name is None
        assert "" not in adapter._sender_cache
