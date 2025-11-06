from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from uuid import uuid4

from siada.services.file_session import FileSession

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.session.task_message_state import TaskMessageState
from siada.support.checkpoint_tracker import CheckPointTracker
from agents.usage import Usage

if TYPE_CHECKING:
    from siada.support.spinner import WaitingSpinner


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

    usage: Optional[Usage] = None
    
    # UI components (injected dependencies)  
    spinner: Any = None
    """Waiting spinner for showing progress during agent execution"""



@dataclass
class RunningSession:

    siada_config: RunningConfig

    session_id: str = field(default_factory=lambda: str(uuid4()))

    state: SessionState = field(default_factory=SessionState)

    checkpoint_tracker: Optional[CheckPointTracker] = None


    @property
    def task_message_state(self) -> TaskMessageState:
        return self.state.task_message_state
    

    def get_input(self) -> str:
        return self.siada_config.io.get_input()
    
    @property
    def openai_session(self) -> Optional[FileSession]:
        return self.state.openai_session
    
    @property
    def spinner(self) -> Any:
        """Get the spinner from session state"""
        return self.state.spinner
