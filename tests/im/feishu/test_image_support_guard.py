"""Unit tests for the image-support guard in LarkAgentExecutor.

Covers:
- _model_supports_images(): reads supports_images from session config
- _has_meaningful_text(): distinguishes real user text from media placeholders
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from siada.im.feishu.lark_agent_executor import LarkAgentExecutor
from siada.im.models import IMMessage


# ── adapter helper ───────────────────────────────────────────────────


def _make_stub_adapter():
    """Create a stub adapter instance for calling _parse_content.

    _LarkAdapterBase is abstract (has abstractmethods _get_lark_client
    and parse_event), so we create a minimal stub subclass that satisfies
    the contract. _parse_content / _extract_post_text don't touch them.
    """
    from siada.im.adapter.feishu import _LarkAdapterBase

    class _StubAdapter(_LarkAdapterBase):
        def _get_lark_client(self):
            raise NotImplementedError

        async def parse_event(self, raw):
            raise NotImplementedError

    return _StubAdapter.__new__(_StubAdapter)


def _parse_content(raw_content: str, msg_type: str) -> str:
    """Parse message content through the real adapter _parse_content."""
    return _make_stub_adapter()._parse_content(raw_content, msg_type)





# ── helpers ──────────────────────────────────────────────────────────


def _make_msg(**kwargs) -> IMMessage:
    defaults = dict(
        request_id="req_001",
        platform="lark",
        user_id="user_001",
        chat_id="oc_xxx",
        chat_type="p2p",
        content_type="text",
        content="hello world",
        timestamp=0.0,
        message_id="om_xxx",
    )
    defaults.update(kwargs)
    return IMMessage(**defaults)


def _make_session(supports_images: bool):
    """Build a minimal fake RunningSession with an llm_config."""
    llm_config = SimpleNamespace(supports_images=supports_images)
    siada_config = SimpleNamespace(llm_config=llm_config)
    return SimpleNamespace(siada_config=siada_config)


# ── _model_supports_images ───────────────────────────────────────────


class TestModelSupportsImages:
    def test_supports_images_true(self):
        session = _make_session(supports_images=True)
        assert LarkAgentExecutor._model_supports_images(session) is True

    def test_supports_images_false(self):
        session = _make_session(supports_images=False)
        assert LarkAgentExecutor._model_supports_images(session) is False

    def test_defaults_to_true_on_error(self):
        # A session whose attribute chain is broken should not cause a
        # false rejection — defaults to True.
        session = SimpleNamespace()  # no siada_config
        assert LarkAgentExecutor._model_supports_images(session) is True


# ── _has_meaningful_text ─────────────────────────────────────────────


class TestHasMeaningfulText:
    def test_plain_text_message(self):
        msg = _make_msg(content="hello world", content_type="text")
        assert LarkAgentExecutor._has_meaningful_text(msg) is True

    def test_empty_content(self):
        msg = _make_msg(content="", content_type="text")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_whitespace_only_content(self):
        msg = _make_msg(content="   \n  ", content_type="text")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_image_only_message(self):
        # Feishu image messages produce placeholder content
        msg = _make_msg(
            content="[image: img_ecffc3b0]",
            content_type="image",
        )
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_file_only_message(self):
        msg = _make_msg(
            content="[file: file_v3_00abc]",
            content_type="file",
        )
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_post_with_real_text(self):
        # Rich-text (post) messages carry extracted plain text
        msg = _make_msg(
            content="Please analyze this chart",
            content_type="post",
        )
        assert LarkAgentExecutor._has_meaningful_text(msg) is True

    def test_text_with_inline_image_placeholder(self):
        # A text message that references an image inline should still be
        # considered as having meaningful text after stripping the placeholder.
        msg = _make_msg(
            content="Look at this [image: img_123] please",
            content_type="text",
        )
        assert LarkAgentExecutor._has_meaningful_text(msg) is True

    def test_none_content(self):
        msg = _make_msg(content=None, content_type="text")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_post_with_only_images_no_text(self):
        # When a rich-text (post) message contains only image nodes and no
        # text/title/at elements, _extract_post_text falls back to str(data)
        # — a raw dict string starting with '{'.  This must be detected as
        # "no meaningful text" so the image-only guard can reject it.
        raw_dict_fallback = str(
            {"zh_cn": {"title": "", "content": [[{"tag": "img", "image_key": "img_xxx"}]]}}
        )
        msg = _make_msg(content=raw_dict_fallback, content_type="post")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_post_with_title_only(self):
        # A post with a title (even without body text) still has text.
        msg = _make_msg(content="My Report", content_type="post")
        assert LarkAgentExecutor._has_meaningful_text(msg) is True


# ── End-to-end tests using real adapter parsing ──────────────────────
# These verify _has_meaningful_text against the actual content that
# _LarkAdapterBase._parse_content produces for each message type.


class TestHasMeaningfulTextWithRealAdapter:
    """Verify _has_meaningful_text against real adapter parse output.

    Traces the parsing path in siada/im/adapter/feishu.py:
      text  → data.get("text")                    real user text
      post  → _extract_post_text(data)            title + text/a/at tags
              (falls back to str(data) if no text elements found)
      image → "[image: {file_key}]"               placeholder
      file  → "[file: {file_key}]"                placeholder
    """

    def test_real_post_with_text_and_images(self):
        # The user's example: a rich-text post with title, text, links,
        # @mentions, and img nodes. _extract_post_text extracts the text
        # parts; img nodes become feishu_media_keys (not in content).
        raw_post = {
            "title": "我是一个标题",
            "content": [
                [{"tag": "text", "text": "第一行 :"},
                 {"tag": "a", "href": "http://www.feishu.cn", "text": "超链接"},
                 {"tag": "at", "user_id": "@_user_1", "user_name": ""}],
                [{"tag": "img", "image_key": "img_47354fbc"}],
                [{"tag": "text", "text": "第二行:"},
                 {"tag": "text", "text": "文本测试"}],
                [{"tag": "img", "image_key": "img_47354fbc"}],
            ],
        }
        content = _parse_content(json.dumps(raw_post), "post")
        msg = _make_msg(content=content, content_type="post")
        # Extracted text is meaningful → True (images will be stripped
        # by the guard, agent still gets the text).
        assert LarkAgentExecutor._has_meaningful_text(msg) is True
        # Sanity: the parsed content contains real text, not raw dict
        assert "我是一个标题" in content
        assert "文本测试" in content

    def test_real_post_with_only_images_no_text(self):
        # A post with only img nodes (no title/text/a/at). _extract_post_text
        # falls back to str(data) — a raw dict string starting with '{'.
        raw_post = {
            "content": [
                [{"tag": "img", "image_key": "img_aaa"}],
                [{"tag": "img", "image_key": "img_bbb"}],
            ],
        }
        content = _parse_content(json.dumps(raw_post), "post")
        msg = _make_msg(content=content, content_type="post")
        # No meaningful text → False (guard will reject image-only input).
        assert LarkAgentExecutor._has_meaningful_text(msg) is False
        # Sanity: confirm the fallback produced a raw dict string
        assert content.startswith("{")

    def test_real_post_locale_wrapped_with_only_images(self):
        # Same edge case but with locale-wrapped format.
        raw_post = {
            "zh_cn": {
                "title": "",
                "content": [[{"tag": "img", "image_key": "img_aaa"}]],
            }
        }
        content = _parse_content(json.dumps(raw_post), "post")

        msg = _make_msg(content=content, content_type="post")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False

    def test_real_image_message_placeholder(self):
        # An image message (msg_type="image") produces placeholder content.
        content = _parse_content(json.dumps({"image_key": "img_ecffc3b0"}), "image")
        msg = _make_msg(content=content, content_type="image")
        assert LarkAgentExecutor._has_meaningful_text(msg) is False
        assert content == "[image: img_ecffc3b0]"



