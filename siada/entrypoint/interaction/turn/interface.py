"""
Turn Interface Module

Contains abstract base classes and interfaces for interaction turns.
"""

from typing import Optional, Any
from abc import ABC, abstractmethod

from agents import TResponseInputItem

# Import existing config and models
from ..config import RunningConfig
from .models import TurnType, TurnInput, TurnOutput


class RunTurn(ABC):
    """Abstract base class for interaction turns"""

    def __init__(self, config: RunningConfig, session: Any, slash_commands: Any):
        """Initialize turn with configuration and session

        Args:
            config: InteractionConfig with execution parameters
            session: Current session instance
        """
        self.config = config
        self.session = session
        self.slash_commands = slash_commands

        # Data tracking
        self.input_data: Optional[TurnInput] = None
        self.output_data: Optional[TurnOutput] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[Exception] = None

    @abstractmethod
    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute the turn with given input

        Args:
            turn_input: Input data for this turn

        Returns:
            TurnOutput: Result of turn execution
        """
        pass

    def can_handle(self, user_input: str) -> bool:
        """Check if this turn type can handle the given input

        Args:
            user_input: Raw user input string

        Returns:
            bool: True if this turn can handle the input
        """
        return True

    def prepare_input(self, raw_input: str) -> TurnInput:
        """Prepare turn input from raw user input

        Args:
            raw_input: Raw user input string

        Returns:
            TurnInput: Prepared input for turn execution
        """
        return TurnInput(use_input=raw_input)

    def get_turn_type(self) -> TurnType:
        """Get the type of this turn

        Returns:
            TurnType: Type of this turn
        """
        return TurnType.CONVERSATION

    def validate_input(self, turn_input: TurnInput) -> bool:
        """Validate turn input

        Args:
            turn_input: Input to validate

        Returns:
            bool: True if input is valid
        """
        return bool(turn_input.use_input and turn_input.use_input.strip())

    def handle_error(self, error: Exception) -> TurnOutput:
        """Handle execution error

        Args:
            error: Exception that occurred

        Returns:
            TurnOutput: Error response
        """
        self.error = error
        
        # Print full error traceback for debugging
        import traceback
        full_traceback = traceback.format_exc()
        self.config.io.print_error(f"Error occurred: {str(error)}\n\nFull traceback:\n{full_traceback}")
        return TurnOutput(
            output=f"Error: {str(error)}",
            metadata={"error_type": type(error).__name__},
            next_action=None,
        )

    def _get_timestamp(self) -> float:
        """Get current timestamp"""
        import time

        return time.time()