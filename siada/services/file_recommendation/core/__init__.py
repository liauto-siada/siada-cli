"""
Core components for file recommendation functionality.
"""

from .completion_engine import CompletionEngine
from .file_discovery import FileDiscoveryService
from .suggestion import Suggestion
from .config import CompletionConfig, FilterOptions, DEFAULT_COMPLETION_CONFIG

__all__ = [
    'CompletionEngine',
    'FileDiscoveryService', 
    'Suggestion',
    'CompletionConfig',
    'FilterOptions',
    'DEFAULT_COMPLETION_CONFIG'
]
