from __future__ import annotations
import pytest
import json
from siada.agent_hub.context_filter.utils import compute_message_signature


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
        message = {"text": "你好世界", "emoji": "😀🎉"}
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