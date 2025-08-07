"""
Interaction Session Management Module

Provides interaction session management functionality working with FileSession:

Core Features:
- Create interaction sessions and associated FileSession
- Interaction session and file_session share the same ID
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
