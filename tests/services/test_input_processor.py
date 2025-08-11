#!/usr/bin/env python3
"""
Test cases for input_processor module.

Tests the process_input function with various input scenarios,
including filtering of function_call_output items with ImageResult structure.
"""

import json
import pytest
from agents import TResponseInputItem
from siada.services.input_processor import (
    process_input, 
    _is_image_result_structure, 
    _check_output_for_image_result,
    _should_filter_function_call_output
)


class TestIsImageResultStructure:
    """Test cases for _is_image_result_structure helper function."""
    
    def test_valid_image_result_structure(self):
        """Test with valid ImageResult structure."""
        valid_data = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            }
        }
        assert _is_image_result_structure(valid_data) is True
    
    def test_invalid_type(self):
        """Test with invalid type field."""
        invalid_data = {
            "type": "text",
            "image_url": {
                "url": "data:image/png;base64,test"
            }
        }
        assert _is_image_result_structure(invalid_data) is False
    
    def test_missing_image_url(self):
        """Test with missing image_url field."""
        invalid_data = {
            "type": "image_url"
        }
        assert _is_image_result_structure(invalid_data) is False
    
    def test_invalid_image_url_structure(self):
        """Test with invalid image_url structure."""
        invalid_data = {
            "type": "image_url",
            "image_url": "not_a_dict"
        }
        assert _is_image_result_structure(invalid_data) is False
    
    def test_missing_url_in_image_url(self):
        """Test with missing url field in image_url."""
        invalid_data = {
            "type": "image_url",
            "image_url": {
                "other_field": "value"
            }
        }
        assert _is_image_result_structure(invalid_data) is False
    
    def test_non_dict_input(self):
        """Test with non-dictionary input."""
        assert _is_image_result_structure("not_a_dict") is False
        assert _is_image_result_structure(None) is False
        assert _is_image_result_structure(123) is False


class TestCheckOutputForImageResult:
    """Test cases for _check_output_for_image_result helper function."""
    
    def test_valid_image_result_json_string(self):
        """Test with valid ImageResult JSON string."""
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_data"
            }
        })
        assert _check_output_for_image_result(image_result_json) is True
    
    def test_invalid_json_string(self):
        """Test with invalid JSON string."""
        assert _check_output_for_image_result("invalid json {") is False
    
    def test_non_image_result_json(self):
        """Test with valid JSON but not ImageResult structure."""
        non_image_json = json.dumps({
            "type": "text",
            "content": "Some text"
        })
        assert _check_output_for_image_result(non_image_json) is False
    
    def test_non_string_input(self):
        """Test with non-string input."""
        assert _check_output_for_image_result(123) is False
        assert _check_output_for_image_result(None) is False
        assert _check_output_for_image_result({"type": "image_url"}) is False


class TestShouldFilterFunctionCallOutput:
    """Test cases for _should_filter_function_call_output helper function."""
    
    def test_dict_with_image_result_output(self):
        """Test dictionary item with ImageResult output."""
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_data"
            }
        })
        
        item = {
            "type": "function_call_output",
            "output": image_result_json
        }
        assert _should_filter_function_call_output(item) is True
    
    def test_dict_with_non_image_output(self):
        """Test dictionary item with non-ImageResult output."""
        non_image_json = json.dumps({
            "type": "text",
            "content": "Some text"
        })
        
        item = {
            "type": "function_call_output",
            "output": non_image_json
        }
        assert _should_filter_function_call_output(item) is False
    
    def test_object_with_image_result_output(self):
        """Test object item with ImageResult output."""
        class MockItem:
            def __init__(self):
                self.type = "function_call_output"
                self.output = json.dumps({
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,test_data"
                    }
                })
        
        item = MockItem()
        assert _should_filter_function_call_output(item) is True
    
    def test_object_with_non_image_output(self):
        """Test object item with non-ImageResult output."""
        class MockItem:
            def __init__(self):
                self.type = "function_call_output"
                self.output = json.dumps({
                    "type": "text",
                    "content": "Some text"
                })
        
        item = MockItem()
        assert _should_filter_function_call_output(item) is False
    
    def test_non_function_call_output_type(self):
        """Test item with different type."""
        item = {
            "type": "user",
            "content": "Hello"
        }
        assert _should_filter_function_call_output(item) is False
    
    def test_missing_output_attribute(self):
        """Test function_call_output item without output attribute."""
        item = {
            "type": "function_call_output"
            # Missing output attribute
        }
        assert _should_filter_function_call_output(item) is False
    
    def test_object_missing_output_attribute(self):
        """Test object function_call_output item without output attribute."""
        class MockItem:
            def __init__(self):
                self.type = "function_call_output"
                # Missing output attribute
        
        item = MockItem()
        assert _should_filter_function_call_output(item) is False
    
    def test_invalid_item_structure(self):
        """Test with invalid item structure."""
        assert _should_filter_function_call_output(None) is False
        assert _should_filter_function_call_output("not_an_item") is False
        assert _should_filter_function_call_output(123) is False


class TestProcessInput:
    """Test cases for process_input function."""
    
    def test_string_input(self):
        """Test with string input."""
        result = process_input("test message")
        assert len(result) == 1
        assert result[0]["content"] == "test message"
    
    def test_empty_list_input(self):
        """Test with empty list input."""
        result = process_input([])
        assert result == []
    
    def test_single_item_list(self):
        """Test with single item list (should not be filtered)."""
        input_list = [{"type": "user", "content": "test"}]
        result = process_input(input_list)
        assert len(result) == 1
        assert result[0] == input_list[0]
    
    def test_list_without_function_call_output(self):
        """Test with list containing no function_call_output items."""
        input_list = [
            {"type": "user", "content": "Hello"},
            {"type": "assistant", "content": "Hi there"},
            {"type": "user", "content": "How are you?"}
        ]
        result = process_input(input_list)
        assert len(result) == 3
        assert result == input_list
    
    def test_filter_function_call_output_with_image_result(self):
        """Test filtering of function_call_output with ImageResult structure."""
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_image_data"
            }
        })
        
        input_list = [
            {"type": "user", "content": "Take a screenshot"},
            {
                "type": "function_call_output",
                "output": image_result_json
            },
            {"type": "assistant", "content": "Screenshot taken"},
            {"type": "user", "content": "Thanks"}  # This is the last element, should not be processed
        ]
        
        result = process_input(input_list)
        # Should filter out the function_call_output item but keep others
        assert len(result) == 3
        assert result[0] == input_list[0]  # user message
        assert result[1] == input_list[2]  # assistant message
        assert result[2] == input_list[3]  # last user message (not processed)
    
    def test_keep_function_call_output_without_image_result(self):
        """Test keeping function_call_output without ImageResult structure."""
        non_image_output = json.dumps({
            "type": "text",
            "content": "Some other output"
        })
        
        input_list = [
            {"type": "user", "content": "Do something"},
            {
                "type": "function_call_output",
                "output": non_image_output
            },
            {"type": "assistant", "content": "Done"}
        ]
        
        result = process_input(input_list)
        # Should keep all items since the function_call_output doesn't have ImageResult structure
        assert len(result) == 3
        assert result == input_list
    
    def test_keep_function_call_output_with_invalid_json(self):
        """Test keeping function_call_output with invalid JSON."""
        input_list = [
            {"type": "user", "content": "Do something"},
            {
                "type": "function_call_output",
                "output": "invalid json {"
            },
            {"type": "assistant", "content": "Done"}
        ]
        
        result = process_input(input_list)
        # Should keep all items since JSON parsing fails
        assert len(result) == 3
        assert result == input_list
    
    def test_keep_function_call_output_with_non_string_output(self):
        """Test keeping function_call_output with non-string output."""
        input_list = [
            {"type": "user", "content": "Do something"},
            {
                "type": "function_call_output",
                "output": {"not": "a string"}
            },
            {"type": "assistant", "content": "Done"}
        ]
        
        result = process_input(input_list)
        # Should keep all items since output is not a string
        assert len(result) == 3
        assert result == input_list
    
    def test_skip_last_element_processing(self):
        """Test that the last element is never filtered, even if it matches criteria."""
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_image_data"
            }
        })
        
        input_list = [
            {"type": "user", "content": "Take a screenshot"},
            {
                "type": "function_call_output",
                "output": image_result_json
            }  # This is the last element, should not be filtered
        ]
        
        result = process_input(input_list)
        # Should keep both items since the last element is not processed
        assert len(result) == 2
        assert result == input_list
    
    def test_multiple_function_call_outputs(self):
        """Test with multiple function_call_output items."""
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_image_data"
            }
        })
        
        non_image_json = json.dumps({
            "type": "text",
            "content": "Some text"
        })
        
        input_list = [
            {"type": "user", "content": "Start"},
            {
                "type": "function_call_output",
                "output": image_result_json
            },  # Should be filtered
            {
                "type": "function_call_output", 
                "output": non_image_json
            },  # Should be kept
            {
                "type": "function_call_output",
                "output": image_result_json
            },  # Should be filtered
            {"type": "assistant", "content": "End"}
        ]
        
        result = process_input(input_list)
        # Should filter out the two ImageResult items but keep others
        assert len(result) == 3
        assert result[0] == input_list[0]  # user message
        assert result[1] == input_list[2]  # non-image function_call_output
        assert result[2] == input_list[4]  # assistant message
    
    def test_object_style_items(self):
        """Test with object-style items (having attributes instead of dict access)."""
        # Create mock objects with attributes
        class MockItem:
            def __init__(self, type_val, output_val=None):
                self.type = type_val
                if output_val is not None:
                    self.output = output_val
        
        image_result_json = json.dumps({
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,test_image_data"
            }
        })
        
        input_list = [
            {"type": "user", "content": "Start"},
            MockItem("function_call_output", image_result_json),  # Should be filtered
            {"type": "assistant", "content": "End"}
        ]
        
        result = process_input(input_list)
        # Should filter out the MockItem with ImageResult
        assert len(result) == 2
        assert result[0] == input_list[0]
        assert result[1] == input_list[2]
    
    def test_invalid_input_type(self):
        """Test with invalid input type."""
        with pytest.raises(ValueError, match="Input must be a string or a list of TResponseInputItem"):
            process_input(123)
        
        with pytest.raises(ValueError, match="Input must be a string or a list of TResponseInputItem"):
            process_input(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
