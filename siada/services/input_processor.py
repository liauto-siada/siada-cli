import json
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


def _should_filter_function_call_output(item) -> bool:
    """
    Determine if a function_call_output item should be filtered out.
    
    Args:
        item: The item to check
        
    Returns:
        True if the item should be filtered out, False otherwise
    """
    try:
        # Check if item has type attribute equal to "function_call_output"
        if hasattr(item, 'type') and getattr(item, 'type') == "function_call_output":
            # Check if item has output attribute
            if hasattr(item, 'output'):
                output = getattr(item, 'output')
                return _check_output_for_image_result(output)
        elif isinstance(item, dict):
            # Handle dictionary-style items
            if item.get('type') == "function_call_output":
                output = item.get('output')
                return _check_output_for_image_result(output)
    except (AttributeError, TypeError):
        # If any attribute access fails, don't filter
        pass
    
    return False


def process_input(input: str | list[TResponseInputItem]) -> str | list[TResponseInputItem]:
    """
    Process the input to ensure it is in the correct format.

    If the input is a string, it will be converted to a single-item list.
    If it is already a list, it will be returned as is, but function_call_output
    items with ImageResult structure in their output will be filtered out.

    Args:
        input: The input to process, either a string or a list of TResponseInputItem.

    Returns:
        A list containing the processed input.
    """
    if isinstance(input, str):
        return input
    elif isinstance(input, list):
        # Create a copy of the list to avoid modifying the original
        filtered_list = []
        
        # Process all elements except the last one
        for i, item in enumerate(input):
            # Skip the last element from processing
            if i == len(input) - 1:
                filtered_list.append(item)
                continue
            
            # Check if this item should be filtered out
            if not _should_filter_function_call_output(item):
                filtered_list.append(item)
        
        return filtered_list
    else:
        raise ValueError("Input must be a string or a list of TResponseInputItem.")
