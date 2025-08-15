"""
上下文管理模块

提供全局上下文管理功能，类似于Java中的ThreadLocal
支持存储多种类型的上下文变量
"""
import contextvars
from typing import Any, Dict, Optional

# 创建上下文变量字典
context_dict_var = contextvars.ContextVar('context_dict', default={})

def set_context_var(key: str, value: Any) -> None:
    """
    设置上下文变量
    
    Args:
        key: 变量名
        value: 变量值
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # 创建副本以避免修改原始字典
    new_dict[key] = value
    context_dict_var.set(new_dict)

def get_context_var(key: str, default: Any = None) -> Any:
    """
    获取上下文变量
    
    Args:
        key: 变量名
        default: 默认值，如果变量不存在则返回此值
        
    Returns:
        上下文变量值，如果不存在则返回默认值
    """
    context_dict = context_dict_var.get()
    return context_dict.get(key, default)

def remove_context_var(key: str) -> None:
    """
    移除上下文变量
    
    Args:
        key: 变量名
    """
    context_dict = context_dict_var.get()
    new_dict = dict(context_dict)  # 创建副本以避免修改原始字典
    if key in new_dict:
        del new_dict[key]
    context_dict_var.set(new_dict)

def clear_context() -> None:
    """
    清空所有上下文变量
    """
    context_dict_var.set({})

# 为了保持向后兼容性，提供session_id的专用方法
def set_session_id(session_id: str) -> None:
    """
    设置当前上下文的session_id
    
    Args:
        session_id: 会话ID
    """
    set_context_var('session_id', session_id)

def get_session_id() -> Optional[str]:
    """
    获取当前上下文的session_id
    
    Returns:
        当前上下文的session_id，如果不存在则返回None
    """
    return get_context_var('session_id')
