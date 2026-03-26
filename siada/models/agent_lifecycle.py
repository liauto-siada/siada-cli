"""
Agent Lifecycle Models
Based on ACP (Agent Communication Protocol) design patterns
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class AgentRunStatus(str, Enum):
    """Agent run status based on ACP RunStatus"""
    CREATED = "created"
    IN_PROGRESS = "in-progress"
    AWAITING = "awaiting"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Check if status is terminal (no further transitions)"""
        terminal_states = {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED
        }
        return self in terminal_states

    @property
    def is_active(self) -> bool:
        """Check if agent is actively running"""
        return self in {AgentRunStatus.IN_PROGRESS, AgentRunStatus.AWAITING}


class MessageEventType(str, Enum):
    """Message event types based on ACP Event system"""
    MESSAGE_CREATED = "message.created"
    MESSAGE_PART = "message.part"
    MESSAGE_COMPLETED = "message.completed"
    RUN_CREATED = "run.created"
    RUN_IN_PROGRESS = "run.in-progress"
    RUN_AWAITING = "run.awaiting"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    RUN_COMPLETED = "run.completed"
    TOOL_CALL_STARTED = "toolCall.started"
    TOOL_CALL_COMPLETED = "toolCall.completed"
    TOOL_CALL_FAILED = "toolCall.failed"
    ERROR = "error"
    GENERIC = "generic"


@dataclass
class MessagePart:
    """Message part for streaming content"""
    content: str
    content_type: str = "text/plain"
    name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """Agent message with metadata"""
    id: str = field(default_factory=lambda: str(uuid4()))
    role: str = "agent"
    parts: List[MessagePart] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Check if message is complete"""
        return self.completed_at is not None

    @property
    def content(self) -> str:
        """Get full message content"""
        return "".join(part.content for part in self.parts)

    def add_part(self, content: str, content_type: str = "text/plain") -> MessagePart:
        """Add a message part"""
        part = MessagePart(content=content, content_type=content_type)
        self.parts.append(part)
        return part

    def complete(self) -> None:
        """Mark message as complete"""
        if not self.completed_at:
            self.completed_at = datetime.now()


@dataclass
class AgentError:
    """Agent error information"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentRun:
    """
    Agent run information based on ACP Run model
    Tracks the lifecycle of a single agent execution
    """
    run_id: str = field(default_factory=lambda: str(uuid4()))
    agent_name: str = ""
    session_id: Optional[str] = None
    status: AgentRunStatus = AgentRunStatus.CREATED
    input_messages: List[AgentMessage] = field(default_factory=list)
    output_messages: List[AgentMessage] = field(default_factory=list)
    error: Optional[AgentError] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark run as started"""
        if self.status == AgentRunStatus.CREATED:
            self.status = AgentRunStatus.IN_PROGRESS
            self.started_at = datetime.now()

    def await_input(self) -> None:
        """Mark run as awaiting user input"""
        if self.status == AgentRunStatus.IN_PROGRESS:
            self.status = AgentRunStatus.AWAITING

    def resume(self) -> None:
        """Resume from awaiting state"""
        if self.status == AgentRunStatus.AWAITING:
            self.status = AgentRunStatus.IN_PROGRESS

    def complete(self) -> None:
        """Mark run as completed"""
        if not self.status.is_terminal:
            self.status = AgentRunStatus.COMPLETED
            self.finished_at = datetime.now()

    def fail(self, error: AgentError) -> None:
        """Mark run as failed"""
        if not self.status.is_terminal:
            self.status = AgentRunStatus.FAILED
            self.error = error
            self.finished_at = datetime.now()

    def cancel(self) -> None:
        """Cancel the run"""
        if not self.status.is_terminal:
            self.status = AgentRunStatus.CANCELLED
            self.finished_at = datetime.now()

    @property
    def duration(self) -> Optional[float]:
        """Get run duration in seconds"""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'run_id': self.run_id,
            'agent_name': self.agent_name,
            'session_id': self.session_id,
            'status': self.status.value,
            'input_messages': [
                {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'created_at': msg.created_at.isoformat(),
                    'completed_at': msg.completed_at.isoformat() if msg.completed_at else None,
                    'metadata': msg.metadata
                }
                for msg in self.input_messages
            ],
            'output_messages': [
                {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'created_at': msg.created_at.isoformat(),
                    'completed_at': msg.completed_at.isoformat() if msg.completed_at else None,
                    'metadata': msg.metadata
                }
                for msg in self.output_messages
            ],
            'error': {
                'code': self.error.code,
                'message': self.error.message,
                'details': self.error.details,
                'timestamp': self.error.timestamp.isoformat()
            } if self.error else None,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'metadata': self.metadata
        }


@dataclass
class AgentEvent:
    """
    Agent event for lifecycle tracking
    Based on ACP Event system
    """
    type: MessageEventType
    run_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    message: Optional[AgentMessage] = None
    message_part: Optional[MessagePart] = None
    run: Optional[AgentRun] = None
    error: Optional[AgentError] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            'type': self.type.value,
            'run_id': self.run_id,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data
        }
        
        if self.message:
            result['message'] = {
                'id': self.message.id,
                'role': self.message.role,
                'content': self.message.content,
                'created_at': self.message.created_at.isoformat(),
                'completed_at': self.message.completed_at.isoformat() if self.message.completed_at else None,
                'metadata': self.message.metadata
            }
        
        if self.message_part:
            result['message_part'] = {
                'content': self.message_part.content,
                'content_type': self.message_part.content_type,
                'name': self.message_part.name,
                'timestamp': self.message_part.timestamp.isoformat(),
                'metadata': self.message_part.metadata
            }
        
        if self.run:
            result['run'] = self.run.to_dict()
        
        if self.error:
            result['error'] = {
                'code': self.error.code,
                'message': self.error.message,
                'details': self.error.details,
                'timestamp': self.error.timestamp.isoformat()
            }
        
        return result
