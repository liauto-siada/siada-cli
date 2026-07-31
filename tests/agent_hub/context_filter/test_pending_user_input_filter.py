"""
Unit tests for PendingUserInputInjector filter.

Covers:
  1. No pending items → model_data.input unchanged, add_items not called
  2. Plain text items → appended to model_data.input as {"role":"user","content":str}
  3. Items with image_paths → multimodal content list format
  4. Empty-string items are skipped
  5. FileSession.add_items is called with exactly the new items
  6. FileSession error is swallowed (does not propagate)
  7. context=None is handled gracefully (no add_items call)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import siada.io.stdin_interrupt_monitor as _mod
from siada.agent_hub.context_filter.pending_user_input_filter import PendingUserInputInjector


def _reset_pending():
    _mod._pending_injections.clear()


def _make_model_data(input_items=None):
    md = MagicMock()
    md.input = list(input_items if input_items is not None else [{"role": "user", "content": "original"}])
    return md


def _make_context(file_session=None):
    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.session.openai_session = file_session or AsyncMock()
    return ctx


class TestPendingUserInputInjector:

    def setup_method(self):
        _reset_pending()

    def teardown_method(self):
        _reset_pending()

    @pytest.mark.asyncio
    async def test_no_pending_leaves_input_unchanged(self):
        injector = PendingUserInputInjector()
        model_data = _make_model_data()
        original_input = list(model_data.input)
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        assert model_data.input == original_input
        ctx.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_plain_text_appended_to_input(self):
        _mod._pending_injections.append((None, "hello agent", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data([{"role": "user", "content": "original"}])
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        assert len(model_data.input) == 2
        injected = model_data.input[-1]
        assert injected == {"role": "user", "content": "hello agent"}

    @pytest.mark.asyncio
    async def test_image_paths_produce_multimodal_content(self, tmp_path):
        # Reuses the same _build_multimodal_input() as the normal (non-queued)
        # turn flow, so images are read and embedded as base64 data URLs.
        img_a = tmp_path / "a.png"
        img_b = tmp_path / "b.png"
        img_a.write_bytes(b"\x89PNG\r\n\x1a\nfake-a")
        img_b.write_bytes(b"\x89PNG\r\n\x1a\nfake-b")

        _mod._pending_injections.append((None, "describe this", [str(img_a), str(img_b)]))
        injector = PendingUserInputInjector()
        model_data = _make_model_data()
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        injected = model_data.input[-1]
        assert injected["role"] == "user"
        assert isinstance(injected["content"], list)
        assert injected["content"][0] == {"type": "input_text", "text": "describe this"}
        # Images are encoded as base64 data URLs (same format as non-queued flow).
        assert injected["content"][1]["type"] == "input_image"
        assert injected["content"][1]["image_url"].startswith("data:image/png;base64,")
        assert injected["content"][2]["type"] == "input_image"
        assert injected["content"][2]["image_url"].startswith("data:image/png;base64,")


    @pytest.mark.asyncio
    async def test_non_list_image_paths_is_discarded(self):
        """A malformed image_paths (e.g. a bare string) must be coerced to None
        and the message falls back to plain text — not iterated char-by-char."""
        _mod._pending_injections.append((None, "look here", "a/b.png"))  # str, not list
        injector = PendingUserInputInjector()
        model_data = _make_model_data([])
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        # Falls back to a plain text user message (no multimodal content list).
        assert len(model_data.input) == 1
        assert model_data.input[0] == {"role": "user", "content": "look here"}

    @pytest.mark.asyncio
    async def test_empty_content_is_skipped(self):

        _mod._pending_injections.append((None, "", None))
        _mod._pending_injections.append((None, "   ", None))  # only whitespace — content is still truthy
        injector = PendingUserInputInjector()
        model_data = _make_model_data([])
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        # "" is falsy → skipped; "   " is truthy → included
        assert len(model_data.input) == 1
        assert model_data.input[0]["content"] == "   "

    @pytest.mark.asyncio
    async def test_add_items_called_with_new_items_only(self):
        _mod._pending_injections.append((None, "msg1", None))
        _mod._pending_injections.append((None, "msg2", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data([{"role": "user", "content": "original"}])
        file_session = AsyncMock()
        ctx = _make_context(file_session)

        await injector.filter(model_data, agent=None, context=ctx)

        file_session.add_items.assert_called_once()
        called_items = file_session.add_items.call_args[0][0]
        assert called_items == [
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
        ]

    @pytest.mark.asyncio
    async def test_file_session_error_is_swallowed(self):
        _mod._pending_injections.append((None, "msg", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data()
        file_session = AsyncMock()
        file_session.add_items.side_effect = RuntimeError("disk full")
        ctx = _make_context(file_session)

        # Must not raise
        await injector.filter(model_data, agent=None, context=ctx)

        # model_data.input was still updated before the error
        assert model_data.input[-1] == {"role": "user", "content": "msg"}

    @pytest.mark.asyncio
    async def test_context_none_no_add_items_call(self):
        _mod._pending_injections.append((None, "msg", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data()

        # Should not raise even with context=None
        await injector.filter(model_data, agent=None, context=None)

        assert model_data.input[-1] == {"role": "user", "content": "msg"}

    @pytest.mark.asyncio
    async def test_pending_deque_is_drained_after_filter(self):
        _mod._pending_injections.append((None, "msg", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data()
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        # Deque must be empty — items consumed
        assert len(_mod._pending_injections) == 0

    @pytest.mark.asyncio
    async def test_multiple_pending_all_appended_in_order(self):
        for msg in ("first", "second", "third"):
            _mod._pending_injections.append((None, msg, None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data([])
        ctx = _make_context()

        await injector.filter(model_data, agent=None, context=ctx)

        contents = [item["content"] for item in model_data.input]
        assert contents == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_filter_sends_queue_item_consumed_notification(self):
        """queue_id present → _send_queue_notification called after injection."""
        notifications_sent = []

        def fake_notify(reason, metadata):
            notifications_sent.append({"reason": reason, "metadata": metadata})

        _mod._pending_injections.append(("qid-abc", "hello with id", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data([])
        ctx = _make_context()

        original_fn = _mod._send_queue_notification
        _mod._send_queue_notification = fake_notify
        try:
            await injector.filter(model_data, agent=None, context=ctx)
        finally:
            _mod._send_queue_notification = original_fn

        assert len(notifications_sent) == 1
        assert notifications_sent[0]["reason"] == "queue_item_consumed"
        assert notifications_sent[0]["metadata"]["id"] == "qid-abc"
        # The notification carries the original prompt text so the frontend can
        # render the user bubble even if its preview queue was already cleared.
        assert notifications_sent[0]["metadata"]["content"] == "hello with id"

    @pytest.mark.asyncio
    async def test_filter_skips_notification_when_id_is_none(self):
        """queue_id is None (old protocol) → no notification sent."""
        notifications_sent = []

        _mod._pending_injections.append((None, "hello no id", None))
        injector = PendingUserInputInjector()
        model_data = _make_model_data([])
        ctx = _make_context()

        original_fn = _mod._send_queue_notification
        _mod._send_queue_notification = lambda r, m: notifications_sent.append(m)
        try:
            await injector.filter(model_data, agent=None, context=ctx)
        finally:
            _mod._send_queue_notification = original_fn

        assert len(notifications_sent) == 0
