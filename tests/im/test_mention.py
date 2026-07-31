"""Unit tests for siada.im.feishu.mention module."""

import pytest

from siada.im.feishu.mention import (
    check_bot_mentioned,
    extract_mention_targets,
    normalize_mentions,
    format_mention_for_text,
    format_mention_for_card,
    build_mentioned_message,
    build_mentioned_card_content,
    build_mention_system_hint,
    build_sender_mention_target,
)
from siada.im.models import IMMessage, MentionTarget


BOT_OPEN_ID = "ou_bot_123"


# ──────────────── Fixtures ────────────────


def _make_mention(open_id: str, name: str, key: str) -> dict:
    """Helper to build a Feishu-style mention dict."""
    return {"id": {"open_id": open_id}, "name": name, "key": key}


def _make_mention_str_id(open_id: str, name: str, key: str) -> dict:
    """Helper with string-style id (non-dict)."""
    return {"id": open_id, "name": name, "key": key}


def _make_msg(
    content: str = "hello",
    mentions: list | None = None,
    has_any_mention: bool = False,
    chat_type: str = "group",
    sender_open_id: str | None = None,
    sender_name: str | None = None,
) -> IMMessage:
    """Helper to build a minimal IMMessage."""
    return IMMessage(
        request_id="req_1",
        platform="lark",
        user_id="u1",
        chat_id="oc_test",
        chat_type=chat_type,
        content_type="text",
        content=content,
        timestamp=0.0,
        mentions=mentions or [],
        has_any_mention=has_any_mention,
        sender_open_id=sender_open_id,
        sender_name=sender_name,
    )


# ──────────────── check_bot_mentioned ────────────────


class TestCheckBotMentioned:
    def test_bot_mentioned_by_open_id(self):
        mentions = [_make_mention(BOT_OPEN_ID, "Bot", "@_user_1")]
        assert check_bot_mentioned(mentions, BOT_OPEN_ID) is True

    def test_bot_not_mentioned(self):
        mentions = [_make_mention("ou_other", "Alice", "@_user_1")]
        assert check_bot_mentioned(mentions, BOT_OPEN_ID) is False

    def test_at_all_counts_as_bot_mention(self):
        mentions = [{"key": "@_all", "id": {"open_id": ""}, "name": "所有人"}]
        assert check_bot_mentioned(mentions, BOT_OPEN_ID) is True

    def test_empty_mentions(self):
        assert check_bot_mentioned([], BOT_OPEN_ID) is False

    def test_string_id_format(self):
        mentions = [_make_mention_str_id(BOT_OPEN_ID, "Bot", "@_user_1")]
        assert check_bot_mentioned(mentions, BOT_OPEN_ID) is True


# ──────────────── extract_mention_targets ────────────────


class TestExtractMentionTargets:
    def test_extracts_non_bot_mentions(self):
        mentions = [
            _make_mention(BOT_OPEN_ID, "Bot", "@_user_1"),
            _make_mention("ou_alice", "Alice", "@_user_2"),
            _make_mention("ou_bob", "Bob", "@_user_3"),
        ]
        targets = extract_mention_targets(mentions, BOT_OPEN_ID)
        assert len(targets) == 2
        assert targets[0].open_id == "ou_alice"
        assert targets[0].name == "Alice"
        assert targets[0].key == "@_user_2"
        assert targets[1].open_id == "ou_bob"

    def test_filters_out_at_all(self):
        mentions = [
            {"key": "@_all", "id": {"open_id": ""}, "name": "所有人"},
            _make_mention("ou_alice", "Alice", "@_user_1"),
        ]
        targets = extract_mention_targets(mentions, BOT_OPEN_ID)
        assert len(targets) == 1
        assert targets[0].open_id == "ou_alice"

    def test_empty_when_only_bot(self):
        mentions = [_make_mention(BOT_OPEN_ID, "Bot", "@_user_1")]
        targets = extract_mention_targets(mentions, BOT_OPEN_ID)
        assert targets == []

    def test_empty_mentions(self):
        assert extract_mention_targets([], BOT_OPEN_ID) == []


# ──────────────── normalize_mentions ────────────────


class TestNormalizeMentions:
    def test_replaces_user_placeholder_with_at_tag(self):
        text = "@_user_1 hello @_user_2"
        mentions = [
            _make_mention(BOT_OPEN_ID, "Bot", "@_user_1"),
            _make_mention("ou_alice", "Alice", "@_user_2"),
        ]
        result = normalize_mentions(text, mentions, BOT_OPEN_ID)
        # Bot placeholder stripped, Alice placeholder replaced
        assert '<at user_id="ou_alice">Alice</at>' in result
        assert "@_user_1" not in result
        assert "@_user_2" not in result

    def test_at_all_replaced(self):
        text = "@_all hello everyone"
        mentions = [{"key": "@_all", "id": {"open_id": ""}, "name": "所有人"}]
        result = normalize_mentions(text, mentions, BOT_OPEN_ID)
        assert "@所有人" in result
        assert "@_all" not in result

    def test_bot_placeholder_stripped(self):
        text = "@_user_1 do something"
        mentions = [_make_mention(BOT_OPEN_ID, "Bot", "@_user_1")]
        result = normalize_mentions(text, mentions, BOT_OPEN_ID)
        assert result == "do something"

    def test_empty_mentions_strips_whitespace(self):
        result = normalize_mentions("  hello  ", [], BOT_OPEN_ID)
        assert result == "hello"


# ──────────────── Outbound formatting ────────────────


class TestOutboundFormatting:
    def test_format_mention_for_text(self):
        t = MentionTarget(open_id="ou_alice", name="Alice", key="@_user_1")
        assert format_mention_for_text(t) == '<at user_id="ou_alice">Alice</at>'

    def test_format_mention_for_card(self):
        t = MentionTarget(open_id="ou_alice", name="Alice", key="@_user_1")
        assert format_mention_for_card(t) == "<at id=ou_alice></at>"

    def test_build_mentioned_message(self):
        targets = [
            MentionTarget(open_id="ou_alice", name="Alice", key="@_user_1"),
            MentionTarget(open_id="ou_bob", name="Bob", key="@_user_2"),
        ]
        result = build_mentioned_message(targets, "Hello!")
        assert result == '<at user_id="ou_alice">Alice</at> <at user_id="ou_bob">Bob</at> Hello!'

    def test_build_mentioned_message_empty(self):
        assert build_mentioned_message([], "Hello!") == "Hello!"

    def test_build_mentioned_card_content(self):
        targets = [
            MentionTarget(open_id="ou_alice", name="Alice", key="@_user_1"),
        ]
        result = build_mentioned_card_content(targets, "Reply content")
        assert result == "<at id=ou_alice></at> Reply content"

    def test_build_mentioned_card_content_empty(self):
        assert build_mentioned_card_content([], "Reply content") == "Reply content"


# ──────────────── build_sender_mention_target ────────────────


class TestBuildSenderMentionTarget:
    def test_group_chat_with_sender(self):
        msg = _make_msg(chat_type="group", sender_open_id="ou_alice", sender_name="Alice")
        target = build_sender_mention_target(msg)
        assert target is not None
        assert target.open_id == "ou_alice"
        assert target.name == "Alice"
        assert target.key == ""

    def test_p2p_chat_returns_none(self):
        msg = _make_msg(chat_type="p2p", sender_open_id="ou_alice", sender_name="Alice")
        assert build_sender_mention_target(msg) is None

    def test_no_sender_open_id_returns_none(self):
        msg = _make_msg(chat_type="group", sender_open_id=None, sender_name="Alice")
        assert build_sender_mention_target(msg) is None

    def test_fallback_to_user_id_for_name(self):
        msg = _make_msg(chat_type="group", sender_open_id="ou_alice", sender_name=None)
        target = build_sender_mention_target(msg)
        assert target is not None
        assert target.name == "u1"  # falls back to user_id


# ──────────────── build_mention_system_hint ────────────────


class TestBuildMentionSystemHint:
    def test_no_mentions_returns_none(self):
        msg = _make_msg(has_any_mention=False, mentions=[])
        assert build_mention_system_hint(msg) is None

    def test_has_any_mention_only(self):
        msg = _make_msg(has_any_mention=True, mentions=[])
        hint = build_mention_system_hint(msg)
        assert hint is not None
        assert "<at" in hint
        assert "Feishu entity" in hint

    def test_group_chat_with_sender_shows_auto_inject(self):
        msg = _make_msg(
            has_any_mention=True, chat_type="group",
            sender_open_id="ou_alice", sender_name="Alice",
        )
        hint = build_mention_system_hint(msg)
        assert hint is not None
        assert "Alice" in hint
        assert "auto-inject" in hint
        assert "sender" in hint

    def test_p2p_chat_no_auto_inject(self):
        msg = _make_msg(
            has_any_mention=True, chat_type="p2p",
            sender_open_id="ou_alice", sender_name="Alice",
        )
        hint = build_mention_system_hint(msg)
        # Should have <at> tag hint but NOT auto-inject hint
        assert hint is not None
        assert "Feishu entity" in hint
        assert "auto-inject" not in hint

    def test_group_no_sender_id_no_auto_inject(self):
        msg = _make_msg(
            has_any_mention=True, chat_type="group",
            sender_open_id=None,
        )
        hint = build_mention_system_hint(msg)
        assert "auto-inject" not in hint
