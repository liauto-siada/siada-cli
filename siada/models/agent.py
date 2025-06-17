"""
Agent数据模型

定义与Agent相关的请求和响应模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Tool(BaseModel):
    """工具模型"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    function: str = Field(..., description="工具函数代码")


class CreateAgentRequest(BaseModel):
    """创建Agent的请求模型"""
    name: str = Field(..., description="Agent名称")
    instructions: str = Field(..., description="Agent指令")
    tools: Optional[List[Tool]] = Field(None, description="Agent可以使用的工具列表")


class AgentResponse(BaseModel):
    """Agent响应模型"""
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent名称")
    instructions: str = Field(..., description="Agent指令")
    model: str = Field(..., description="使用的模型名称")


class RunAgentRequest(BaseModel):
    """运行Agent的请求模型"""
    agent_name: str = Field(..., description="Agent 名称")
    input: str = Field(..., description="输入文本")
    model: Optional[str] = Field("gpt-4o", description="使用的模型名称")
    max_turns: Optional[int] = Field(10, description="最大运行轮数")
    session_id: Optional[str] = Field(None, description="会话ID")


class RunAgentResponse(BaseModel):
    """运行Agent的响应模型"""
    final_output: str = Field(..., description="最终输出")
    turns: int = Field(..., description="运行轮数")
    completed: bool = Field(..., description="是否完成")
    trace_id: Optional[str] = Field(None, description="跟踪ID")
