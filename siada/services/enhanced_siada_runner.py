"""
Enhanced Siada Runner with Agent Lifecycle Management
Integrates agent lifecycle tracking with existing SiadaRunner
"""

import asyncio
import time
from typing import Optional, Literal, overload, List
from datetime import datetime

from agents import RunResult, RunResultStreaming, TResponseInputItem

from siada.services.siada_runner import SiadaRunner
from siada.session.session_models import RunningSession
from siada.foundation.logging import logger as logging

# Import lifecycle management components
from siada.services.agent_lifecycle_manager import get_lifecycle_manager
from siada.models.agent_lifecycle import AgentError, MessageEventType


class EnhancedSiadaRunner(SiadaRunner):
    """
    Enhanced runner that integrates agent lifecycle management
    with the existing SiadaRunner infrastructure.
    
    Features:
    - Automatic lifecycle tracking for all agent runs
    - Message streaming with state tracking
    - Error handling with lifecycle events
    - Slash command integration
    - Event emission for UI updates
    """
    
    def __init__(self):
        super().__init__()
        self.lifecycle_manager = get_lifecycle_manager()
        self._current_run_id = None
        self._current_message_id = None
        
        # Register event handler for logging
        self.lifecycle_manager.register_event_handler(self._log_lifecycle_event)
    
    def _log_lifecycle_event(self, event):
        """Log lifecycle events for debugging"""
        logging.debug(
            f"[Lifecycle] {event.type.value} - Run: {event.run_id[:16]}..."
        )
    
    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[True],
    ) -> RunResultStreaming: ...

    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[False],
    ) -> RunResult: ...

    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        stream: bool = False,
    ) -> RunResult | RunResultStreaming:
        """
        Enhanced run_agent with lifecycle tracking.
        
        This method wraps the original SiadaRunner.run_agent with:
        - Agent run lifecycle tracking
        - Message state management
        - Error handling with lifecycle events
        - Event emission for UI/monitoring
        
        Args:
            agent_name: Name of the Agent
            user_input: User input (string or message list)
            workspace: Workspace path, optional
            session: Running session object, optional
            stream: Whether to enable streaming output
            
        Returns:
            RunResult or RunResultStreaming based on stream parameter
        """
        # Get lifecycle manager
        lifecycle_manager = get_lifecycle_manager()
        
        # Extract session ID for tracking
        session_id = session.session_id if session else None
        
        # Create run in lifecycle manager
        run = lifecycle_manager.create_run(
            agent_name=agent_name,
            session_id=session_id
        )
        
        logging.info(
            f"[EnhancedRunner] Created lifecycle run {run.run_id[:16]}... "
            f"for agent '{agent_name}'"
        )
        
        try:
            # Start the run
            lifecycle_manager.start_run(run.run_id)
            
            # Create message for output tracking
            message = lifecycle_manager.create_message(run.run_id, role="agent")
            
            # Execute the original run_agent
            logging.info(
                f"[EnhancedRunner] Executing agent (stream={stream})"
            )
            start_time = time.time()
            
            if stream:
                # Streaming execution with message part tracking
                result = await SiadaRunner.run_agent(
                    agent_name=agent_name,
                    user_input=user_input,
                    workspace=workspace,
                    session=session,
                    stream=True
                )
                
                # Wrap the streaming result to track message parts
                async def wrapped_stream():
                    """Wrap stream to emit message parts"""
                    try:
                        async for chunk in result:
                            # Track message part
                            if hasattr(chunk, 'content') and chunk.content:
                                lifecycle_manager.add_message_part(
                                    run.run_id,
                                    message.id,
                                    str(chunk.content)
                                )
                            yield chunk
                        
                        # Complete message after streaming
                        lifecycle_manager.complete_message(run.run_id, message.id)
                        
                    except Exception as e:
                        # Handle streaming error
                        logging.error(f"[EnhancedRunner] Streaming error: {e}")
                        error = AgentError(
                            code="STREAM_ERROR",
                            message=str(e)
                        )
                        lifecycle_manager.fail_run(run.run_id, error)
                        raise
                
                # Return wrapped streaming result
                return wrapped_stream()
                
            else:
                # Normal execution
                result = await SiadaRunner.run_agent(
                    agent_name=agent_name,
                    user_input=user_input,
                    workspace=workspace,
                    session=session,
                    stream=False
                )
                
                # Track message content
                if hasattr(result, 'messages') and result.messages:
                    for msg in result.messages:
                        if hasattr(msg, 'content'):
                            lifecycle_manager.add_message_part(
                                run.run_id,
                                message.id,
                                str(msg.content)
                            )
                
                # Complete message
                lifecycle_manager.complete_message(run.run_id, message.id)
                
                elapsed = time.time() - start_time
                logging.info(
                    f"[EnhancedRunner] Agent execution completed "
                    f"(took {elapsed:.2f}s)"
                )
                
                # Complete the run
                lifecycle_manager.complete_run(run.run_id)
                
                return result
                
        except Exception as e:
            # Handle execution error
            logging.error(
                f"[EnhancedRunner] Agent execution failed: {e}",
                exc_info=True
            )
            
            # Create error object
            error = AgentError(
                code="EXECUTION_ERROR",
                message=str(e),
                details={
                    'agent_name': agent_name,
                    'session_id': session_id,
                    'stream': stream
                }
            )
            
            # Fail the run
            lifecycle_manager.fail_run(run.run_id, error)
            
            # Re-raise the exception
            raise
    
    @staticmethod
    async def handle_slash_command(
        command: str,
        args: str,
        session: RunningSession
    ) -> dict:
        """
        Handle slash commands with lifecycle tracking.
        
        Args:
            command: The slash command (without /)
            args: Command arguments
            session: Running session
            
        Returns:
            dict: Command execution result
        """
        lifecycle_manager = get_lifecycle_manager()
        
        # Create a run for the command
        run = lifecycle_manager.create_run(
            agent_name=f"command_{command}",
            session_id=session.session_id if session else None
        )
        
        logging.info(f"[EnhancedRunner] Executing slash command: /{command}")
        
        try:
            # Start the run
            lifecycle_manager.start_run(run.run_id)
            
            # Execute the command (integrate with existing slash_commands)
            from siada.support.slash_commands import SlashCommands
            
            # Get slash commands handler from session
            if hasattr(session, 'slash_commands'):
                result = session.slash_commands.run(session, f"/{command} {args}")
            else:
                result = {"status": "error", "message": "Slash commands not available"}
            
            # Complete the run
            lifecycle_manager.complete_run(run.run_id)
            
            logging.info(f"[EnhancedRunner] Slash command completed: /{command}")
            
            return result
            
        except Exception as e:
            # Handle command error
            logging.error(f"[EnhancedRunner] Slash command failed: {e}")
            
            error = AgentError(
                code="COMMAND_ERROR",
                message=str(e),
                details={'command': command, 'args': args}
            )
            
            lifecycle_manager.fail_run(run.run_id, error)
            
            return {
                "status": "error",
                "message": str(e),
                "command": command
            }


# Convenience functions for backward compatibility
async def run_agent_with_lifecycle(
    agent_name: str,
    user_input: str | list[TResponseInputItem],
    workspace: str = None,
    session: RunningSession = None,
    stream: bool = False,
) -> RunResult | RunResultStreaming:
    """
    Convenience function to run agent with lifecycle tracking.
    
    This is a drop-in replacement for SiadaRunner.run_agent that adds
    lifecycle management capabilities.
    """
    return await EnhancedSiadaRunner.run_agent(
        agent_name=agent_name,
        user_input=user_input,
        workspace=workspace,
        session=session,
        stream=stream
    )


def get_current_run_statistics() -> dict:
    """
    Get current run statistics from lifecycle manager.
    
    Returns:
        dict: Statistics including total runs, active runs, etc.
    """
    lifecycle_manager = get_lifecycle_manager()
    return lifecycle_manager.get_run_statistics()


def get_active_runs() -> List:
    """
    Get list of currently active runs.
    
    Returns:
        List: List of active AgentRun objects
    """
    lifecycle_manager = get_lifecycle_manager()
    return lifecycle_manager.get_active_runs()
