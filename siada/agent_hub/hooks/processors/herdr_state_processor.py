"""Mirror agent turn state into the hosting Herdr pane.

Herdr needs to know whether a pane's agent is working, waiting for input, or
idle. Screen scraping cannot see that for Siada, so the state is reported
directly: an agent run in flight is ``working`` and the moment it returns is
``idle``.

The processor is registered in :class:`SiadaAgentHooks`, which every
top-level agent uses on both runtime paths (the ACP server and the TUI
backend), so one registration covers both. Sub-agents run with
``SiadaBasicAgentHooks`` and are intentionally not wired: their start/end
happens inside the parent's turn, and reporting from them would flip the pane
back to ``idle`` while the parent agent is still working.
"""

from typing import Any, Optional

from agents import (
    Agent,
    AgentHooks,
    ModelResponse,
    RunContextWrapper,
    TContext,
    TResponseInputItem,
    Tool,
)

from siada.foundation import herdr_reporter
from siada.foundation.code_agent_context import CodeAgentContext


def _session_id(context: RunContextWrapper[CodeAgentContext]) -> Optional[str]:
    """Read the session id off the run context, tolerating a missing session."""
    try:
        return getattr(context.context, "session_id", None)
    except Exception:
        return None


class HerdrStateProcessor(AgentHooks):
    """Report `working` for the duration of an agent run and `idle` after it."""

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        herdr_reporter.report_state(
            herdr_reporter.STATE_WORKING, session_id=_session_id(context)
        )

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        herdr_reporter.report_state(
            herdr_reporter.STATE_IDLE, session_id=_session_id(context)
        )

    # No-op lifecycle hooks — explicitly defined to satisfy AgentHooks.
    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        pass

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        pass
