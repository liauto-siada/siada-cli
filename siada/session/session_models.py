from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from agents import SQLiteSession
from siada.models.model_settings import ModelSettings


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
    """
    Interaction session model
    
    Manages user interaction sessions, working together with OpenAI Agents' session system:
    - OpenAI SQLiteSession: Manages large language model conversation history and memory
    - Our Session: Manages interaction state, context and business logic
    """
    
    # Basic information
    session_id: str = field(default_factory=lambda: str(uuid4()))
    """Unique session identifier"""
    
    # Model configuration
    config: Optional[ModelSettings] = None
    """Model configuration information using ModelSettings structure"""
    
    # Interaction state data
    state: SessionState = field(default_factory=SessionState)
    """Session state object"""
