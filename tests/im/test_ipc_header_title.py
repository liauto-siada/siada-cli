"""Tests for header_title passthrough across the IPC → card_sender pipeline.

Covers the compatibility matrix from the design doc:
1. enqueue_ipc_message(content) — no header_title → chat_id card has no "header" key.
2. enqueue_ipc_message(content, header_title="X") — all three delivery paths
   (chat_id / open_id / email) carry header_title="X" in the generated card.
3. enqueue_ipc_message(content, source_session_id="src", header_title="X") —
   cross-session card takes priority; header_title is ignored.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from siada.im.feishu.card_sender import build_markdown_card
from siada.im.feishu.ipc_handler import IpcMessageHandler


# ── Unit tests for build_markdown_card ────────────────────────────────


class TestBuildMarkdownCard:
    """Verify the single branching point: if header_title → header present."""

    def test_no_header_when_title_is_none(self) -> None:
        card = build_markdown_card("hello world")
        assert "header" not in card
        assert card["body"]["elements"][0]["content"] == "hello world"

    def test_no_header_when_title_is_empty_string(self) -> None:
        card = build_markdown_card("hello", header_title="")
        assert "header" not in card

    def test_header_present_when_title_given(self) -> None:
        card = build_markdown_card("body", header_title="My Title")
        assert card["header"]["title"]["content"] == "My Title"
        assert card["header"]["template"] == "blue"  # default

    def test_custom_template(self) -> None:
        card = build_markdown_card(
            "body", header_title="T", header_template="green",
        )
        assert card["header"]["template"] == "green"

    def test_schema_is_v2(self) -> None:
        card = build_markdown_card("x", header_title="Y")
        assert card["schema"] == "2.0"

    def test_json_serializable(self) -> None:
        card = build_markdown_card("c", header_title="Siada 每日总结 · 2025-05-12")
        s = json.dumps(card, ensure_ascii=False)
        assert "Siada 每日总结" in s


# ── Integration tests for IPC handler header_title passthrough ────────


def _make_handler(
    *,
    chat_id: str | None = "oc_test",
    open_id: str | None = None,
) -> tuple[IpcMessageHandler, MagicMock]:
    """Create an IpcMessageHandler with mocked card_sender."""
    card_sender = MagicMock()
    card_sender.send_im = AsyncMock(return_value="msg_im")
    card_sender.send_by_open_id = AsyncMock(return_value="msg_oid")
    card_sender.send_by_email = AsyncMock(return_value="msg_email")
    card_sender.send_card_json = AsyncMock(return_value="msg_card")

    # Build a minimal routing table mock
    routing = MagicMock()
    if chat_id:
        routing.chats = {chat_id: "sid_1"}
        routing.open_ids = {}
    elif open_id:
        routing.chats = {}
        routing.open_ids = {open_id: "sid_1"}
    else:
        routing.chats = {}
        routing.open_ids = {}

    def is_single(cid: str) -> bool:
        return True  # treat all chats as single (P2P)

    handler = IpcMessageHandler(
        card_sender=card_sender,
        get_routed_session_id=lambda *a, **kw: "sid_1",
        get_session=lambda sid: None,  # skip history write
        is_single_chat=is_single,
        resolve_notify_email=lambda: "user@example.com",
        resolve_preferred_language=lambda: None,
    )
    return handler, card_sender, routing  # type: ignore[return-value]


class TestIpcHeaderTitlePassthrough:
    """Verify header_title flows from enqueue → drain → card_sender calls."""

    @pytest.mark.asyncio
    async def test_chat_id_no_header_title(self) -> None:
        """enqueue(content) → send_im called with header_title=None."""
        handler, sender, routing = _make_handler(chat_id="oc_1")

        await handler.enqueue("hello", "markdown")
        await handler.drain_pending(routing=routing)

        sender.send_im.assert_called_once()
        _, kwargs = sender.send_im.call_args
        assert kwargs.get("header_title") is None

    @pytest.mark.asyncio
    async def test_chat_id_with_header_title(self) -> None:
        """enqueue(content, header_title="X") → send_im(header_title="X")."""
        handler, sender, routing = _make_handler(chat_id="oc_1")

        await handler.enqueue(
            "hello", "markdown", header_title="Siada 每日总结 · 2025-05-12",
        )
        await handler.drain_pending(routing=routing)

        sender.send_im.assert_called_once()
        _, kwargs = sender.send_im.call_args
        assert kwargs["header_title"] == "Siada 每日总结 · 2025-05-12"

    @pytest.mark.asyncio
    async def test_open_id_with_header_title(self) -> None:
        """open_id path: header_title forwarded to send_by_open_id."""
        handler, sender, routing = _make_handler(
            chat_id=None, open_id="ou_abc",
        )

        await handler.enqueue(
            "content", "markdown", header_title="Daily Summary",
        )
        await handler.drain_pending(routing=routing)

        sender.send_by_open_id.assert_called_once()
        _, kwargs = sender.send_by_open_id.call_args
        assert kwargs["header_title"] == "Daily Summary"

    @pytest.mark.asyncio
    async def test_email_with_header_title(self) -> None:
        """email fallback path: header_title forwarded to send_by_email."""
        handler, sender, routing = _make_handler(
            chat_id=None, open_id=None,
        )

        await handler.enqueue(
            "content", "markdown", header_title="Summary",
        )
        await handler.drain_pending(routing=routing)

        sender.send_by_email.assert_called_once()
        _, kwargs = sender.send_by_email.call_args
        assert kwargs["header_title"] == "Summary"

    @pytest.mark.asyncio
    async def test_cross_session_card_ignores_header_title(self) -> None:
        """source_session_id present → cross-session card; header_title ignored.

        When source_session_id is provided, a cross-session notification card
        is built (with its own "Cross-Session Message" header). The caller's
        header_title should NOT appear in the resulting card — send_card_json
        is used instead of send_im.
        """
        handler, sender, routing = _make_handler(chat_id="oc_1")

        await handler.enqueue(
            "content", "markdown",
            source_session_id="src_sess",
            header_title="Should Be Ignored",
        )
        await handler.drain_pending(routing=routing)

        # Cross-session path uses send_card_json, not send_im
        sender.send_card_json.assert_called_once()
        card_json = sender.send_card_json.call_args[0][1]
        # The card header should be the cross-session template, not our header_title
        assert "Cross-Session Message" in card_json["header"]["title"]["content"]
        assert "Should Be Ignored" not in json.dumps(card_json)

        # send_im should NOT have been called for this message
        sender.send_im.assert_not_called()


# ── Notification template tests ───────────────────────────────────────


class TestDailySummaryNotificationTemplate:
    def test_chinese_default(self) -> None:
        from siada.im.feishu.notification_templates import (
            get_daily_summary_notification_template,
        )

        t = get_daily_summary_notification_template()
        assert "每日总结" in t.header_title
        # Date should NOT appear in header (it's in the summary body)
        assert "{date}" not in t.header_title

    def test_english(self) -> None:
        from siada.im.feishu.notification_templates import (
            get_daily_summary_notification_template,
        )

        t = get_daily_summary_notification_template("en")
        assert "Daily Summary" in t.header_title
        assert "{date}" not in t.header_title

    def test_zh_cn(self) -> None:
        from siada.im.feishu.notification_templates import (
            get_daily_summary_notification_template,
        )

        t = get_daily_summary_notification_template("zh-CN")
        assert "每日总结" in t.header_title

    def test_none_language_defaults_to_chinese(self) -> None:
        from siada.im.feishu.notification_templates import (
            get_daily_summary_notification_template,
        )

        t = get_daily_summary_notification_template(None)
        assert "每日总结" in t.header_title
