from typing import Optional, List, Any
from agents import Agent, ModelResponse, AgentHooks, TContext, TResponseInputItem, RunContextWrapper, Tool
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.hooks.agent_processors.context_track_processor import ContextTrackProcessor


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

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """Called when an agent starts execution."""
        
        # Delegate to all processors
        for processor in self.processors:
            await processor.on_agent_start(context, agent)

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        """Called when an agent completes execution."""
        
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