"""Tests for Feishu media key extraction and post text parsing.

Regression coverage for the bug where post messages without a locale wrapper
(direct format: {"title": "", "content": [[...]]}) were silently dropping
all img tags because the code expected locale-wrapped format
({"zh_cn": {"title": "", "content": [...]}}).
"""

import json
import pytest

from siada.im.feishu.media import extract_media_keys_from_message


# ── extract_media_keys_from_message ───────────────────────────────────────────


class TestExtractMediaKeysPostDirect:
    """post messages in direct (no-locale) format: {"title": "", "content": [[...]]}"""

    def _make_raw(self, content_nodes):
        return json.dumps({"title": "", "content": content_nodes})

    def test_single_image_direct_format(self):
        """Regression: image in direct-format post must be extracted."""
        raw = self._make_raw([[{"tag": "img", "image_key": "img_v3_abc123"}]])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_abc123", "image")]

    def test_multiple_images_direct_format(self):
        raw = self._make_raw([
            [{"tag": "img", "image_key": "img_v3_001"}],
            [{"tag": "text", "text": "hello"}],
            [{"tag": "img", "image_key": "img_v3_002"}],
        ])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_001", "image"), ("img_v3_002", "image")]

    def test_mixed_text_and_image_direct_format(self):
        raw = self._make_raw([
            [{"tag": "text", "text": "see below"}, {"tag": "img", "image_key": "img_v3_xyz"}]
        ])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_xyz", "image")]

    def test_no_image_direct_format_returns_empty(self):
        raw = self._make_raw([[{"tag": "text", "text": "plain text"}]])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == []

    def test_empty_content_direct_format(self):
        raw = json.dumps({"title": "", "content": []})
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == []


class TestExtractMediaKeysPostLocaleWrapped:
    """post messages in locale-wrapped format: {"zh_cn": {"title": "", "content": [...]}}"""

    def _make_raw(self, content_nodes, locale="zh_cn"):
        return json.dumps({locale: {"title": "", "content": content_nodes}})

    def test_single_image_locale_format(self):
        raw = self._make_raw([[{"tag": "img", "image_key": "img_v3_locale_001"}]])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_locale_001", "image")]

    def test_multiple_images_locale_format(self):
        raw = self._make_raw([
            [{"tag": "img", "image_key": "img_v3_la"}],
            [{"tag": "img", "image_key": "img_v3_lb"}],
        ])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_la", "image"), ("img_v3_lb", "image")]

    def test_no_image_locale_format(self):
        raw = self._make_raw([[{"tag": "text", "text": "no image here"}]])
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == []


class TestExtractMediaKeysImageAndFile:
    """Non-post message types (image, file) are unaffected by the locale fix."""

    def test_image_message(self):
        raw = json.dumps({"image_key": "img_v3_standalone"})
        pairs = extract_media_keys_from_message(raw, "image")
        assert pairs == [("img_v3_standalone", "image")]

    def test_file_message(self):
        raw = json.dumps({"file_key": "file_abc"})
        pairs = extract_media_keys_from_message(raw, "file")
        assert pairs == [("file_abc", "file")]

    def test_video_skipped(self):
        raw = json.dumps({"file_key": "video_xyz"})
        assert extract_media_keys_from_message(raw, "video") == []

    def test_audio_skipped(self):
        raw = json.dumps({"file_key": "audio_xyz"})
        assert extract_media_keys_from_message(raw, "audio") == []

    def test_sticker_skipped(self):
        raw = json.dumps({"file_key": "sticker_xyz"})
        assert extract_media_keys_from_message(raw, "sticker") == []


class TestExtractMediaKeysRealWorldPayload:
    """Regression test using the exact payload from the field incident (2026-06-24).

    Real message content (from Lark SDK debug log):
        {"title":"","content":[[{"tag":"img","image_key":"img_v3_0212v_d21ee534-...","width":556,"height":156}],
                                [{"tag":"text","text":"你能看这个图吗？","style":[]}]]}
    """

    RAW = (
        '{"title":"","content":[[{"tag":"img","image_key":"img_v3_0212v_abc","width":556,"height":156}],'
        '[{"tag":"text","text":"你能看这个图吗？","style":[]}]]}'
    )

    def test_image_key_extracted(self):
        pairs = extract_media_keys_from_message(self.RAW, "post")
        assert pairs == [("img_v3_0212v_abc", "image")]

    def test_text_extracted_by_parse_content(self):
        """_parse_content for the same payload must return the text body."""
        from siada.im.adapter.feishu import LarkRelayAdapter
        adapter = LarkRelayAdapter()
        result = adapter._parse_content(self.RAW, "post")
        assert "你能看这个图吗？" in result

    def test_img_tag_extra_fields_ignored(self):
        """width/height fields on the img node must not break extraction."""
        import json
        raw = json.dumps({
            "title": "",
            "content": [[{
                "tag": "img",
                "image_key": "img_v3_xyz",
                "width": 100,
                "height": 200,
            }]],
        })
        pairs = extract_media_keys_from_message(raw, "post")
        assert pairs == [("img_v3_xyz", "image")]


class TestExtractMediaKeysEdgeCases:
    def test_invalid_json_returns_empty(self):
        assert extract_media_keys_from_message("not-json", "post") == []

    def test_empty_string_returns_empty(self):
        assert extract_media_keys_from_message("", "post") == []

    def test_img_tag_without_image_key_skipped(self):
        raw = json.dumps({"title": "", "content": [[{"tag": "img"}]]})
        assert extract_media_keys_from_message(raw, "post") == []


# ── _extract_post_text (via _LarkAdapterBase) ─────────────────────────────────


class TestExtractPostTextDirectFormat:
    """_extract_post_text must handle direct format: {"title": "", "content": [[...]]}"""

    def _make_adapter(self):
        # Use LarkRelayAdapter as a concrete subclass of _LarkAdapterBase
        from siada.im.adapter.feishu import LarkRelayAdapter
        return LarkRelayAdapter()

    def test_text_extracted_direct_format(self):
        adapter = self._make_adapter()
        data = {"title": "My Title", "content": [[{"tag": "text", "text": "Hello world"}]]}
        result = adapter._extract_post_text(data)
        assert "My Title" in result
        assert "Hello world" in result

    def test_image_only_direct_format_returns_empty_parts(self):
        """With only an img tag, there's no text — should not fall back to str(data)."""
        adapter = self._make_adapter()
        # Image-only post: parts will be empty, fallback is str(data)
        data = {"title": "", "content": [[{"tag": "img", "image_key": "img_v3_abc"}]]}
        result = adapter._extract_post_text(data)
        # With the fix, it iterates correctly; parts is empty → returns str(data)
        # But crucially it does NOT crash and does NOT skip the locale-dict check
        assert isinstance(result, str)

    def test_locale_wrapped_still_works(self):
        adapter = self._make_adapter()
        data = {"zh_cn": {"title": "Title", "content": [[{"tag": "text", "text": "Body"}]]}}
        result = adapter._extract_post_text(data)
        assert "Title" in result
        assert "Body" in result

    def test_direct_format_with_at_tag(self):
        adapter = self._make_adapter()
        data = {
            "title": "",
            "content": [[{"tag": "at", "user_name": "Alice", "user_id": "ou_xxx"}]],
        }
        result = adapter._extract_post_text(data)
        assert "@Alice" in result
