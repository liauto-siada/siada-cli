"""
Lifecycle Adapter
Handles integration of agent lifecycle management with various siada-agenthub scenarios:
- Slash commands
- Streaming messages
- Error handling
- Exception propagation
"""

import sys
import traceback
from typing import Optional, Any, Callable, AsyncIterator
from datetime import datetime

from siada.models.agent_lifecycle import (
    AgentError,
    MessageEventType,
    AgentRunStatus
)
from siada.services.agent_lifecycle_manager import get_lifecycle_manager
from siada.foundation.logging import logger as logging


class LifecycleAdapter:
    """
    Adapter for integrating agent lifecycle management with existing code.
    
    This adapter provides methods to:
    - Track slash command execution
    - Handle streaming output with lifecycle events
    - Capture and track errors
    - Emit events for UI updates
    """
    
    def __init__(self):
        self.lifecycle_manager = get_lifecycle_manager()
        self._active_runs = {}  # run_id -> context
    
    def track_slash_command(
        self,
        command: str,
        handler: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Track a slash command execution with lifecycle.
        
        Args:
            command: Command name (e.g., "help", "restore")
            handler: Command handler function
            *args, **kwargs: Arguments for handler
            
        Returns:
            Handler result
            
        Example:
            adapter = LifecycleAdapter()
            result = adapter.track_slash_command(
                "help",
                lambda: print("Help text"),
            )
        """
        # Create run for command
        run = self.lifecycle_manager.create_run(
            agent_name=f"cmd_{command}",
            session_id=kwargs.get('session_id')
        )
        
        self._active_runs[run.run_id] = {
            'type': 'command',
            'command': command
        }
        
        logging.info(f"[Lifecycle] Tracking slash command: /{command}")
        
        try:
            # Start run
            self.lifecycle_manager.start_run(run.run_id)
            
            # Execute handler
            result = handler(*args, **kwargs)
            
            # Complete run
            self.lifecycle_manager.complete_run(run.run_id)
            
            logging.info(f"[Lifecycle] Command completed: /{command}")
            
            return result
            
        except Exception as e:
            # Capture error
            error = AgentError(
                code="COMMAND_ERROR",
                message=str(e),
                details={
                    'command': command,
                    'traceback': traceback.format_exc()
                }
            )
            
            self.lifecycle_manager.fail_run(run.run_id, error)
            
            logging.error(
                f"[Lifecycle] Command failed: /{command} - {e}",
                exc_info=True
            )
            
            # Re-raise
            raise
        
        finally:
            # Cleanup
            self._active_runs.pop(run.run_id, None)
    
    async def track_async_slash_command(
        self,
        command: str,
        handler: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Track an async slash command execution.
        
        Args:
            command: Command name
            handler: Async command handler
            *args, **kwargs: Arguments for handler
            
        Returns:
            Handler result
        """
        run = self.lifecycle_manager.create_run(
            agent_name=f"cmd_{command}",
            session_id=kwargs.get('session_id')
        )
        
        self._active_runs[run.run_id] = {
            'type': 'async_command',
            'command': command
        }
        
        logging.info(f"[Lifecycle] Tracking async command: /{command}")
        
        try:
            self.lifecycle_manager.start_run(run.run_id)
            result = await handler(*args, **kwargs)
            self.lifecycle_manager.complete_run(run.run_id)
            return result
            
        except Exception as e:
            error = AgentError(
                code="ASYNC_COMMAND_ERROR",
                message=str(e),
                details={'command': command}
            )
            self.lifecycle_manager.fail_run(run.run_id, error)
            logging.error(f"[Lifecycle] Async command failed: /{command} - {e}")
            raise
        
        finally:
            self._active_runs.pop(run.run_id, None)
    
    async def wrap_streaming_output(
        self,
        stream: AsyncIterator,
        run_id: str,
        message_id: Optional[str] = None
    ) -> AsyncIterator:
        """
        Wrap a streaming output to emit lifecycle events.
        
        Args:
            stream: Async iterator of output chunks
            run_id: Run ID for tracking
            message_id: Optional message ID (creates new if None)
            
        Yields:
            Original stream chunks
            
        Example:
            async def my_stream():
                yield "Hello"
                yield " world"
            
            wrapped = adapter.wrap_streaming_output(
                my_stream(),
                run_id="run-123"
            )
            async for chunk in wrapped:
                print(chunk)
        """
        # Create message if not provided
        if not message_id:
            message = self.lifecycle_manager.create_message(run_id)
            message_id = message.id
        
        try:
            chunk_count = 0
            
            async for chunk in stream:
                chunk_count += 1
                
                # Extract content from chunk
                content = self._extract_chunk_content(chunk)
                
                if content:
                    # Emit message part event
                    self.lifecycle_manager.add_message_part(
                        run_id,
                        message_id,
                        content
                    )
                
                # Yield original chunk
                yield chunk
            
            # Complete message
            self.lifecycle_manager.complete_message(run_id, message_id)
            
            logging.debug(
                f"[Lifecycle] Completed streaming message "
                f"({chunk_count} chunks)"
            )
            
        except Exception as e:
            # Log streaming error but don't fail the run here
            # (let the caller decide)
            logging.error(
                f"[Lifecycle] Streaming error: {e}",
                exc_info=True
            )
            raise
    
    def _extract_chunk_content(self, chunk: Any) -> Optional[str]:
        """
        Extract content from various chunk types.
        
        Args:
            chunk: Output chunk (various formats)
            
        Returns:
            String content or None
        """
        # Handle different chunk formats
        if isinstance(chunk, str):
            return chunk
        
        if hasattr(chunk, 'content'):
            return str(chunk.content)
        
        if hasattr(chunk, 'text'):
            return str(chunk.text)
        
        if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'content'):
            return str(chunk.delta.content)
        
        if isinstance(chunk, dict):
            return chunk.get('content') or chunk.get('text')
        
        return None
    
    def capture_exception(
        self,
        run_id: str,
        exception: Exception,
        context: Optional[dict] = None
    ) -> AgentError:
        """
        Capture an exception and convert to AgentError.
        
        Args:
            run_id: Run ID for the failed run
            exception: The exception that occurred
            context: Optional context information
            
        Returns:
            AgentError object
            
        Example:
            try:
                # Some operation
                pass
            except Exception as e:
                error = adapter.capture_exception("run-123", e, {
                    'operation': 'file_read',
                    'file': 'test.py'
                })
                # Error is already tracked in lifecycle
        """
        # Get exception details
        exc_type = type(exception).__name__
        exc_message = str(exception)
        exc_traceback = traceback.format_exc()
        
        # Create error object
        error = AgentError(
            code=exc_type.upper(),
            message=exc_message,
            details={
                'type': exc_type,
                'traceback': exc_traceback,
                **(context or {})
            }
        )
        
        # Fail the run
        self.lifecycle_manager.fail_run(run_id, error)
        
        logging.error(
            f"[Lifecycle] Captured exception for run {run_id[:16]}...: "
            f"{exc_type}: {exc_message}"
        )
        
        return error
    
    def emit_custom_event(
        self,
        run_id: str,
        event_type: str,
        data: dict
    ):
        """
        Emit a custom event for a run.
        
        Args:
            run_id: Run ID
            event_type: Custom event type
            data: Event data
            
        Example:
            adapter.emit_custom_event(
                "run-123",
                "tool_execution",
                {"tool": "edit_file", "file": "test.py"}
            )
        """
        logging.info(
            f"[Lifecycle] Custom event '{event_type}' for run {run_id[:16]}..."
        )
        
        # You can extend this to emit custom events through the lifecycle manager
        # For now, just log it
    
    def get_run_context(self, run_id: str) -> Optional[dict]:
        """
        Get context for an active run.
        
        Args:
            run_id: Run ID
            
        Returns:
            Context dict or None
        """
        return self._active_runs.get(run_id)
    
    def cleanup_old_runs(self, max_age_seconds: int = 3600):
        """
        Clean up old terminal runs.
        
        Args:
            max_age_seconds: Maximum age for terminal runs
            
        Returns:
            Number of runs cleaned up
        """
        count = self.lifecycle_manager.cleanup_old_runs(max_age_seconds)
        
        if count > 0:
            logging.info(f"[Lifecycle] Cleaned up {count} old runs")
        
        return count


# Global adapter instance
_global_adapter: Optional[LifecycleAdapter] = None


def get_lifecycle_adapter() -> LifecycleAdapter:
    """
    Get or create the global lifecycle adapter instance.
    
    Returns:
        LifecycleAdapter: Global adapter instance
    """
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = LifecycleAdapter()
    return _global_adapter


# Decorator for automatic slash command tracking
def track_command(command_name: str):
    """
    Decorator to automatically track a slash command function.
    
    Args:
        command_name: Name of the command
        
    Example:
        @track_command("help")
        def cmd_help(session, args):
            return "Help text"
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            adapter = get_lifecycle_adapter()
            return adapter.track_slash_command(
                command_name,
                func,
                *args,
                **kwargs
            )
        
        # Preserve function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        
        return wrapper
    
    return decorator


def track_async_command(command_name: str):
    """
    Decorator to automatically track an async slash command function.
    
    Args:
        command_name: Name of the command
        
    Example:
        @track_async_command("restore")
        async def cmd_restore(session, args):
            # Async restore logic
            pass
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            adapter = get_lifecycle_adapter()
            return await adapter.track_async_slash_command(
                command_name,
                func,
                *args,
                **kwargs
            )
        
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        
        return wrapper
    
    return decorator
