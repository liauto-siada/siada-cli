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
    RunningSession,
    SessionState
)

from .session_manager import (
    RunningSessionManager,
)

__all__ = [
    # Data models
    "RunningSession",
    "SessionState",
    
    # Managers
    "RunningSessionManager",
]
