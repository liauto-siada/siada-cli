"""
File Recommendation Service - @ 文件推荐功能

This package provides intelligent file path auto-completion for @ commands.
When users type @ followed by text, the system provides real-time file and directory suggestions.

Main Components:
- FileRecommendationEngine: Main engine that coordinates all components
- CompletionEngine: Core completion logic
- FileDiscoveryService: File discovery and filtering
- Suggestion data structures and utilities

Usage:
    from siada.services.file_recommendation import FileRecommendationEngine
    
    engine = FileRecommendationEngine(
        current_directory=os.getcwd(),
        config=CompletionConfig()
    )
    
    if engine.should_show_suggestions("@src/main"):
        suggestions = engine.get_suggestions("@src/main")
"""

from .core.completion_engine import CompletionEngine
from .core.file_discovery import FileDiscoveryService
from .core.suggestion import Suggestion
from .core.config import CompletionConfig, FilterOptions, DEFAULT_COMPLETION_CONFIG
from .utils.path_utils import escape_path, unescape_path
from .utils.text_utils import (
    is_completion_active, 
    parse_at_command_path,
    to_code_points, 
    cp_len, 
    cp_slice
)

__all__ = [
    # Main classes
    'CompletionEngine',
    'FileDiscoveryService',
    'FileRecommendationEngine',
    
    # Data structures
    'Suggestion',
    'CompletionConfig',
    'FilterOptions',
    'DEFAULT_COMPLETION_CONFIG',
    
    # Utilities
    'escape_path',
    'unescape_path',
    'is_completion_active',
    'parse_at_command_path',
    'to_code_points',
    'cp_len',
    'cp_slice'
]

# Version information
__version__ = '1.0.0'
__author__ = 'Siada Team'
__description__ = 'Intelligent file path auto-completion for @ commands'


class FileRecommendationEngine:
    """
    Main file recommendation engine
    
    This is the primary interface for the file recommendation functionality.
    """
    
    def __init__(self, current_directory: str = None, config: CompletionConfig = None):
        """
        Initialize the file recommendation engine
        
        Args:
            current_directory: Current working directory (default: current working directory)
            config: Completion configuration (default: DEFAULT_COMPLETION_CONFIG)
        """
        import os
        
        self.current_directory = current_directory or os.getcwd()
        self.config = config or DEFAULT_COMPLETION_CONFIG
        
        # Initialize components
        self.file_discovery = FileDiscoveryService(self.current_directory)
        self.completion_engine = CompletionEngine(
            search_directories=[self.current_directory],
            config=self.config
        )
    
    def should_show_suggestions(self, text: str, cursor_row: int = 0, cursor_col: int = None) -> bool:
        """
        Check if file suggestions should be shown
        
        Args:
            text: Input text
            cursor_row: Cursor row position (default: 0)
            cursor_col: Cursor column position (default: end of text)
            
        Returns:
            bool: True if suggestions should be shown
        """
        # Use the completion engine's logic for determining when to show suggestions
        return self.completion_engine.should_show_suggestions(text)
    
    async def get_suggestions(self, text: str) -> list[Suggestion]:
        """
        Get file suggestions for the given text
        
        Args:
            text: Input text containing @ command
            
        Returns:
            List of file suggestions
        """
        return await self.completion_engine.get_suggestions(text)
    
    def get_suggestions_sync(self, text: str) -> list[Suggestion]:
        """
        Synchronous version of get_suggestions
        
        Args:
            text: Input text containing @ command
            
        Returns:
            List of file suggestions
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_suggestions(text))
        except RuntimeError:
            # No event loop running, create a new one
            return asyncio.run(self.get_suggestions(text))
