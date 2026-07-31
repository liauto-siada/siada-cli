"""
Services package for Siada.

This package contains various services used throughout the Siada application.
"""

from .handle_at_command import (
    AtCommandProcessor,
    HandleAtCommandParams,
    HandleAtCommandResult,
    handle_at_command
)

from .file_recommendation import (
    FileRecommendationEngine,
    CompletionConfig,
    FilterOptions,
    DEFAULT_COMPLETION_CONFIG
)

from .git_service import (
    GitService,
    GitServiceError
)

# FileSession intentionally NOT imported here: file_session.py pulls in
# agents.memory.session (557ms agents SDK) which must not load at startup.
# Import it directly: from siada.services.file_session import FileSession

__all__ = [
    'AtCommandProcessor',
    'HandleAtCommandParams', 
    'HandleAtCommandResult',
    'handle_at_command',
    'FileRecommendationEngine',
    'CompletionConfig',
    'FilterOptions',
    'DEFAULT_COMPLETION_CONFIG',
    'GitService',
    'GitServiceError',
]
