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
    _process_image_result_filter
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


class TestProcessImageResultFilter:
    """Test cases for _process_image_result_filter function."""
    
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
        result = _process_image_result_filter(item)
        assert result["type"] == "function_call_output"
        assert result["output"] == "This image has been cropped and read. To avoid an excessively long token, this message is ignored"
        # Ensure original item is not modified
        assert item["output"] == image_result_json
    
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
        result = _process_image_result_filter(item)
        assert result == item  # Should return the same item unchanged
    
    def test_non_function_call_output_type(self):
        """Test item with different type."""
        item = {
            "type": "user",
            "content": "Hello"
        }
        result = _process_image_result_filter(item)
        assert result == item  # Should return the same item unchanged
    
    def test_missing_output_attribute(self):
        """Test function_call_output item without output attribute."""
        item = {
            "type": "function_call_output"
            # Missing output attribute
        }
        result = _process_image_result_filter(item)
        assert result == item  # Should return the same item unchanged


class TestProcessInput:
    """Test cases for process_input function."""
    
    def test_string_input(self):
        """Test with string input."""
        result = process_input("test message")
        assert result == "test message"
    
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
        """Test replacing output of function_call_output with ImageResult structure."""
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
        # Should keep all items but replace the output of function_call_output item
        assert len(result) == 4
        assert result[0] == input_list[0]  # user message
        assert result[1]["type"] == "function_call_output"  # function_call_output item
        assert result[1]["output"] == "This image has been cropped and read. To avoid an excessively long token, this message is ignored"
        assert result[2] == input_list[2]  # assistant message
        assert result[3] == input_list[3]  # last user message (not processed)
    
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
            },  # Should have output replaced
            {
                "type": "function_call_output", 
                "output": non_image_json
            },  # Should be kept unchanged
            {
                "type": "function_call_output",
                "output": image_result_json
            },  # Should have output replaced
            {"type": "assistant", "content": "End"}
        ]
        
        result = process_input(input_list)
        # Should keep all items but replace output of ImageResult items
        assert len(result) == 5
        assert result[0] == input_list[0]  # user message
        assert result[1]["type"] == "function_call_output"  # first image function_call_output
        assert result[1]["output"] == "This image has been cropped and read. To avoid an excessively long token, this message is ignored"
        assert result[2] == input_list[2]  # non-image function_call_output (unchanged)
        assert result[3]["type"] == "function_call_output"  # second image function_call_output
        assert result[3]["output"] == "This image has been cropped and read. To avoid an excessively long token, this message is ignored"
        assert result[4] == input_list[4]  # assistant message
    
    def test_non_dict_items_unchanged(self):
        """Test that non-dictionary items are kept unchanged."""
        class MockItem:
            def __init__(self, type_val, output_val=None):
                self.type = type_val
                if output_val is not None:
                    self.output = output_val
        
        input_list = [
            {"type": "user", "content": "Start"},
            MockItem("function_call_output", "some output"),  # Non-dict item, should be unchanged
            {"type": "assistant", "content": "End"}
        ]
        
        result = process_input(input_list)
        # Should keep all items unchanged since non-dict items are not processed
        assert len(result) == 3
        assert result[0] == input_list[0]
        assert result[1] == input_list[1]  # MockItem should be unchanged
        assert result[2] == input_list[2]
    
    def test_invalid_input_type(self):
        """Test with invalid input type."""
        with pytest.raises(ValueError, match="Input must be a string or a list of TResponseInputItem"):
            process_input(123)
        
        with pytest.raises(ValueError, match="Input must be a string or a list of TResponseInputItem"):
            process_input(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
