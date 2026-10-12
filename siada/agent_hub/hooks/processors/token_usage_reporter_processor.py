"""
Token Usage Reporter Processor

Hook-chain extension point for per-LLM-call token accounting.

This build reports usage nowhere: the provider endpoint the user configured
owns its own accounting, and the cache hit-rate / cost figures shown in the UI
are derived locally by ``CacheStatusProcessor``. The processor stays in the
hook chain to document that extension point and overrides nothing but the
lifecycle callbacks the composite hook expects.

``SiadaAgentHooks`` delegates ``on_agent_start`` / ``on_agent_end`` to every
processor, and ``agents.AgentHooks`` does not define those two names, so they
are declared here as explicit no-ops.
"""

from typing import Any

from agents import Agent, AgentHooks, RunContextWrapper, TContext

from siada.foundation.code_agent_context import CodeAgentContext


class TokenUsageReporterProcessor(AgentHooks):
    """Inert processor; see the module docstring for why nothing is reported."""

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """No-op — kept because the composite hook always delegates it."""

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        """No-op — kept because the composite hook always delegates it."""
