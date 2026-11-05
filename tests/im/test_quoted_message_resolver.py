"""Tests for QuotedMessageResolver and related utilities."""
from __future__ import annotations

import json
import pytest

from siada.im.feishu.quoted_message_resolver import (
    QuotedMessage,
    QuotedMessageResolver,
    parse_message_content,
    _parse_post_content,
    _parse_interactive_content,
    _sanitize_and_truncate,
)
from siada.im.feishu.prompt_injection import build_quoted_message_block
from siada.im.models import IMMessage


# ─── parse_message_content tests ─────────────────────────────────────────


class TestParseMessageContent:
    """Tests for parse_message_content across different msg_types."""

    def test_text_message(self):
        content = json.dumps({"text": "hello world"})
        assert parse_message_content("text", content) == "hello world"

    def test_text_message_empty(self):
        content = json.dumps({"text": ""})
        assert parse_message_content("text", content) == ""

    def test_image_message(self):
        content = json.dumps({"image_key": "img_xxx"})
        assert parse_message_content("image", content) == "[图片]"

    def test_file_message_with_name(self):
        content = json.dumps({"file_key": "file_xxx", "file_name": "report.pdf"})
        assert parse_message_content("file", content) == "[文件: report.pdf]"

    def test_file_message_without_name(self):
        content = json.dumps({"file_key": "file_xxx"})
        assert parse_message_content("file", content) == "[文件]"

    def test_audio_message(self):
        content = json.dumps({"file_key": "audio_xxx"})
        assert parse_message_content("audio", content) == "[语音消息]"

    def test_video_message(self):
        content = json.dumps({"file_key": "video_xxx"})
        assert parse_message_content("video", content) == "[视频]"

    def test_sticker_message(self):
        content = json.dumps({"file_key": "sticker_xxx"})
        assert parse_message_content("sticker", content) == "[表情包]"

    def test_share_chat_message(self):
        content = json.dumps({"chat_id": "oc_xxx"})
        assert parse_message_content("share_chat", content) == "[分享卡片]"

    def test_system_message_returns_empty(self):
        content = json.dumps({"type": "add_member"})
        assert parse_message_content("system", content) == ""

    def test_invalid_json(self):
        assert parse_message_content("text", "not json{{{") == ""

    def test_none_content(self):
        assert parse_message_content("text", None) == ""

    def test_unknown_type_with_text_field(self):
        content = json.dumps({"text": "fallback text"})
        assert parse_message_content("unknown_type", content) == "fallback text"


class TestParsePostContent:
    """Tests for rich text (post) parsing."""

    def test_simple_post_zh_cn(self):
        content = {
            "zh_cn": {
                "title": "测试标题",
                "content": [
                    [
                        {"tag": "text", "text": "第一行文本"},
                        {"tag": "a", "text": "链接", "href": "https://example.com"},
                    ],
                    [
                        {"tag": "text", "text": "第二行"},
                        {"tag": "at", "user_name": "张三"},
                    ],
                ],
            }
        }
        result = _parse_post_content(content)
        assert "测试标题" in result
        assert "第一行文本" in result
        assert "链接(https://example.com)" in result
        assert "第二行" in result
        assert "@张三" in result

    def test_post_flat_format(self):
        content = {
            "title": "Flat Title",
            "content": [
                [{"tag": "text", "text": "hello"}],
            ],
        }
        result = _parse_post_content(content)
        assert "Flat Title" in result
        assert "hello" in result

    def test_post_with_image_tag(self):
        content = {
            "zh_cn": {
                "title": "",
                "content": [
                    [{"tag": "img", "image_key": "img_xxx"}],
                ],
            }
        }
        result = _parse_post_content(content)
        assert "[图片]" in result

    def test_post_with_emotion(self):
        content = {
            "zh_cn": {
                "title": "",
                "content": [
                    [{"tag": "emotion", "emoji_type": "SMILE"}],
                ],
            }
        }
        result = _parse_post_content(content)
        assert "[SMILE]" in result

    def test_post_empty_content(self):
        content = {"zh_cn": {"title": "Only Title", "content": []}}
        result = _parse_post_content(content)
        assert result == "Only Title"


class TestParseInteractiveContent:
    """Tests for interactive card content parsing."""

    def test_card_with_header_and_markdown(self):
        content = {
            "header": {"title": {"content": "Card Title"}},
            "body": {
                "elements": [{"tag": "markdown", "content": "Some **bold** text"}],
            },
        }
        result = _parse_interactive_content(content)
        assert "[卡片: Card Title]" in result
        assert "Some **bold** text" in result

    def test_card_header_only(self):
        content = {
            "header": {"title": {"content": "Header Only"}},
            "body": {"elements": []},
        }
        result = _parse_interactive_content(content)
        assert result == "[卡片: Header Only]"

    def test_card_body_only(self):
        content = {
            "body": {
                "elements": [{"tag": "markdown", "content": "Body text"}],
            },
        }
        result = _parse_interactive_content(content)
        assert "[卡片] Body text" in result

    def test_card_no_content(self):
        content = {}
        result = _parse_interactive_content(content)
        assert result == "[互动卡片]"

    def test_card_nested_elements_and_top_level_title(self):
        content = {
            "title": "💬 Answer",
            "elements": [
                [
                    {"tag": "img", "image_key": "img_v3_02ad_e19fca1f-912a-450e-95de-3c229091b53g"},
                    {"tag": "text", "text": "请升级至最新版本客户端，以查看内容"},
                    {"tag": "text", "text": ""},
                ]
            ],
        }
        result = _parse_interactive_content(content)
        assert result == "[卡片: 💬 Answer] 请升级至最新版本客户端，以查看内容"


# ─── _sanitize_and_truncate tests ────────────────────────────────────────


class TestSanitizeAndTruncate:
    """Tests for content sanitization and truncation."""

    def test_normal_text_unchanged(self):
        assert _sanitize_and_truncate("hello") == "hello"

    def test_strips_null_bytes(self):
        assert _sanitize_and_truncate("he\x00llo") == "hello"

    def test_neutralizes_triple_backticks(self):
        text = "```python\ncode\n```"
        result = _sanitize_and_truncate(text)
        assert "```" not in result
        assert "` ` `" in result

    def test_truncation(self):
        long_text = "a" * 3000
        result = _sanitize_and_truncate(long_text, max_len=100)
        assert len(result) < 200  # truncated + indicator
        assert "truncated" in result
        assert "3000 chars total" in result

    def test_empty_string(self):
        assert _sanitize_and_truncate("") == ""

    def test_no_truncation_at_boundary(self):
        text = "a" * 2000
        result = _sanitize_and_truncate(text, max_len=2000)
        assert result == text  # Exactly at boundary, no truncation


# ─── QuotedMessageResolver tests ─────────────────────────────────────────


class TestQuotedMessageResolverLocal:
    """Tests for local session history lookup."""

    @pytest.mark.asyncio
    async def test_no_parent_id_returns_none(self):
        resolver = QuotedMessageResolver()
        result = await resolver.resolve(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_in_history_by_message_id(self):
        resolver = QuotedMessageResolver()
        history = [
            {"message_id": "om_111", "content": "first msg", "sender_name": "Alice"},
            {"message_id": "om_222", "content": "second msg", "sender_name": "Bob"},
            {"message_id": "om_333", "content": "third msg"},
        ]
        result = await resolver.resolve("om_222", session_history=history)
        assert result is not None
        assert result.message_id == "om_222"
        assert result.content == "second msg"
        assert result.sender_name == "Bob"

    @pytest.mark.asyncio
    async def test_not_found_in_history_no_client(self):
        resolver = QuotedMessageResolver()
        history = [
            {"message_id": "om_111", "content": "first msg"},
        ]
        result = await resolver.resolve("om_999", session_history=history)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_underscore_message_id(self):
        resolver = QuotedMessageResolver()
        history = [
            {"_message_id": "om_444", "content": "special msg", "sender_name": "Eve"},
        ]
        result = await resolver.resolve("om_444", session_history=history)
        assert result is not None
        assert result.content == "special msg"

    @pytest.mark.asyncio
    async def test_empty_history(self):
        resolver = QuotedMessageResolver()
        result = await resolver.resolve("om_111", session_history=[])
        assert result is None


# ─── build_quoted_message_block tests ────────────────────────────────────


class TestBuildQuotedMessageBlock:
    """Tests for prompt_injection.build_quoted_message_block."""

    def _make_msg(self, **kwargs) -> IMMessage:
        defaults = dict(
            request_id="req_1",
            platform="lark",
            user_id="user_1",
            chat_id="chat_1",
            chat_type="p2p",
            content_type="text",
            content="hello",
            timestamp=1234567890.0,
        )
        defaults.update(kwargs)
        return IMMessage(**defaults)

    def test_no_quoted_content_returns_none(self):
        msg = self._make_msg()
        assert build_quoted_message_block(msg) is None

    def test_with_quoted_content_and_sender(self):
        msg = self._make_msg(
            quoted_content="帮我看一下代码",
            quoted_sender="张三",
        )
        result = build_quoted_message_block(msg)
        assert result is not None
        assert "Replied message" in result
        assert "张三" in result
        assert "帮我看一下代码" in result

    def test_with_quoted_content_no_sender(self):
        msg = self._make_msg(
            quoted_content="some quoted text",
        )
        result = build_quoted_message_block(msg)
        assert result is not None
        assert "some quoted text" in result
        assert "sender" not in result  # sender field should be absent

    def test_output_is_json_parseable(self):
        msg = self._make_msg(
            quoted_content="hello world",
            quoted_sender="Alice",
        )
        result = build_quoted_message_block(msg)
        # Extract JSON part after the comment line
        lines = result.split("\n", 1)
        assert lines[0].startswith("//")
        json_part = lines[1]
        data = json.loads(json_part)
        assert data["sender"] == "Alice"
        assert data["body"] == "hello world"
