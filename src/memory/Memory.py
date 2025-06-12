"""
记忆模块

提供记忆agent工作过程中的全部上下文的功能
"""
from __future__ import annotations
from typing import Generic, TypeVar, Any

from agents import TContext
from pydantic import BaseModel

from src.memory.SystemContext import SystemContext
from src.user_agents.examples.air_customer_agent import AirlineAgentContext
from src.user_agents import agent_map

# 泛型类型变量，用于表示不同类型的model_context
T = TypeVar('T')


class Memory(BaseModel, Generic[T, TContext]):
    """
    记忆类
    
    负责记忆agent工作过程中的全部上下文
    包含三个字段：session_id, system_context, model_context
    """
    # 配置模型，允许任意类型
    model_config = {
        "arbitrary_types_allowed": True
    }
    
    session_id: str  # 由前端传入，作为必需参数
    system_context: SystemContext[TContext]  # 使用泛型SystemContext
    model_context: T
    
    @classmethod
    def create(cls, session_id: str, current_agent: str, model_context: T) -> "Memory[T, TContext]":
        """
        创建一个新的Memory实例
        
        Args:
            session_id: 会话ID，由前端传入
            current_agent: 当前agent的名称
            model_context: 模型上下文对象
            
        Returns:
            创建的Memory对象
        """
        agent = agent_map[current_agent]
        # 直接创建SystemContext实例
        system_context = SystemContext(current_agent=agent)

        if current_agent == "air_customer":
            model_context = AirlineAgentContext()
            
        return cls(
            session_id=session_id,
            system_context=system_context,
            model_context=model_context
        )
