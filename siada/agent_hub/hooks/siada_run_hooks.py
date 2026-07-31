from typing import Optional, List, Any
from agents import Agent, ModelResponse, RunContextWrapper, RunHooks, TContext, TResponseInputItem, Tool
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger
from siada.agent_hub.hooks.agent_processors.context_track_processor import ContextTrackProcessor
from siada.agent_hub.hooks.processors.checkpointing_processor import CheckpointingProcessor


class SiadaRunHooks(RunHooks):
    """
    Common hooks class that combines multiple processors for agent execution.
    
    This class acts as a composite that delegates to multiple RunHooks processors,
    allowing for modular and extensible hook functionality.
    """
    
    def __init__(self, processors: Optional[List[RunHooks]] = None):
        """
        Initialize with a list of processors.
        
        Args:
            processors: List of RunHooks processors to use. If None, defaults to standard processors.
        """
        if processors is None:
            self.processors = [
                CheckpointingProcessor(),
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
        # Inject any pending additionalContext messages collected by hook guardrails.
        code_ctx = context.context
        if code_ctx is not None and code_ctx.hook_pending_contexts:
            for ctx_text in code_ctx.hook_pending_contexts:
                input_items.append({"role": "system", "content": ctx_text})
                logger.info(f"[SiadaRunHooks] additionalContext injected at index={len(input_items)-1}, total_items={len(input_items)}: {ctx_text[:120]}")
            code_ctx.hook_pending_contexts.clear()

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

    def add_processor(self, processor: RunHooks) -> None:
        """
        Add a new processor to the hooks.
        
        Args:
            processor: The RunHooks processor to add
        """
        self.processors.append(processor)

    def remove_processor(self, processor: RunHooks) -> None:
        """
        Remove a processor from the hooks.
        
        Args:
            processor: The RunHooks processor to remove
        """
        if processor in self.processors:
            self.processors.remove(processor)
