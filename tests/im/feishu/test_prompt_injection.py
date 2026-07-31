"""Unit tests for siada/im/feishu/prompt_injection.py.

Test cases from design document §8.
"""
from __future__ import annotations

import json

import pytest

from siada.im.feishu.prompt_injection import build_inbound_user_context_suffix
from siada.im.models import IMMessage, MentionTarget


# ── helpers ──────────────────────────────────────────────────────────


def _make_msg(**kwargs) -> IMMessage:
    defaults = dict(
        request_id="req_001",
        platform="lark",
        user_id="张三",
        chat_id="oc_group_xxx",
        chat_type="group",
        content_type="text",
        content="帮我看看登录失败问题",
        timestamp=0.0,
        message_id="om_xxx",
        sender_name="张三",
        sender_open_id="ou_abc123",
        mentioned_bot=False,
        has_any_mention=False,
        mentions=[],
    )
    defaults.update(kwargs)
    return IMMessage(**defaults)


def _parse_block(prefix: str, label: str) -> dict:
    """Extract and parse the JSON from a labelled untrusted block."""
    marker = f"// {label} (untrusted metadata):\n"
    assert marker in prefix, f"Block '{label}' not found in prefix:\n{prefix}"
    start = prefix.index(marker) + len(marker)
    # find the end of this JSON object (next block or end of string)
    rest = prefix[start:]
    # JSON object ends at the first closing brace that balances
    depth = 0
    end = 0
    for i, ch in enumerate(rest):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(rest[:end])


# ── Test 1: DM basics ─────────────────────────────────────────────────


class TestDMBasic:
    def setup_method(self):
        self.msg = _make_msg(chat_type="p2p", chat_id="oc_dm_xxx")
        self.prefix = build_inbound_user_context_suffix(
            self.msg, include_conversation_info=True,
        )

    def test_prefix_not_none(self):
        assert self.prefix is not None

    def test_has_conversation_block(self):
        assert "// Conversation info (untrusted metadata):" in self.prefix

    def test_has_sender_id(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert data["sender_id"] == "张三"

    def test_has_message_id(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert data["message_id"] == "om_xxx"

    def test_no_sender_field(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert "sender" not in data

    def test_no_chat_id(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert "chat_id" not in data

    def test_no_is_group_chat(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert "is_group_chat" not in data

    def test_no_was_mentioned(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert "was_mentioned" not in data

    def test_no_sender_block(self):
        assert "Sender (untrusted metadata)" not in self.prefix


# ── Test 2: DM with feature disabled ─────────────────────────────────


class TestDMDisabled:
    def test_no_output(self):
        msg = _make_msg(chat_type="p2p", chat_id="oc_dm_xxx")
        result = build_inbound_user_context_suffix(msg, include_conversation_info=False)
        assert result is None

    def test_still_returns_mention_hints_if_present(self):
        """Even with context disabled, mention hints are still emitted."""
        msg = _make_msg(
            chat_type="p2p",
            chat_id="oc_dm_xxx",
            has_any_mention=True,
        )
        result = build_inbound_user_context_suffix(msg, include_conversation_info=False)
        assert result is not None
        assert "[System:" in result
        assert "Conversation info" not in result


# ── Test 3: Group chat basics ─────────────────────────────────────────


class TestGroupBasic:
    def setup_method(self):
        self.msg = _make_msg()
        self.prefix = build_inbound_user_context_suffix(
            self.msg, include_conversation_info=True,
        )

    def test_has_chat_id(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert data["chat_id"] == "oc_group_xxx"

    def test_has_is_group_chat(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert data["is_group_chat"] is True

    def test_no_was_mentioned(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert "was_mentioned" not in data

    def test_no_sender_block(self):
        assert "Sender (untrusted metadata)" not in self.prefix


# ── Test 4: Group chat with @bot ──────────────────────────────────────


class TestGroupWithBotMention:
    def setup_method(self):
        self.msg = _make_msg(
            mentioned_bot=True,
            has_any_mention=True,
            sender_open_id="ou_abc123",
        )
        self.prefix = build_inbound_user_context_suffix(
            self.msg, include_conversation_info=True,
        )

    def test_was_mentioned_true(self):
        data = _parse_block(self.prefix, "Conversation info")
        assert data["was_mentioned"] is True

    def test_mention_hint_present(self):
        assert "[System: This message includes Feishu @-mention tags" in self.prefix

    def test_auto_notify_hint_present(self):
        assert "[System: The following users will be auto-notified" in self.prefix


# ── Test 5: Group chat with reply_to_id ───────────────────────────────


class TestGroupWithReplyTo:
    def test_reply_to_id_from_parent_id(self):
        msg = _make_msg(parent_id="om_parent_xxx")
        prefix = build_inbound_user_context_suffix(msg, include_conversation_info=True)
        data = _parse_block(prefix, "Conversation info")
        assert data["reply_to_id"] == "om_parent_xxx"

    def test_reply_to_id_from_root_id_when_no_parent(self):
        msg = _make_msg(parent_id=None, root_id="om_root_xxx")
        prefix = build_inbound_user_context_suffix(msg, include_conversation_info=True)
        data = _parse_block(prefix, "Conversation info")
        assert data["reply_to_id"] == "om_root_xxx"

    def test_no_reply_to_id_when_absent(self):
        msg = _make_msg(parent_id=None, root_id=None)
        prefix = build_inbound_user_context_suffix(msg, include_conversation_info=True)
        data = _parse_block(prefix, "Conversation info")
        assert "reply_to_id" not in data


# ── Test 6: Group chat with non-bot mentions ──────────────────────────


class TestGroupWithOtherMentions:
    def test_mention_hint_lists_mentioned_users(self):
        msg = _make_msg(
            has_any_mention=True,
            mentions=[MentionTarget(open_id="ou_alice", name="Alice", key="@_user_1")],
            sender_open_id="ou_abc123",
        )
        prefix = build_inbound_user_context_suffix(msg, include_conversation_info=True)
        assert "Alice" in prefix
        assert "[System: The following users will be auto-notified" in prefix


# ── Test 7: Group chat with feature disabled ──────────────────────────


class TestGroupDisabled:
    def setup_method(self):
        self.msg = _make_msg(
            has_any_mention=True,
            mentioned_bot=True,
            sender_open_id="ou_abc123",
        )
        self.prefix = build_inbound_user_context_suffix(
            self.msg, include_conversation_info=False,
        )

    def test_no_conversation_info_block(self):
        assert "Conversation info" not in (self.prefix or "")



    def test_mention_hints_still_present(self):
        assert self.prefix is not None
        assert "[System:" in self.prefix
