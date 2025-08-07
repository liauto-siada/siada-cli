"""
Context management for code agents.

Combines TracingProcessor and AgentHooks to ensure complete message history maintenance.
"""
from __future__ import annotations

from typing import Any

from agents import Agent, RunContextWrapper
from agents.lifecycle import AgentHooks
from agents.tool import Tool
from agents.tracing import TracingProcessor, Trace, Span
from agents.items import TResponseInputItem

from siada.foundation.code_agent_context import CodeAgentContext


class ContextHooks(AgentHooks[CodeAgentContext]):
    """Context management hooks for code agents.

    Uses AgentHooks to capture agent-level events,
    ensuring user input and assistant output are properly recorded.
    """

    def __init__(self):
        super().__init__()
        print("🔧 ContextHooks initialized")

    async def on_start(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext]
    ) -> None:
        """Called when agent execution starts."""
        pass

    async def on_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            output: Any
    ) -> None:
        """Called when agent execution ends."""
        pass

    async def on_tool_start(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool
    ) -> None:
        """Called when tool execution starts."""
        pass

    async def on_tool_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool,
            result: str
    ) -> None:
        """Called when tool execution ends."""
        pass


class ContextTracingProcessor(TracingProcessor):
    """Tracing processor for code agent context."""

    def __init__(self, context: CodeAgentContext):
        self.context = context

    def on_trace_start(self, trace: "Trace") -> None:
        """Called when trace starts."""
        pass

    def on_span_start(self, span: "Span[Any]") -> None:
        """Called when span starts."""
        pass

    def on_span_end(self, span: "Span[Any]") -> None:
        """Called when span ends."""
        pass

    def on_trace_end(self, trace: "Trace") -> None:
        """Called when trace ends."""
        pass

    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass

    def force_flush(self) -> None:
        """Force flush any pending data."""
        pass