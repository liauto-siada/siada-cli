"""Tests for siada.support.chat_compat_items.

The helpers rewrite Responses-only item shapes into ChatCompletions-safe
proxies so replayed history survives protocol conversion (model switch,
sub-agent on another model, compaction summarization, token counting):

1. native ``apply_patch`` items -> function-call-shaped proxies;
2. id-less assistant output messages (the compaction acknowledgment shape)
   -> plain assistant text messages.
"""
from __future__ import annotations

import json

import pytest

from siada.support.chat_compat_items import (
    NATIVE_PATCH_CALL,
    NATIVE_PATCH_CALL_OUTPUT,
    PROXY_TOOL_NAME,
    to_chat_compatible_item,
    to_chat_compatible_items,
)

_OPERATION = {"type": "update_file", "path": "a.py", "diff": "@@\n-old\n+new\n"}


def _patch_call(call_id: str = "c1") -> dict:
    return {
        "type": NATIVE_PATCH_CALL,
        "id": "apc_1",
        "call_id": call_id,
        "status": "completed",
        "operation": dict(_OPERATION),
        "created_by": "direct",
    }


def _patch_output(call_id: str = "c1") -> dict:
    return {
        "type": NATIVE_PATCH_CALL_OUTPUT,
        "id": "apco_1",
        "call_id": call_id,
        "status": "completed",
        "output": "Updated a.py",
    }


class TestToChatCompatibleItem:
    def test_patch_call_becomes_function_call_proxy(self):
        proxy = to_chat_compatible_item(_patch_call())
        assert proxy == {
            "type": "function_call",
            "call_id": "c1",
            "name": PROXY_TOOL_NAME,
            "arguments": json.dumps(
                {"operation": _OPERATION}, ensure_ascii=False, separators=(",", ":")
            ),
        }

    def test_patch_output_becomes_function_call_output(self):
        proxy = to_chat_compatible_item(_patch_output())
        assert proxy == {
            "type": "function_call_output",
            "call_id": "c1",
            "output": "Updated a.py",
        }

    def test_pairing_key_falls_back_to_item_id(self):
        call = _patch_call()
        call.pop("call_id")
        assert to_chat_compatible_item(call)["call_id"] == "apc_1"

    def test_non_string_output_is_json_encoded(self):
        output = _patch_output()
        output["output"] = {"text": "ok"}
        proxy = to_chat_compatible_item(output)
        assert proxy["output"] == '{"text":"ok"}'

    def test_non_patch_item_returned_unchanged(self):
        item = {"role": "user", "content": "hi"}
        assert to_chat_compatible_item(item) is item

    def test_pydantic_object_form_supported(self):
        from openai.types.responses import ResponseApplyPatchToolCall

        obj = ResponseApplyPatchToolCall(
            id="apc_x",
            call_id="cx",
            type=NATIVE_PATCH_CALL,
            status="completed",
            operation={"type": "update_file", "path": "b.py", "diff": "@@"},
        )
        proxy = to_chat_compatible_item(obj)
        assert proxy["type"] == "function_call"
        assert proxy["call_id"] == "cx"
        assert proxy["name"] == PROXY_TOOL_NAME
        payload = json.loads(proxy["arguments"])
        assert payload["operation"]["path"] == "b.py"


class TestToChatCompatibleItems:
    def test_returns_same_object_when_nothing_to_rewrite(self):
        items = [
            {"role": "user", "content": "hi"},
            {"type": "function_call", "call_id": "c", "name": "x", "arguments": "{}"},
        ]
        assert to_chat_compatible_items(items) is items

    def test_rewrites_pairs_and_keeps_other_items(self):
        items = [
            {"role": "user", "content": "hi"},
            _patch_call(),
            _patch_output(),
            {"role": "user", "content": "bye"},
        ]

        out = to_chat_compatible_items(items)

        assert out is not items
        assert [i.get("type") or i.get("role") for i in out] == [
            "user",
            "function_call",
            "function_call_output",
            "user",
        ]
        # Untouched neighbours keep their identity.
        assert out[0] is items[0]
        assert out[3] is items[3]
        # The caller's list and its items are never mutated.
        assert items[1]["type"] == NATIVE_PATCH_CALL
        assert items[2]["type"] == NATIVE_PATCH_CALL_OUTPUT

    def test_non_list_inputs_pass_through(self):
        assert to_chat_compatible_items("hello") == "hello"
        marker = {"type": NATIVE_PATCH_CALL}
        assert to_chat_compatible_items(marker) is marker
        assert to_chat_compatible_items([]) == []


def _ack_message() -> dict:
    """The compaction acknowledgment shape: id-less assistant output message."""
    return {
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "output_text",
                "text": "Got it. Thanks for the additional context!",
            }
        ],
    }


class TestIdLessAssistantOutputMessage:
    """SDK route check: without an ``id`` these items break the converter.

    ``Converter.maybe_response_output_message`` requires ``{"id", "content"}``,
    so an id-less assistant message falls into the EasyInputMessage branch,
    whose parser rejects ``output_text`` parts.  The rewrite converts the item
    into a string-content assistant message, which both the converter and the
    Responses input schema accept.
    """

    def test_id_less_output_text_message_is_rewritten(self):
        proxy = to_chat_compatible_item(_ack_message())
        assert proxy == {
            "type": "message",
            "role": "assistant",
            "content": "Got it. Thanks for the additional context!",
        }

    def test_rewritten_message_converts_offline(self):
        from agents.models.chatcmpl_converter import Converter

        messages = Converter.items_to_messages(
            [to_chat_compatible_item(_ack_message())]
        )
        assert messages == [
            {"role": "assistant", "content": "Got it. Thanks for the additional context!"}
        ]

    def test_raw_ack_message_fails_without_rewrite(self):
        """Anchor: the raw shape is exactly what used to break replay."""
        from agents.exceptions import UserError
        from agents.models.chatcmpl_converter import Converter

        with pytest.raises(UserError, match="Unknown content"):
            Converter.items_to_messages([_ack_message()])

    def test_message_with_id_is_untouched(self):
        item = _ack_message()
        item["id"] = "msg_fixture_1"
        assert to_chat_compatible_item(item) is item

    def test_string_content_assistant_message_is_untouched(self):
        item = {"role": "assistant", "content": "already fine"}
        assert to_chat_compatible_item(item) is item

    def test_non_assistant_output_message_is_untouched(self):
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "output_text", "text": "x"}],
        }
        assert to_chat_compatible_item(item) is item

    def test_multiple_output_text_parts_join_like_the_sdk(self):
        item = {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "line 1"},
                {"type": "output_text", "text": "line 2"},
            ],
        }
        proxy = to_chat_compatible_item(item)
        assert proxy["content"] == "line 1\nline 2"

    def test_compacted_history_rewrites_only_the_ack(self):
        history = [
            {"role": "user", "content": "orig"},
            {"role": "user", "content": "<context>summary</context>"},
            _ack_message(),
            {"role": "user", "content": "next"},
        ]

        out = to_chat_compatible_items(history)

        assert out is not history
        assert out[0] is history[0]
        assert out[1] is history[1]
        assert out[3] is history[3]
        assert out[2] == {
            "type": "message",
            "role": "assistant",
            "content": "Got it. Thanks for the additional context!",
        }
        # The caller's history is never mutated.
        assert history[2]["content"][0]["type"] == "output_text"