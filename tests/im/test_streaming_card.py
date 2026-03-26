"""Tests for LarkStreamingCard - fire-and-forget update and close drain logic.

Covers:
1. merge_streaming_text pure function
2. update() fires background task instead of blocking
3. update() cancels previous inflight task on new update
4. close() drains inflight task before final flush
5. close() with final_text bypasses merge
6. throttle skips HTTP but stores pending text
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from siada.im.streaming_card import (
    LarkStreamingCard,
    StreamingCardState,
    merge_streaming_text,
)


# ── merge_streaming_text tests ───────────────────────────────────────


class TestMergeStreamingText:
    def test_empty_previous_returns_next(self):
        assert merge_streaming_text("", "hello") == "hello"

    def test_empty_next_returns_previous(self):
        assert merge_streaming_text("hello", "") == "hello"

    def test_identical_returns_same(self):
        assert merge_streaming_text("abc", "abc") == "abc"

    def test_next_starts_with_previous(self):
        assert merge_streaming_text("hel", "hello world") == "hello world"

    def test_previous_starts_with_next(self):
        assert merge_streaming_text("hello world", "hello") == "hello world"

    def test_next_contains_previous(self):
        assert merge_streaming_text("world", "hello world") == "hello world"

    def test_previous_contains_next(self):
        assert merge_streaming_text("hello world", "world") == "hello world"

    def test_partial_overlap(self):
        assert merge_streaming_text("abc", "cde") == "abcde"

    def test_no_overlap_concatenates(self):
        assert merge_streaming_text("abc", "xyz") == "abcxyz"

    def test_chinese_overlap(self):
        assert merge_streaming_text("这", "这是") == "这是"


# ── LarkStreamingCard unit tests ─────────────────────────────────────


def _make_card() -> LarkStreamingCard:
    """Create a LarkStreamingCard with pre-set state (skip real HTTP start)."""
    card = LarkStreamingCard.__new__(LarkStreamingCard)
    card._app_id = "test"
    card._app_secret = "test"
    card._domain = "lark_cn"
    card._throttle_ms = 100
    card._log = lambda msg: None
    card._state = StreamingCardState(
        card_id="card_123",
        message_id="msg_456",
        sequence=1,
        current_text="",
    )
    card._closed = False
    card._last_update_time = 0.0
    card._pending_text = None
    card._inflight_task = None
    card._token = "fake_token"
    card._token_expires_at = time.time() + 7200
    card._http_session = AsyncMock()
    return card


class TestUpdateFireAndForget:
    """Verify update() creates background tasks instead of blocking."""

    @pytest.mark.asyncio
    async def test_update_creates_task_not_awaits_http(self):
        """update() should return immediately, with _inflight_task set."""
        card = _make_card()

        # Mock _update_card_content to be a slow coroutine
        call_count = 0
        original_done = asyncio.Event()

        async def _slow_update(text, on_error=None):
            nonlocal call_count
            call_count += 1
            await original_done.wait()

        card._update_card_content = _slow_update

        # Call update - should return immediately
        await card.update("hello world")

        # Task should be created but not yet completed
        assert card._inflight_task is not None
        assert not card._inflight_task.done()
        assert card._state.current_text == "hello world"

        # Let the background task finish
        original_done.set()
        await card._inflight_task
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_update_cancels_previous_inflight(self):
        """A new update should cancel the previous inflight task."""
        card = _make_card()

        gate = asyncio.Event()
        calls = []

        async def _slow_update(text, on_error=None):
            calls.append(text)
            await gate.wait()

        card._update_card_content = _slow_update

        # First update
        await card.update("first")
        first_task = card._inflight_task
        assert first_task is not None

        # Force throttle window to pass
        card._last_update_time = 0.0

        # Second update should cancel first
        await card.update("first second")
        assert card._inflight_task is not first_task

        # Yield control so the event loop processes the cancellation
        await asyncio.sleep(0)
        assert first_task.cancelled()

        # Let second complete
        gate.set()
        await card._inflight_task

    @pytest.mark.asyncio
    async def test_throttle_stores_pending_text(self):
        """When throttled, update should store pending text but not fire HTTP."""
        card = _make_card()
        card._last_update_time = time.time()  # just updated

        update_called = False

        async def _mock_update(text, on_error=None):
            nonlocal update_called
            update_called = True

        card._update_card_content = _mock_update

        await card.update("throttled text")

        assert card._pending_text is not None
        assert card._inflight_task is None
        assert not update_called


class TestCloseDrain:
    """Verify close() properly drains inflight tasks."""

    @pytest.mark.asyncio
    async def test_close_drains_inflight_before_final(self):
        """close() should await inflight task before sending final update."""
        card = _make_card()

        inflight_completed = False
        close_update_texts = []

        async def _slow_inflight(text, on_error=None):
            nonlocal inflight_completed
            await asyncio.sleep(0.01)
            inflight_completed = True

        async def _track_update(text, on_error=None):
            close_update_texts.append(text)

        # Set up an inflight task
        card._update_card_content = _slow_inflight
        await card.update("partial")

        assert card._inflight_task is not None

        # Now mock _update_card_content for close's final update
        card._update_card_content = _track_update

        # Mock _close_streaming_mode
        card._close_streaming_mode = AsyncMock()
        card._http_session = AsyncMock()
        card._http_session.closed = False

        await card.close(final_text="final answer")

        assert inflight_completed
        assert card._closed
        # Final text should be sent since it differs from current_text
        assert "final answer" in close_update_texts

    @pytest.mark.asyncio
    async def test_close_with_final_text_skips_merge(self):
        """close(final_text=...) should use final_text directly."""
        card = _make_card()
        card._state.current_text = "old text"
        card._pending_text = "pending text"

        update_texts = []

        async def _track(text, on_error=None):
            update_texts.append(text)

        card._update_card_content = _track
        card._close_streaming_mode = AsyncMock()
        card._http_session = AsyncMock()
        card._http_session.closed = False

        await card.close(final_text="completely new final")

        # Should use final_text directly, not merge with pending
        assert "completely new final" in update_texts

    @pytest.mark.asyncio
    async def test_close_without_final_text_merges_pending(self):
        """close() without final_text should merge pending with current."""
        card = _make_card()
        card._state.current_text = "hello"
        card._pending_text = "hello world"

        update_texts = []

        async def _track(text, on_error=None):
            update_texts.append(text)

        card._update_card_content = _track
        card._close_streaming_mode = AsyncMock()
        card._http_session = AsyncMock()
        card._http_session.closed = False

        await card.close()

        # Should merge: "hello" + "hello world" => "hello world"
        assert "hello world" in update_texts