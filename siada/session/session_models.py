from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from uuid import uuid4

from agents import SQLiteSession

from siada.entrypoint.interaction.config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig


@dataclass
class SessionState:
    """
    Interaction session state data model
    
    Stores state information during user interactions, complementing OpenAI Agents' SQLiteSession:
    - SQLiteSession: Stores large language model conversation history
    - SessionState: Stores interaction state and context information
    """

    # Core state fields
    context_vars: Dict[str, Any] = field(default_factory=dict)
    """Context variables, works with foundation.context module"""

    # Agent-related state
    current_agent: Optional[str] = None
    """Currently active Agent name"""
    
    openai_session: Optional[SQLiteSession] = None


@dataclass
class RunningSession:

    siada_config: RunningConfig

    session_id: str = field(default_factory=lambda: str(uuid4()))

    state: SessionState = field(default_factory=SessionState)

    def get_input(self) -> str:
        return self.siada_config.io.get_input()
