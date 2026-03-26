"""
Message State Tracker
Enhanced message state tracking with lifecycle events
Based on ACP Event system design
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable
from enum import Enum

from siada.models.agent_lifecycle import (
    AgentMessage,
    MessagePart,
    MessageEventType,
    AgentEvent
)


class MessageState(str, Enum):
    """Message state during lifecycle"""
    CREATING = "creating"  # Message is being created
    STREAMING = "streaming"  # Message parts are being streamed
    COMPLETED = "completed"  # Message is complete
    FAILED = "failed"  # Message creation failed


@dataclass
class TrackedMessage:
    """
    Tracked message with state information
    """
    message: AgentMessage
    state: MessageState = MessageState.CREATING
    part_count: int = 0
    total_content_length: int = 0
    error: Optional[str] = None
    events: List[AgentEvent] = field(default_factory=list)

    def add_part(self, part: MessagePart) -> None:
        """Add a part and update tracking"""
        self.part_count += 1
        self.total_content_length += len(part.content)
        if self.state == MessageState.CREATING:
            self.state = MessageState.STREAMING

    def complete(self) -> None:
        """Mark as completed"""
        self.state = MessageState.COMPLETED

    def fail(self, error: str) -> None:
        """Mark as failed"""
        self.state = MessageState.FAILED
        self.error = error

    @property
    def is_active(self) -> bool:
        """Check if message is actively being created"""
        return self.state in {MessageState.CREATING, MessageState.STREAMING}

    @property
    def is_terminal(self) -> bool:
        """Check if message is in terminal state"""
        return self.state in {MessageState.COMPLETED, MessageState.FAILED}


@dataclass
class MessageStateTracker:
    """
    Tracks message states and lifecycle events
    Enhanced version of TaskMessageState with event tracking
    """
    session_id: str = ""
    run_id: str = ""
    
    # Tracked messages by ID
    _messages: Dict[str, TrackedMessage] = field(default_factory=dict)
    
    # Event history
    _events: List[AgentEvent] = field(default_factory=list)
    
    # Event handlers
    _event_handlers: List[Callable[[AgentEvent], None]] = field(default_factory=list)

    def register_event_handler(self, handler: Callable[[AgentEvent], None]) -> None:
        """Register an event handler"""
        self._event_handlers.append(handler)

    def unregister_event_handler(self, handler: Callable[[AgentEvent], None]) -> None:
        """Unregister an event handler"""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def _emit_event(self, event: AgentEvent) -> None:
        """Emit an event to handlers and store in history"""
        self._events.append(event)
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                # Log but don't fail on handler errors
                import logging
                logging.error(f"Error in event handler: {e}", exc_info=True)

    def create_message(self, message: AgentMessage) -> TrackedMessage:
        """Create and track a new message"""
        tracked = TrackedMessage(message=message)
        self._messages[message.id] = tracked

        # Emit message created event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_CREATED,
            run_id=self.run_id,
            message=message
        )
        tracked.events.append(event)
        self._emit_event(event)

        return tracked

    def add_message_part(
        self,
        message_id: str,
        content: str,
        content_type: str = "text/plain"
    ) -> MessagePart:
        """Add a part to a tracked message"""
        tracked = self._messages.get(message_id)
        if not tracked:
            raise ValueError(f"Message {message_id} not tracked")

        # Add part to message
        part = tracked.message.add_part(content, content_type)
        tracked.add_part(part)

        # Emit message part event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_PART,
            run_id=self.run_id,
            message=tracked.message,
            message_part=part
        )
        tracked.events.append(event)
        self._emit_event(event)

        return part

    def complete_message(self, message_id: str) -> None:
        """Complete a tracked message"""
        tracked = self._messages.get(message_id)
        if not tracked:
            raise ValueError(f"Message {message_id} not tracked")

        tracked.message.complete()
        tracked.complete()

        # Emit message completed event
        event = AgentEvent(
            type=MessageEventType.MESSAGE_COMPLETED,
            run_id=self.run_id,
            message=tracked.message
        )
        tracked.events.append(event)
        self._emit_event(event)

    def fail_message(self, message_id: str, error: str) -> None:
        """Mark a message as failed"""
        tracked = self._messages.get(message_id)
        if not tracked:
            raise ValueError(f"Message {message_id} not tracked")

        tracked.fail(error)

        # Emit error event
        from siada.models.agent_lifecycle import AgentError
        agent_error = AgentError(code="MESSAGE_FAILED", message=error)
        event = AgentEvent(
            type=MessageEventType.ERROR,
            run_id=self.run_id,
            message=tracked.message,
            error=agent_error
        )
        tracked.events.append(event)
        self._emit_event(event)

    def get_message(self, message_id: str) -> Optional[TrackedMessage]:
        """Get a tracked message"""
        return self._messages.get(message_id)

    def get_all_messages(self) -> List[TrackedMessage]:
        """Get all tracked messages"""
        return list(self._messages.values())

    def get_active_messages(self) -> List[TrackedMessage]:
        """Get all active messages"""
        return [msg for msg in self._messages.values() if msg.is_active]

    def get_completed_messages(self) -> List[TrackedMessage]:
        """Get all completed messages"""
        return [
            msg for msg in self._messages.values()
            if msg.state == MessageState.COMPLETED
        ]

    def get_events(
        self,
        event_type: Optional[MessageEventType] = None,
        since: Optional[datetime] = None
    ) -> List[AgentEvent]:
        """
        Get events with optional filtering
        
        Args:
            event_type: Filter by event type
            since: Only return events after this timestamp
        """
        events = self._events

        if event_type:
            events = [e for e in events if e.type == event_type]

        if since:
            events = [e for e in events if e.timestamp > since]

        return events

    def get_message_events(self, message_id: str) -> List[AgentEvent]:
        """Get all events for a specific message"""
        tracked = self._messages.get(message_id)
        if not tracked:
            return []
        return tracked.events

    def get_statistics(self) -> Dict:
        """Get tracking statistics"""
        total_messages = len(self._messages)
        total_parts = sum(msg.part_count for msg in self._messages.values())
        total_content = sum(msg.total_content_length for msg in self._messages.values())

        by_state = {}
        for state in MessageState:
            count = sum(1 for msg in self._messages.values() if msg.state == state)
            by_state[state.value] = count

        by_event_type = {}
        for event_type in MessageEventType:
            count = sum(1 for event in self._events if event.type == event_type)
            by_event_type[event_type.value] = count

        return {
            'total_messages': total_messages,
            'total_parts': total_parts,
            'total_content_length': total_content,
            'by_state': by_state,
            'by_event_type': by_event_type,
            'total_events': len(self._events)
        }

    def clear(self) -> None:
        """Clear all tracked data"""
        self._messages.clear()
        self._events.clear()

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'session_id': self.session_id,
            'run_id': self.run_id,
            'messages': [
                {
                    'id': tracked.message.id,
                    'state': tracked.state.value,
                    'part_count': tracked.part_count,
                    'total_content_length': tracked.total_content_length,
                    'content': tracked.message.content,
                    'created_at': tracked.message.created_at.isoformat(),
                    'completed_at': tracked.message.completed_at.isoformat() 
                        if tracked.message.completed_at else None,
                    'error': tracked.error
                }
                for tracked in self._messages.values()
            ],
            'events': [event.to_dict() for event in self._events],
            'statistics': self.get_statistics()
        }
