"""
HandleAtCommand - A service for processing @ commands in user queries.

This package provides functionality to parse user input containing @ commands,
resolve file paths, read file contents, and inject them into AI context.

Main Components:
- AtCommandProcessor: Main processor that coordinates all components
- AtCommandParser: Parses @ commands from user input
- PathResolver: Resolves @ paths to actual file paths
- Models: Data structures and type definitions
- Exceptions: Custom exception classes
- Utils: Utility functions

Usage:
    from siada.services.handle_at_command import AtCommandProcessor, HandleAtCommandParams
    
    processor = AtCommandProcessor(config)
    params = HandleAtCommandParams(
        query="Please explain @file.py",
        config=config,
        add_item=add_item_func,
        on_debug_message=debug_func,
        message_id=123
    )
    result = await processor.handle_at_command(params)
"""

from .processor import AtCommandProcessor
from .parser import AtCommandParser
from .resolver import PathResolver
from .models import (
    AtCommandPart,
    HandleAtCommandParams,
    HandleAtCommandResult,
    ResolverContext,
    PathResolutionResult,
    ProcessingStats,
    IgnoredFileStats
)
from .exceptions import (
    AtCommandError,
    PathNotFoundError,
    PathIgnoredError,
    FileTooLargeError,
    PermissionDeniedError,
    SecurityViolationError,
    InvalidPathError,
    WorkspaceSecurityError
)
from . import utils

__all__ = [
    # Main classes
    'AtCommandProcessor',
    'AtCommandParser',
    'PathResolver',
    
    # Data models
    'AtCommandPart',
    'HandleAtCommandParams',
    'HandleAtCommandResult',
    'ResolverContext',
    'PathResolutionResult',
    'ProcessingStats',
    'IgnoredFileStats',
    
    # Exceptions
    'AtCommandError',
    'PathNotFoundError',
    'PathIgnoredError',
    'FileTooLargeError',
    'PermissionDeniedError',
    'SecurityViolationError',
    'InvalidPathError',
    'WorkspaceSecurityError',
    
    # Utilities
    'utils'
]

# Version information
__version__ = '1.0.0'
__author__ = 'Siada Team'
__description__ = 'A service for processing @ commands in user queries'


# Convenience function for easy usage
async def handle_at_command(query: str, config, add_item: callable, 
                           on_debug_message: callable, message_id: int, 
                           signal=None) -> HandleAtCommandResult:
    """
    Convenience function to handle @ commands
    
    Args:
        query: User input query
        config: Configuration object
        add_item: Function to add items to history
        on_debug_message: Debug message callback
        message_id: Message ID
        signal: Cancellation signal (optional)
        
    Returns:
        HandleAtCommandResult with processed query and status
    """
    processor = AtCommandProcessor(config)
    params = HandleAtCommandParams(
        query=query,
        config=config,
        add_item=add_item,
        on_debug_message=on_debug_message,
        message_id=message_id,
        signal=signal
    )
    return await processor.handle_at_command(params)
