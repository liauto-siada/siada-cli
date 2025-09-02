from agents import Agent, RunContextWrapper, RunHooks, TContext, Tool
from agents.tool_context import ToolContext
import re


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
        # add the function_call_out_to_the_task_message_state
        if isinstance(context, ToolContext):
            context.context.session.state.task_message_state.add_message(
                {
                    "call_id": context.tool_call_id,
                    "output": str(result),
                    "type": "function_call_output",
                }
            )
            context.context.save_checkpoints()
