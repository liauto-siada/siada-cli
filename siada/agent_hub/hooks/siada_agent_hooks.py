from typing import Optional, List, Any
from agents import Agent, ModelResponse, AgentHooks, TContext, TResponseInputItem, RunContextWrapper, Tool
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.hooks.agent_processors.context_track_processor import ContextTrackProcessor
from siada.agent_hub.hooks.processors.agent_name_processor import AgentNameProcessor
from siada.agent_hub.hooks.processors.llm_spinner_processor import LLMSpinnerProcessor
from siada.agent_hub.hooks.processors.token_usage_reporter_processor import TokenUsageReporterProcessor
from siada.agent_hub.hooks.processors.cache_status_processor import CacheStatusProcessor
from siada.agent_hub.hooks.processors.todo_reminder_processor import TodoReminderProcessor



class SiadaAgentHooks(AgentHooks):
    """
    Common hooks class that combines multiple processors for agent execution.
    
    This class acts as a composite that delegates to multiple AgentHooks processors,
    allowing for modular and extensible hook functionality.
    """
    
    def __init__(self, processors: Optional[List[AgentHooks]] = None):
        """
        Initialize with a list of processors.
        
        Args:
            processors: List of AgentHooks processors to use. If None, defaults to standard processors.
        """
        if processors is None:
            # Default processors
            self.processors = [
                ContextTrackProcessor(),
                LLMSpinnerProcessor(),  # Add spinner for LLM calls
                TokenUsageReporterProcessor(),  # Report token usage to telemetry
                CacheStatusProcessor(),  # Send cache hit-rate + cost data to frontend
                # Scope AGENT_NAME to each LLM call so server-side analytics
                # always see the agent that actually issued the request, and
                # the value never leaks to unrelated code running on the same
                # asyncio task after the agent returns.
                AgentNameProcessor(),
                # Nudge models prone to looping on an unchanged tool call
                # (currently only kivy-deepseek-v4-flash) to change course.
                ModelHallucinationSuppressionProcessor(),
                # Injects the hidden todo reminder into the real per-call
                # input on_llm_start, then persists it into
                # the real Session on_llm_end right after that call succeeds,
                # so it's both part of the live call and survives in
                # api_history.json for future turns / session resume.
                TodoReminderProcessor(),
                # Add more processors here as needed
            ]

        else:
            self.processors = processors

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called just before invoking the LLM for this agent."""
        
        # Delegate to all processors
        for processor in self.processors:
            await processor.on_llm_start(context, agent, system_prompt, input_items)

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Called immediately after the LLM call returns for this agent."""
        
        # Delegate to all processors
        for processor in self.processors:
            await processor.on_llm_end(context, agent, response)

    async def on_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """Called when an agent starts execution.

        Note: `AgentHooksBase` (the base class for `agent.hooks`) defines this
        lifecycle method as `on_start`, not `on_agent_start` (the latter is the
        `RunHooksBase` naming used for `Runner.run(hooks=...)`). Overriding the
        wrong name means the SDK silently never calls it.
        """

        # Delegate to all processors
        for processor in self.processors:
            await processor.on_agent_start(context, agent)

    async def on_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        """Called when an agent completes execution.

        See note on `on_start` regarding the `on_end` vs `on_agent_end` naming.
        """

        # Delegate to all processors
        for processor in self.processors:
            await processor.on_agent_end(context, agent, output)

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        """Called before a tool is executed."""
        
        # Delegate to all processors
        for processor in self.processors:
            await processor.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        """Called after a tool completes execution."""
        
        # Delegate to all processors
        for processor in self.processors:
            await processor.on_tool_end(context, agent, tool, result)

    def add_processor(self, processor: AgentHooks) -> None:
        """
        Add a new processor to the hooks.
        
        Args:
            processor: The AgentHooks processor to add
        """
        self.processors.append(processor)

    def remove_processor(self, processor: AgentHooks) -> None:
        """
        Remove a processor from the hooks.
        
        Args:
            processor: The AgentHooks processor to remove
        """
        if processor in self.processors:
            self.processors.remove(processor)
