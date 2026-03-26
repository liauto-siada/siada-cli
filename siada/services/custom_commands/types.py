"""
Type definitions for custom commands system
"""

from typing import Callable, Dict, Any, List, Optional, Union
from dataclasses import dataclass
from enum import Enum


class CommandKind(Enum):
    """Type of command"""
    BUILTIN = "builtin"  # Built-in system commands
    FILE = "file"        # User-defined commands from files
    MCP = "mcp"          # MCP server prompts


@dataclass
class CommandContext:
    """
    Context provided to command actions during execution.
    Contains all necessary information for processing commands.
    """
    # Session information
    session: Any  # The current session object
    
    # Configuration
    workspace: str  # Current workspace directory
    
    # IO interface
    io: Any  # IO object for printing messages
    
    # Command invocation details
    invocation: Dict[str, Any]  # {raw: str, name: str, args: str}
    
    # Optional services
    verbose: bool = False
    

@dataclass
class CommandResult:
    """
    Result of command execution
    """
    type: str  # 'submit_prompt', 'confirm_shell_commands', 'noop'
    content: Optional[str] = None  # Processed prompt content
    commands_to_confirm: Optional[List[str]] = None  # Shell commands needing confirmation
    original_invocation: Optional[Dict[str, Any]] = None  # For retry after confirmation


@dataclass
class CustomCommand:
    """
    Represents a custom slash command loaded from a TOML file.
    """
    name: str  # Command name (e.g., "git:commit", "review")
    description: Optional[str]  # Human-readable description
    prompt: str  # The prompt template
    kind: CommandKind  # Type of command
    extension_name: Optional[str] = None  # For extension commands
    
    # Execution function
    action: Optional[Callable[[CommandContext, str], CommandResult]] = None


# Special syntax markers
SHORTHAND_ARGS_PLACEHOLDER = '{{args}}'  # Parameter placeholder
SHELL_INJECTION_TRIGGER = '!{'           # Shell command execution
AT_FILE_INJECTION_TRIGGER = '@{'         # File content injection


class ConfirmationRequiredError(Exception):
    """
    Exception raised when shell commands need user confirmation
    """
    def __init__(self, message: str, commands: List[str]):
        super().__init__(message)
        self.commands = commands
