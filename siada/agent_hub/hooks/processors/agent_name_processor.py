"""
Agent Name Processor

Scopes the `AGENT_NAME` context variable to the duration of a single LLM call,
so the value tagged on the outgoing `X-Siada-Event-Type` header always matches
the agent that actually initiated the request.

Without this processor, `AGENT_NAME` set by a parent agent (e.g. the top-level
coder agent in `SiadaRunner.run_agent`) leaks into the coroutine / task that
runs *after* the agent returns, causing subsequent LLM calls — including calls
initiated by sibling or non-agent code paths on the same task — to be
mis-attributed.
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

from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.context import (
    AGENT_NAME,
    get_context_var,
    remove_context_var_inplace,
    set_context_var_inplace,
)


# Fallback tag used when the Agent does not expose a name. The server-side
# analytics pipeline treats this as "unknown agent".
_DEFAULT_AGENT_NAME = "UnknownAgent"


class AgentNameProcessor(AgentHooks):
    """
    Set AGENT_NAME on `on_llm_start` and restore the previous value on
    `on_llm_end`, effectively turning the LLM call into a scoped override.

    The previous value (or absence) is captured on a per-instance stack so
    nested agent invocations that share the same hook chain still unwind
    cleanly.
    """

    # Sentinel marking "key was absent before this call" so we can correctly
    # `remove_context_var` on exit rather than setting it to None.
    _MISSING: Any = object()

    def __init__(self, agent_name: Optional[str] = None) -> None:
        """
        Args:
            agent_name: Optional explicit name. When None (the default) the
                processor falls back to the Agent's `name` attribute at call
                time, which lets a single processor instance be reused across
                agents.
        """
        self._explicit_name = agent_name
        # Stack of previous values to support nested on_llm_start / on_llm_end
        # pairs on the same processor instance.
        self._previous_stack: list[Any] = []

    def _resolve_name(self, agent: "Agent[TContext]") -> str:
        if self._explicit_name:
            return self._explicit_name
        return getattr(agent, "name", None) or _DEFAULT_AGENT_NAME

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        # IMPORTANT: the agents SDK invokes on_llm_start / on_llm_end inside
        # `asyncio.gather(...)`, which runs each coroutine in a separate Task
        # with a COPY of the parent Context. A regular `ContextVar.set()`
        # performed here would therefore be invisible to the parent task that
        # subsequently builds the LLM request headers. We mutate the shared
        # context dict in place so the write propagates back through the
        # shared dict reference (see set_context_var_inplace docstring).
        previous = get_context_var(AGENT_NAME, self._MISSING)
        self._previous_stack.append(previous)
        set_context_var_inplace(AGENT_NAME, self._resolve_name(agent))

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        # Symmetric to on_llm_start: restore the previous value in place so
        # the parent task sees the unwind as well.
        if not self._previous_stack:
            # Defensive: on_llm_end invoked without a matching on_llm_start.
            # Just clear the key so nothing leaks.
            remove_context_var_inplace(AGENT_NAME)
            return
        previous = self._previous_stack.pop()
        if previous is self._MISSING:
            remove_context_var_inplace(AGENT_NAME)
        else:
            set_context_var_inplace(AGENT_NAME, previous)

    # No-op lifecycle hooks — explicitly defined to satisfy AgentHooks interface
    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
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
