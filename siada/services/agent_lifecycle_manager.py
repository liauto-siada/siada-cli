"""
Agent Lifecycle Manager
Manages agent execution lifecycle and state transitions
Based on ACP Executor design patterns
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional
from datetime import datetime

from siada.models.agent_lifecycle import (
    AgentRun,
    AgentRunStatus,
    AgentEvent,
    MessageEventType,
    AgentMessage,
    AgentError,
    MessagePart
)


logger = logging.getLogger(__name__)


class AgentLifecycleManager:
    """
    Manages agent run lifecycle and emits events
    Similar to ACP Executor pattern
    """

    def __init__(self):
        self.runs: Dict[str, AgentRun] = {}
        self.event_handlers: List[Callable[[AgentEvent], None]] = []
        self._active_runs: Dict[str, asyncio.Task] = {}

    def register_event_handler(self, handler: Callable[[AgentEvent], None]) -> None:
        """Register an event handler for lifecycle events"""
        self.event_handlers.append(handler)

    def unregister_event_handler(self, handler: Callable[[AgentEvent], None]) -> None:
        """Unregister an event handler"""
        if handler in self.event_handlers:
            self.event_handlers.remove(handler)

    def _emit_event(self, event: AgentEvent) -> None:
        """Emit an event to all registered handlers"""
        for handler in self.event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}", exc_info=True)

    def create_run(
        self,
        agent_name: str,
        session_id: Optional[str] = None,
        input_messages: Optional[List[AgentMessage]] = None,
        metadata: Optional[Dict] = None
    ) -> AgentRun:
        """Create a new agent run"""
        run = AgentRun(
            agent_name=agent_name,
            session_id=session_id,
            input_messages=input_messages or [],
            metadata=metadata or {}
        )
        self.runs[run.run_id] = run

        # Emit run created event
        event = AgentEvent(
            type=MessageEventType.RUN_CREATED,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        logger.info(f"Created run {run.run_id} for agent {agent_name}")
        return run

    def start_run(self, run_id: str) -> None:
        """Start a run"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.start()

        # Emit run in-progress event
        event = AgentEvent(
            type=MessageEventType.RUN_IN_PROGRESS,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        logger.info(f"Started run {run_id}")

    def create_message(self, run_id: str, role: str = "agent") -> AgentMessage:
        """Create a new message for streaming output"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        message = AgentMessage(role=role)
        run.output_messages.append(message)

        # Emit message created event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_CREATED,
            run_id=run.run_id,
            message=message
        )
        self._emit_event(event)

        logger.debug(f"Created message {message.id} for run {run_id}")
        return message

    def add_message_part(
        self,
        run_id: str,
        message_id: str,
        content: str,
        content_type: str = "text/plain"
    ) -> MessagePart:
        """Add a part to a streaming message"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Find the message
        message = None
        for msg in run.output_messages:
            if msg.id == message_id:
                message = msg
                break

        if not message:
            raise ValueError(f"Message {message_id} not found in run {run_id}")

        part = message.add_part(content, content_type)

        # Emit message part event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_PART,
            run_id=run.run_id,
            message=message,
            message_part=part
        )
        self._emit_event(event)

        return part

    def complete_message(self, run_id: str, message_id: str) -> None:
        """Complete a message"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Find the message
        message = None
        for msg in run.output_messages:
            if msg.id == message_id:
                message = msg
                break

        if not message:
            raise ValueError(f"Message {message_id} not found in run {run_id}")

        message.complete()

        # Emit message completed event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_COMPLETED,
            run_id=run.run_id,
            message=message
        )
        self._emit_event(event)

        logger.debug(f"Completed message {message_id} for run {run_id}")

    def await_input(self, run_id: str) -> None:
        """Mark run as awaiting user input"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.await_input()

        # Emit run awaiting event
        event = AgentEvent(
            type=MessageEventType.RUN_AWAITING,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        logger.info(f"Run {run_id} awaiting user input")

    def resume_run(self, run_id: str) -> None:
        """Resume a run from awaiting state"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.resume()

        # Emit run in-progress event
        event = AgentEvent(
            type=MessageEventType.RUN_IN_PROGRESS,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        logger.info(f"Resumed run {run_id}")

    def complete_run(self, run_id: str) -> None:
        """Complete a run successfully"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.complete()

        # Emit run completed event
        event = AgentEvent(
            type=MessageEventType.RUN_COMPLETED,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        # Clean up active task if exists
        if run_id in self._active_runs:
            del self._active_runs[run_id]

        logger.info(f"Completed run {run_id} (duration: {run.duration}s)")

    def fail_run(self, run_id: str, error: AgentError) -> None:
        """Fail a run with an error"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.fail(error)

        # Emit run failed event
        event = AgentEvent(
            type=MessageEventType.RUN_FAILED,
            run_id=run.run_id,
            run=run,
            error=error
        )
        self._emit_event(event)

        # Clean up active task if exists
        if run_id in self._active_runs:
            del self._active_runs[run_id]

        logger.error(f"Run {run_id} failed: {error.message}")

    def cancel_run(self, run_id: str) -> None:
        """Cancel a run"""
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Cancel active task if exists
        if run_id in self._active_runs:
            task = self._active_runs[run_id]
            task.cancel()
            del self._active_runs[run_id]

        run.cancel()

        # Emit run cancelled event
        event = AgentEvent(
            type=MessageEventType.RUN_CANCELLED,
            run_id=run.run_id,
            run=run
        )
        self._emit_event(event)

        logger.info(f"Cancelled run {run_id}")

    def get_run(self, run_id: str) -> Optional[AgentRun]:
        """Get a run by ID"""
        return self.runs.get(run_id)

    def get_active_runs(self) -> List[AgentRun]:
        """Get all active runs"""
        return [run for run in self.runs.values() if run.status.is_active]

    def get_terminal_runs(self) -> List[AgentRun]:
        """Get all terminal runs"""
        return [run for run in self.runs.values() if run.status.is_terminal]

    def cleanup_old_runs(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up old terminal runs
        Returns the number of runs cleaned up
        """
        now = datetime.now()
        to_remove = []

        for run_id, run in self.runs.items():
            if run.status.is_terminal and run.finished_at:
                age = (now - run.finished_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(run_id)

        for run_id in to_remove:
            del self.runs[run_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old runs")

        return len(to_remove)

    def get_run_statistics(self) -> Dict:
        """Get statistics about runs"""
        stats = {
            'total': len(self.runs),
            'by_status': {},
            'active': 0,
            'terminal': 0
        }

        for run in self.runs.values():
            status = run.status.value
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            if run.status.is_active:
                stats['active'] += 1
            elif run.status.is_terminal:
                stats['terminal'] += 1

        return stats


# Global instance
_global_lifecycle_manager: Optional[AgentLifecycleManager] = None


def get_lifecycle_manager() -> AgentLifecycleManager:
    """Get or create the global lifecycle manager instance"""
    global _global_lifecycle_manager
    if _global_lifecycle_manager is None:
        _global_lifecycle_manager = AgentLifecycleManager()
    return _global_lifecycle_manager
