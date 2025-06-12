"""
系统上下文模块

提供系统级别的上下文信息存储
"""
from __future__ import annotations

from typing import Any, Optional, TypeVar, Generic

from agents import (
    Agent,
    TContext
)

# 使用普通Python类而不是Pydantic模型，但保留泛型
class SystemContext(Generic[TContext]):
    """
    系统上下文类
    
    存储系统级别的上下文信息，如当前正在使用的agent
    """
    def __init__(self, current_agent: Agent[TContext]):
        """
        初始化SystemContext实例
        
        Args:
            current_agent: 当前正在使用的agent
        """
        self.current_agent = current_agent
