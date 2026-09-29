"""
Services package for Siada.

This package contains various services used throughout the Siada application.

Submodules are imported lazily on demand: any ``from siada.services.X import Y`` executes this file,
and the previous top-level imports of handle_at_command/file_recommendation/git_service used to pull in
heavy dependencies such as rich/spinner/read_many_files_tool before skills load (~100ms).
"""

import importlib

_LAZY_EXPORTS = {
    'AtCommandProcessor': '.handle_at_command',
    'HandleAtCommandParams': '.handle_at_command',
    'HandleAtCommandResult': '.handle_at_command',
    'handle_at_command': '.handle_at_command',
    'FileRecommendationEngine': '.file_recommendation',
    'CompletionConfig': '.file_recommendation',
    'FilterOptions': '.file_recommendation',
    'DEFAULT_COMPLETION_CONFIG': '.file_recommendation',
    'GitService': '.git_service',
    'GitServiceError': '.git_service',
}

# FileSession intentionally NOT imported here: file_session.py pulls in
# agents.memory.session (557ms agents SDK) which must not load at startup.
# Import it directly: from siada.services.file_session import FileSession

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        module = importlib.import_module(_LAZY_EXPORTS[name], __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
