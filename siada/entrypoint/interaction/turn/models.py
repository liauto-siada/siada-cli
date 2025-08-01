"""
Turn Models Module

Contains data models and type definitions for interaction turns.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from siada.support.slash_commands import SwitchEvent


class TurnType(Enum):
    """Types of interaction turns"""

    COMMAND = "command"  # Slash commands (/help, /edit, etc.)
    CONVERSATION = "conversation"  # Regular AI conversation


@dataclass
class TurnInput:
    """Input data for a turn"""

    use_input: str  # Raw user input


@dataclass
class TurnOutput:
    """Output data from a turn"""

    output: str | SwitchEvent  # Response content
    metadata: Dict[str, Any]  # Response metadata
    next_action: Optional[str]  # Suggested next action