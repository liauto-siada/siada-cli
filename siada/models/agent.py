"""Request and response data models for agents."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Tool(BaseModel):
    """Tool model."""
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    function: str = Field(..., description="Tool function code")


class CreateAgentRequest(BaseModel):
    """Request to create an agent."""
    name: str = Field(..., description="Agent name")
    instructions: str = Field(..., description="Agent instructions")
    tools: Optional[List[Tool]] = Field(None, description="Tools available to the agent")


class AgentResponse(BaseModel):
    """Agent response model."""
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent name")
    instructions: str = Field(..., description="Agent instructions")
    model: str = Field(..., description="Model name")


class RunAgentRequest(BaseModel):
    """Request to run an agent."""
    agent_name: str = Field(..., description="Agent name")
    input: str = Field(..., description="Input text")
    model: Optional[str] = Field("gpt-4o", description="Model name")
    max_turns: Optional[int] = Field(10, description="Maximum turns")
    session_id: Optional[str] = Field(None, description="Session ID")


class RunAgentResponse(BaseModel):
    """Response from an agent run."""
    final_output: str = Field(..., description="Final output")
    turns: int = Field(..., description="Number of turns")
    completed: bool = Field(..., description="Whether the run completed")
    trace_id: Optional[str] = Field(None, description="Trace ID")
