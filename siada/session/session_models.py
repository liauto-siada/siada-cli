from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from agents import SQLiteSession
from siada.entrypoint.interaction.interaction_controller import InteractionConfig
from siada.io.io import InputOutput
from siada.models.model_setting import ModelConfig
from siada.support.commands import SlashCommands

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
class Session:
    
    session_id: str = field(default_factory=lambda: str(uuid4()))

    interaction_config: InteractionConfig
    
    state: SessionState = field(default_factory=SessionState)
