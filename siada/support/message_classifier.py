from typing import Optional, Any, Tuple


def get_role_from_item(item: Any) -> Optional[str]:
    """
    Extract role information from a message item.
    
    Args:
        item: Message item to extract role from
        
    Returns:
        Optional[str]: Role string ('user', 'assistant', 'system', 'developer', 'tool') or None
    """
    role, _ = get_role_and_type_from_item(item)
    return role


def get_item_type_from_item(item: Any) -> Optional[str]:
    """
    Extract item type information from a message item.
    
    Args:
        item: Message item to extract type from
        
    Returns:
        Optional[str]: Item type string or None
    """
    _, item_type = get_role_and_type_from_item(item)
    return item_type


def get_role_and_type_from_item(item: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract both role and item type information from a message item.
    
    Args:
        item: Message item to extract role and type from
        
    Returns:
        Tuple[Optional[str], Optional[str]]: (role, item_type) where:
            - role: 'user', 'assistant', 'system', 'developer', 'tool' or None
            - item_type: specific item type string or None
    """
    
    if not isinstance(item, dict):
        return None, None
    
    item_type = item.get("type")
    
    # 1. First, check explicit type fields for all typed messages and tool calls
    if item_type == "message":
        role = item.get("role")
        if role in ("user", "assistant", "system", "developer"):
            return role, "message"
    
    # 3. Check tool call types from assistant
    if item_type == "function_call":
        return "assistant", "function_call"
    elif item_type == "file_search_call":
        return "assistant", "file_search_call"
    elif item_type == "computer_call":
        return "assistant", "computer_call"
    elif item_type == "function_web_search":
        return "assistant", "function_web_search"
    elif item_type == "code_interpreter_call":
        return "assistant", "code_interpreter_call"
    elif item_type == "image_generation_call":
        return "assistant", "image_generation_call"
    elif item_type == "local_shell_call":
        return "assistant", "local_shell_call"
    elif item_type == "mcp_call":
        return "assistant", "mcp_call"
    elif item_type == "custom_tool_call":
        return "assistant", "custom_tool_call"
    
    # 4. Check tool output types
    elif item_type == "function_call_output":
        return "tool", "function_call_output"
    elif item_type == "computer_call_output":
        return "tool", "computer_call_output"
    elif item_type == "local_shell_call_output":
        return "tool", "local_shell_call_output"
    elif item_type == "custom_tool_call_output":
        return "tool", "custom_tool_call_output"
    
    # 5. Reasoning content from assistant
    elif item_type == "reasoning":
        return "assistant", "reasoning"
    
    # 6. MCP types without specific roles
    elif item_type == "mcp_list_tools":
        return None, "mcp_list_tools"
    elif item_type == "mcp_approval_request":
        return None, "mcp_approval_request"
    elif item_type == "mcp_approval_response":
        return None, "mcp_approval_response"
    elif item_type == "item_reference":
        return None, "item_reference"
    
    # 2. Handle EasyInputMessageParam - simple format {content: ..., role: ...} without type
    # This handles both cases with and without explicit type field  
    elif item_type is None and "content" in item and "role" in item:
        role = item.get("role")
        if role in ("user", "assistant", "system", "developer"):
            return role, "easy_input_message"
    
    # 3. Handle unknown types or cases with type but no specific handling
    return None, item_type
