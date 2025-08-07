from agents import Agent, ModelResponse, AgentHooks, TContext, TResponseInputItem, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext


class ContextTrackProcessor(AgentHooks):
    """
    Processor for tracking message history during agent execution.
    
    This processor manages the message history in the task_message_state,
    resetting it before LLM calls and adding new messages after responses.
    """

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Called immediately after the LLM call returns for this agent."""
        
        # Add response messages to the message history
        input_items = response.to_input_items()
        siada_context = context.context
        siada_context.session.state.task_message_state.add_messages(
           messages=input_items
       )