"""
SiadaBasicAgentHooks

A lightweight, extensible composite hook intended for agents that do **not**
need the full processor chain of `SiadaAgentHooks` (which bundles spinner,
token telemetry, context tracking, etc.), but still want the per-LLM-call
`AGENT_NAME` scoping that `AgentNameProcessor` provides — plus the ability to
plug in additional processors later without re-implementing the delegation
boilerplate.

Typical usage from a secondary / utility agent (e.g. MemoryAgent):

    from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks

    agent = Agent(
        name="MemoryAgent",
        ...,
        hooks=SiadaBasicAgentHooks(),           # AGENT_NAME scoping only
    )

    # Or extend with extra processors:
    agent = Agent(
        name="MemoryAgent",
        ...,
        hooks=SiadaBasicAgentHooks(extra_processors=[MyCustomProcessor()]),
    )

The class deliberately mirrors the `SiadaAgentHooks` composite shape so the two
can be used interchangeably — callers just pick the default processor set that
fits their agent's lifecycle needs.
"""

from typing import Any, List, Optional

from agents import (
    Agent,
    AgentHooks,
    ModelResponse,
    RunContextWrapper,
    TContext,
    TResponseInputItem,
    Tool,
)

from siada.agent_hub.hooks.processors.agent_name_processor import AgentNameProcessor
from siada.foundation.code_agent_context import CodeAgentContext


class SiadaBasicAgentHooks(AgentHooks):
    """
    Minimal composite AgentHooks — delegates every lifecycle event to an
    ordered list of processors (which are themselves `AgentHooks`).

    Default processor chain:
        [AgentNameProcessor()]

    Behaviors:
      - Pass `processors=...` to fully replace the default chain.
      - Pass `extra_processors=...` to append additional processors after the
        defaults (the common case when you just want to add one more hook).

    Both kwargs are optional; the class is safe to instantiate with no
    arguments and will still correctly scope `AGENT_NAME` per LLM call
    using the Agent's own `.name`.
    """

    def __init__(
        self,
        processors: Optional[List[AgentHooks]] = None,
        *,
        extra_processors: Optional[List[AgentHooks]] = None,
    ) -> None:
        if processors is not None:
            # Explicit override — caller takes full responsibility for the
            # processor chain (and must include AgentNameProcessor themselves
            # if they want AGENT_NAME scoping).
            self.processors: List[AgentHooks] = list(processors)
        else:
            # Default: scope AGENT_NAME for every LLM call so the outgoing
            # X-Siada-Event-Type header always reflects the agent that
            # actually issued the request, and the override is cleared on
            # on_llm_end to prevent leakage into unrelated follow-up work
            # running on the same asyncio task. AgentNameProcessor reads the
            # name from the Agent passed to on_llm_start, so no explicit
            # name needs to be threaded through this composite.
            self.processors = [AgentNameProcessor()]
            if extra_processors:
                self.processors.extend(extra_processors)

    # ------------------------------------------------------------------ #
    # Mutator helpers — mirror SiadaAgentHooks' public surface so the two
    # composites are drop-in compatible.
    # ------------------------------------------------------------------ #

    def add_processor(self, processor: AgentHooks) -> None:
        """Append a processor to the chain."""
        self.processors.append(processor)

    def remove_processor(self, processor: AgentHooks) -> None:
        """Remove a processor from the chain (no-op if not present)."""
        if processor in self.processors:
            self.processors.remove(processor)

    # ------------------------------------------------------------------ #
    # AgentHooks lifecycle — delegate to every processor in order.
    # ------------------------------------------------------------------ #

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        for processor in self.processors:
            await processor.on_llm_start(context, agent, system_prompt, input_items)

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        # Unwind in reverse so the lifecycle is symmetrical: processors that
        # set state on on_llm_start get to clean up before processors that ran
        # earlier in the chain. This matters for stacked context-var scopes.
        for processor in reversed(self.processors):
            await processor.on_llm_end(context, agent, response)

    async def on_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        # `AgentHooksBase` names this lifecycle method `on_start` (not
        # `on_agent_start`, which is the `RunHooksBase` naming) — overriding
        # the wrong name means the SDK silently never calls it.
        for processor in self.processors:
            await processor.on_agent_start(context, agent)

    async def on_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        for processor in reversed(self.processors):
            await processor.on_agent_end(context, agent, output)

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        for processor in self.processors:
            await processor.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        for processor in reversed(self.processors):
            await processor.on_tool_end(context, agent, tool, result)
