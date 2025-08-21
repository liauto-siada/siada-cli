from agents import Agent, RunContextWrapper, RunHooks, TContext, Tool


class CheckpointingProcessor(RunHooks):

    """
    Processor for handling checkpointing during agent execution.
    
    This processor saves checkpoints after tool executions to allow resuming
    from the last checkpoint in case of interruptions.
    """

    async def on_tool_end(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent,
        tool: Tool,
        result: str,
    ) -> None:
        """Called immediately after a tool execution completes."""
        # Initialize checkpoint tracker with context workspace and session ID
        # Save checkpoint using the current API
        context.context.save_checkpoints()
    