"""Tests for build_ipc_notification_card - IPC cross-session card structure."""

from __future__ import annotations

import json

from siada.im.feishu.ipc_handler import build_ipc_notification_card


class TestBuildIpcNotificationCard:
    """Unit tests for the IPC notification card builder."""

    def test_card_schema_is_v2(self) -> None:
        card = build_ipc_notification_card("hello", "sess_123")
        assert card["schema"] == "2.0"

    def test_header_orange_theme(self) -> None:
        card = build_ipc_notification_card("content", "src_sess")
        header = card["header"]
        assert header["template"] == "orange"
        assert "Cross-Session Message" in header["title"]["content"]
        # No subtitle in new layout
        assert "subtitle" not in header

    def test_content_is_first_element(self) -> None:
        card = build_ipc_notification_card("my **bold** message", "sess_2")
        elements = card["body"]["elements"]
        # Content -> hr -> footer
        assert elements[0]["tag"] == "markdown"
        assert elements[0]["content"] == "my **bold** message"

    def test_footer_has_source_session(self) -> None:
        long_id = "feishu_direct_ou_abc123_oc_xyz789_1713000000000"
        card = build_ipc_notification_card("x", long_id)
        footer = card["body"]["elements"][2]
        assert footer["tag"] == "markdown"
        assert footer["text_size"] == "notation"
        assert long_id in footer["content"]
        assert "**Source:**" in footer["content"]

    def test_footer_includes_current_session_when_provided(self) -> None:
        card = build_ipc_notification_card("x", "src_sess", current_session_id="cur_sess")
        footer = card["body"]["elements"][2]["content"]
        assert "src_sess" in footer
        assert "cur_sess" in footer
        assert "**Current:**" in footer

    def test_footer_omits_current_session_label_when_empty(self) -> None:
        card = build_ipc_notification_card("x", "src_sess")
        footer = card["body"]["elements"][2]["content"]
        assert "**Current:**" not in footer

    def test_footer_has_tip_text(self) -> None:
        card = build_ipc_notification_card("x", "s1")
        footer = card["body"]["elements"][2]["content"]
        assert "<font color='purple'>" in footer  # purple system tip color
        assert "**Reply here to switch to the source session.**" in footer
        assert "**To stay here, reply to an earlier message in this session.**" in footer

    def test_layout_order(self) -> None:
        card = build_ipc_notification_card("content", "s1", "s2")
        elements = card["body"]["elements"]
        assert len(elements) == 3
        assert elements[0]["tag"] == "markdown"  # content
        assert elements[1]["tag"] == "hr"         # divider
        assert elements[2]["tag"] == "markdown"   # footer

    def test_card_is_json_serializable(self) -> None:
        card = build_ipc_notification_card("test", "sess_abc", "sess_cur")
        json_str = json.dumps(card, ensure_ascii=False)
        assert isinstance(json_str, str)

    def test_card_uses_chinese_template_when_preferred_language_is_zh_cn(self) -> None:
        card = build_ipc_notification_card(
            "内容",
            "source_sess",
            "current_sess",
            preferred_language="zh-CN",
        )

        assert card["header"]["title"]["content"] == "📬 跨会话消息"
        footer = card["body"]["elements"][2]["content"]
        assert "**回复这条消息或者直接发送新消息，都会切到来源session。**" in footer
        assert "**若想留在当前session，请回复本session中更早的一条消息。**" in footer
        assert "**来源:** `source_sess`" in footer
        assert "**当前:** `current_sess`" in footer

    def test_card_falls_back_to_english_for_unknown_language(self) -> None:
        card = build_ipc_notification_card(
            "hello",
            "source_sess",
            preferred_language="fr",
        )

        assert card["header"]["title"]["content"] == "📬 Cross-Session Message"
        footer = card["body"]["elements"][2]["content"]
        assert "**Reply here to switch to the source session.**" in footer
        assert "**Source:** `source_sess`" in footer
