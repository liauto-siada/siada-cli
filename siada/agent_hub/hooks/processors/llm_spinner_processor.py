"""
LLM Spinner Processor

Provides visual feedback during LLM calls by displaying a waiting spinner.
"""

from typing import Optional
from agents import Agent, ModelResponse, AgentHooks, TContext, TResponseInputItem, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.support.spinner import WaitingSpinner


class LLMSpinnerProcessor(AgentHooks):
    """
    Processor that displays a waiting spinner during LLM calls.
    
    This processor:
    - Starts a spinner when LLM call begins (on_llm_start)
    - Stops the spinner when LLM call completes (on_llm_end)
    """
    
    def __init__(self, spinner_text: str = "Waiting for LLM...", text_color: str = "#79B8FF"):
        """
        Initialize the LLM spinner processor.
        
        Args:
            spinner_text: Text to display with the spinner
            text_color: Color of the spinner text (hex or color name)
        """
        self.spinner_text = spinner_text
        self.text_color = text_color
        self.spinner: Optional[WaitingSpinner] = None

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        """
        Called just before invoking the LLM.
        Starts the waiting spinner and injects it into session for external access.
        Only starts spinner in interactive mode.
        """
        # Only start spinner if we're in interactive mode
        if hasattr(context.context, 'session') and context.context.session and context.context.session.siada_config:
            running_config = getattr(context.context.session, 'siada_config', None)
            
            # Check if we're in interactive mode
            if not running_config or not getattr(running_config, 'interactive', True):
                # Non-interactive mode, skip spinner
                return
            
            # Get agent name for personalized message
            agent_name = getattr(context.context.session.siada_config, 'agent_name', 'Agent')
            spinner_text = f"Thinking ..."
            
            # Get IO instance to pass to spinner for panel status checking
            io_instance = getattr(running_config, 'io', None) if running_config else None
            
            # Create and start spinner with IO instance
            self.spinner = WaitingSpinner(spinner_text, text_color=self.text_color, io_instance=io_instance)
            self.spinner.start()
            
            # Inject spinner into session state for external access
            # This allows _stop_waiting_spinner() in conversation_turn.py to stop it
            # when the first stream data arrives
            context.context.session.state.spinner = self.spinner

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """
        Called immediately after the LLM call returns.
        Stops the waiting spinner with fallback cleanup.
        
        This method ensures spinner is stopped in all cases:
        1. Stops self.spinner (processor's own reference)
        2. Stops session.state.spinner (external reference used by conversation_turn)
        3. Stops session.spinner (legacy reference if exists)
        """
        # Stop processor's own spinner reference
        if self.spinner is not None:
            try:
                self.spinner.stop()
            except Exception:
                pass  # Ignore stop errors
            finally:
                self.spinner = None
        
        # Fallback: Also stop spinner in session.state (used by conversation_turn._stop_waiting_spinner)
        if hasattr(context.context, 'session') and context.context.session:
            session = context.context.session
            
            # Stop session.state.spinner
            if hasattr(session, 'state') and hasattr(session.state, 'spinner'):
                spinner = session.state.spinner
                if spinner:
                    try:
                        spinner.stop()
                    except Exception:
                        pass  # Ignore stop errors
                    finally:
                        session.state.spinner = None
            
            # Stop session.spinner (legacy reference)
            if hasattr(session, 'spinner') and session.spinner:
                try:
                    session.spinner.stop()
                except Exception:
                    pass  # Ignore stop errors
                finally:
                    session.spinner = None

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """Called when an agent starts execution."""
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: any,
    ) -> None:
        """Called when an agent completes execution."""
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: any,
    ) -> None:
        """Called before a tool is executed."""
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: any,
        result: str,
    ) -> None:
        """Called after a tool completes execution."""
        pass
