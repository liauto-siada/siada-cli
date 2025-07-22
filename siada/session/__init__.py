"""
Interaction Session Management Module

Provides interaction session management functionality working with OpenAI Agents SQLiteSession:

Core Features:
- Create interaction sessions and associated OpenAI SQLiteSession
- Interaction session and openai_session share the same ID
- Support ModelSettings model configuration
- Simplified API focusing on session creation
"""

from .session_models import (
    Session,
    SessionState
)

from .session_manager import (
    InteractionSessionManager,
)

__all__ = [
    # Data models
    "Session",
    "SessionState",
    
    # Managers
    "InteractionSessionManager",
]
