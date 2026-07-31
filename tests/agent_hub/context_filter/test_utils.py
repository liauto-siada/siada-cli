from __future__ import annotations
import pytest
import json

from agents.models.chatcmpl_converter import Converter

from siada.agent_hub.context_filter.utils import (
    _normalize_to_responses_items,
    compute_message_signature,
)



class TestComputeMessageSignature:
    def test_simple_string_message(self):
        message = "Hello, World!"
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
        expected = "7959b2c4af2fd6d142ba32babd30ceb7"
        assert signature == expected
    
    def test_dict_message(self):
        message = {"key": "value", "number": 42}
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
        expected = "8cf3b709add71050e2dd6aed6dd0fb79"
        assert signature == expected
    
    def test_dict_with_different_order_same_signature(self):
        message1 = {"a": 1, "b": 2, "c": 3}
        message2 = {"c": 3, "a": 1, "b": 2}
        signature1 = compute_message_signature(message1)
        signature2 = compute_message_signature(message2)
        assert signature1 == signature2
    
    def test_list_message(self):
        message = [1, 2, 3, "test", {"nested": "dict"}]
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
    
    def test_nested_structure(self):
        message = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"],
                    "data": 123
                }
            },
            "array": [1, 2, {"nested": True}]
        }
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
    
    def test_unicode_content(self):
        message = {"text": "ä˝ ĺĽ˝ä¸ç", "emoji": "đđ"}
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
    
    def test_same_content_same_signature(self):
        message = {"data": "test", "value": 100}
        signature1 = compute_message_signature(message)
        signature2 = compute_message_signature(message)
        assert signature1 == signature2
    
    def test_different_content_different_signature(self):
        message1 = {"data": "test1"}
        message2 = {"data": "test2"}
        signature1 = compute_message_signature(message1)
        signature2 = compute_message_signature(message2)
        assert signature1 != signature2
    
    def test_empty_message(self):
        message = {}
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
        expected = "99914b932bd37a50b983c5e7c90ae93b"
        assert signature == expected
    
    def test_none_value(self):
        message = {"key": None}
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
    
    def test_boolean_values(self):
        message = {"true": True, "false": False}
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32
    
    def test_numeric_types(self):
        message = {
            "int": 42,
            "float": 3.14,
            "negative": -100,
            "large": 999999999999
        }
        signature = compute_message_signature(message)
        assert isinstance(signature, str)
        assert len(signature) == 32


class TestNormalizeToResponsesItems:
    """
    Verify that ChatCompletion-style dicts injected by some provider paths
    (e.g. li/Bedrock/ADK) are rewritten to Responses-API items so that
    ``Converter.items_to_messages`` no longer raises
    ``Unhandled item type or structure``.
    """

    def test_chat_completion_assistant_with_tool_calls_is_expanded(self):
        # Reproduces the exact shape from the production log.
        items = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "toolu_bdrk_01KVMzvfk88VF7fMKRw17Z9u",
                        "type": "function",
                        "function": {
                            "name": "edit_file",
                            "arguments": '{"command":"view","path":"/x"}',
                        },
                    },
                    {
                        "id": "toolu_bdrk_015MVgXkdSLqq9CpyWrrtz6U",
                        "type": "function",
                        "function": {
                            "name": "regex_search_files",
                            "arguments": '{"directory_path":"/x"}',
                        },
                    },
                ],
            }
        ]

        normalized = _normalize_to_responses_items(items)

        # Empty content drops the textual message; both tool calls are kept.
        assert len(normalized) == 2
        assert all(it.get("type") == "function_call" for it in normalized)
        assert normalized[0]["call_id"] == "toolu_bdrk_01KVMzvfk88VF7fMKRw17Z9u"
        assert normalized[0]["name"] == "edit_file"
        assert normalized[0]["arguments"] == '{"command":"view","path":"/x"}'
        assert normalized[1]["call_id"] == "toolu_bdrk_015MVgXkdSLqq9CpyWrrtz6U"
        assert normalized[1]["name"] == "regex_search_files"

        # And critically: the converter must now accept the normalized items.
        # (No assertion on output content — we only require it not to raise.)
        Converter.items_to_messages(items=normalized)

    def test_assistant_with_text_content_and_tool_calls_preserves_text(self):
        items = [
            {
                "role": "assistant",
                "content": "Let me run two tools",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    },
                ],
            }
        ]

        normalized = _normalize_to_responses_items(items)

        # First entry is a Responses-acceptable assistant message;
        # second entry is the function_call.
        assert len(normalized) == 2
        assert normalized[0] == {"role": "assistant", "content": "Let me run two tools"}
        assert normalized[1]["type"] == "function_call"
        assert normalized[1]["call_id"] == "tc_1"
        Converter.items_to_messages(items=normalized)

    def test_chat_completion_tool_message_becomes_function_call_output(self):
        items = [
            {
                "role": "tool",
                "tool_call_id": "toolu_bdrk_xyz",
                "content": "tool result body",
            }
        ]

        normalized = _normalize_to_responses_items(items)

        assert normalized == [
            {
                "type": "function_call_output",
                "call_id": "toolu_bdrk_xyz",
                "output": "tool result body",
            }
        ]
        Converter.items_to_messages(items=normalized)

    def test_tool_message_with_list_content_is_stringified(self):
        items = [
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": [{"type": "text", "text": "hi"}],
            }
        ]

        normalized = _normalize_to_responses_items(items)

        assert normalized[0]["type"] == "function_call_output"
        # JSON-encoded so token count reflects the structured payload.
        assert json.loads(normalized[0]["output"]) == [
            {"type": "text", "text": "hi"}
        ]

    def test_dict_with_function_arguments_is_json_encoded(self):
        items = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "f",
                            # arguments occasionally arrive as a real dict
                            "arguments": {"path": "/x", "n": 3},
                        },
                    }
                ],
            }
        ]

        normalized = _normalize_to_responses_items(items)

        assert normalized[0]["type"] == "function_call"
        assert json.loads(normalized[0]["arguments"]) == {"path": "/x", "n": 3}

    def test_already_responses_items_are_passed_through(self):
        items = [
            {"role": "user", "content": "hi"},  # strict EasyInputMessage
            {
                "type": "function_call",
                "call_id": "abc",
                "name": "do",
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": "abc",
                "output": "ok",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            },
        ]

        normalized = _normalize_to_responses_items(items)

        # Identity at the list level: same items in the same order.
        assert normalized == items
        # The converter accepts them as-is.
        Converter.items_to_messages(items=normalized)

    def test_unknown_shape_is_left_for_converter_to_reject(self):
        # A dict that is neither ChatCompletion-style nor a Responses item.
        # Normalizer must NOT silently swallow it; converter should still raise.
        items = [{"role": "assistant", "extra_field": "weird"}]

        normalized = _normalize_to_responses_items(items)
        assert normalized == items
        with pytest.raises(Exception):
            Converter.items_to_messages(items=normalized)

    def test_non_dict_items_are_pass_through(self):
        items = ["raw string", 42, None]
        assert _normalize_to_responses_items(items) == items

    def test_non_list_input_is_returned_unchanged(self):
        # The normalizer is a no-op for plain strings (caller handles them
        # separately via litellm.token_counter(text=...)).
        assert _normalize_to_responses_items("hello") == "hello"

    def test_does_not_mutate_input(self):
        original = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            }
        ]
        snapshot = json.loads(json.dumps(original))
        _normalize_to_responses_items(original)
        assert original == snapshot

