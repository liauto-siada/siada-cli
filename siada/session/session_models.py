from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from uuid import uuid4

from siada.services.file_session import FileSession

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.session.task_message_state import TaskMessageState
from siada.support.checkpoint_tracker import CheckPointTracker


@dataclass
class SessionState:
    """
    Interaction session state data model
    
    Stores state information during user interactions, complementing FileSession:
    - FileSession: Stores large language model conversation history in JSON files
    - SessionState: Stores interaction state and context information
    """

    # Core state fields
    context_vars: Dict[str, Any] = field(default_factory=dict)
    """Context variables, works with foundation.context module"""

    # Agent-related state
    current_agent: Optional[str] = None
    """Currently active Agent name"""
    
    openai_session: Optional[FileSession] = None
    
    # Task message state
    task_message_state: TaskMessageState = field(default_factory=TaskMessageState)
    """Task message state for managing conversation history"""
    
    async def sync_messages_from_openai_session(self, limit: Optional[int] = None) -> None:
        """
        Sync messages from openai_session to task_message_state.
        
        Args:
            limit: Maximum number of messages to sync. If None, syncs all messages.
        """
        if self.openai_session:
            messages = await self.openai_session.get_items(limit=limit)
            self.task_message_state.sync_from_openai_session(messages)

    


@dataclass
class RunningSession:

    siada_config: RunningConfig

    session_id: str = field(default_factory=lambda: str(uuid4()))

    state: SessionState = field(default_factory=SessionState)

    checkpoint_tracker: Optional[CheckPointTracker] = None

    def get_input(self) -> str:
        return self.siada_config.io.get_input()
