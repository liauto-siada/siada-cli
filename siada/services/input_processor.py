import json
from typing import Dict, Any, Callable, List
from agents import TResponseInputItem


def _is_image_result_structure(data: dict) -> bool:
    """
    Check if the given data matches the ImageResult structure.
    
    Args:
        data: Dictionary to check
        
    Returns:
        True if data matches ImageResult structure, False otherwise
    """
    try:
        # Check if it has the required structure for ImageResult
        if not isinstance(data, dict):
            return False
            
        # Must have type field with value "image_url"
        if data.get("type") != "image_url":
            return False
            
        # Must have image_url field
        image_url = data.get("image_url")
        if not isinstance(image_url, dict):
            return False
            
        # image_url must have url field
        if "url" not in image_url:
            return False
            
        return True
    except (AttributeError, TypeError):
        return False


def _check_output_for_image_result(output) -> bool:
    """
    Check if the output contains ImageResult structure.
    
    Args:
        output: The output to check
        
    Returns:
        True if output contains ImageResult structure, False otherwise
    """
    if not isinstance(output, str):
        return False
        
    try:
        # Try to parse output as JSON
        parsed_output = json.loads(output)
        # Check if it matches ImageResult structure
        return _is_image_result_structure(parsed_output)
    except (json.JSONDecodeError, ValueError):
        # If JSON parsing fails, it's not an ImageResult
        return False


def _process_image_result_filter(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process function_call_output items with ImageResult structure.
    
    Args:
        item: Dictionary item to process
        
    Returns:
        Modified item with replaced output, or original item if no modification needed
    """
    # Only process function_call_output items
    if item.get('type') != "function_call_output":
        return item
    
    # Check if output contains ImageResult structure
    output = item.get('output')
    if _check_output_for_image_result(output):
        # Create a copy and replace the output
        modified_item = item.copy()
        modified_item['output'] = "This image has been cropped and read. To avoid an excessively long token, this message is ignored"
        return modified_item
    
    return item


# List of all processing functions to be applied
PROCESSING_FUNCTIONS: List[Callable[[Dict[str, Any]], Dict[str, Any]]] = [
    _process_image_result_filter,
    # Future processing functions can be added here
]


def process_input(input: str | list[TResponseInputItem]) -> str | list[TResponseInputItem]:
    """
    Process the input to ensure it is in the correct format.

    If the input is a string, it will be returned as is.
    If it is a list, each item (except the last one) will be processed through
    all registered processing functions to apply various filters and transformations.

    Args:
        input: The input to process, either a string or a list of TResponseInputItem.

    Returns:
        The processed input.
    """
    if isinstance(input, str):
        return input
    elif isinstance(input, list):
        # Create a copy of the list to avoid modifying the original
        processed_list = []
        
        # Process all elements except the last one
        for i, item in enumerate(input):
            # Skip the last element from processing
            if i == len(input) - 1:
                processed_list.append(item)
                continue
            
            # Only process dictionary items
            if isinstance(item, dict):
                processed_item = item
                # Apply all processing functions in sequence
                for process_func in PROCESSING_FUNCTIONS:
                    processed_item = process_func(processed_item)
                processed_list.append(processed_item)
            else:
                # Non-dictionary items are added as-is
                processed_list.append(item)
        
        return processed_list
    else:
        raise ValueError("Input must be a string or a list of TResponseInputItem.")
