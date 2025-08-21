"""
Context management module

Provides global context management functionality, similar to ThreadLocal in Java
Supports storing multiple types of context variables
"""
import contextvars
from typing import Any, Dict, Optional

# Create context variable dictionary
context_dict_var = contextvars.ContextVar('context_dict', default={})

def set_context_var(key: str, value: Any) -> None:
    """
    Set context variable
    
    Args:
        key: Variable name
        value: Variable value
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # Create a copy to avoid modifying the original dictionary
    new_dict[key] = value
    context_dict_var.set(new_dict)

def get_context_var(key: str, default: Any = None) -> Any:
    """
    Get context variable
    
    Args:
        key: Variable name
        default: Default value, returns this value if variable doesn't exist
        
    Returns:
        Context variable value, returns default value if doesn't exist
    """
    context_dict = context_dict_var.get()
    return context_dict.get(key, default)

def remove_context_var(key: str) -> None:
    """
    Remove context variable
    
    Args:
        key: Variable name
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # Create a copy to avoid modifying the original dictionary
    if key in new_dict:
        del new_dict[key]
    context_dict_var.set(new_dict)

def clear_context() -> None:
    """
    Clear all context variables
    """
    context_dict_var.set({})

# To maintain backward compatibility, provide dedicated methods for session_id
def set_session_id(session_id: str) -> None:
    """
    Set session_id for current context
    
    Args:
        session_id: Session ID
    """
    set_context_var('session_id', session_id)

def get_session_id() -> Optional[str]:
    """
    Get session_id from current context
    
    Returns:
        Current context's session_id, returns None if doesn't exist
    """
    return get_context_var('session_id')
