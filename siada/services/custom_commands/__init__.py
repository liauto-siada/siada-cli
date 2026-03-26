"""
Custom Commands System for Siada CLI

This module provides a flexible custom command system that allows users to define
reusable prompt templates with advanced features like:
- Parameter injection with {{args}}
- Shell command execution with !{...}
- File content injection with @{...}
- User global commands and project-specific commands
"""

# Use relative imports to avoid triggering siada.services.__init__.py
from .command_loader import FileCommandLoader
from .command_service import CommandService
from .types import CommandContext, CustomCommand, CommandResult

__all__ = [
    'FileCommandLoader',
    'CommandService',
    'CommandContext',
    'CustomCommand',
    'CommandResult',
]
