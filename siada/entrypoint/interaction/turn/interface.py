"""
Turn Interface Module

Contains abstract base classes and interfaces for interaction turns.
"""

from typing import Optional, Any
from abc import ABC, abstractmethod

from agents import AgentsException


# Import existing config and models
from ..running_config import RunningConfig
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
        self.error = error
        
        import traceback
        from siada.foundation.logging import logger
        
        full_traceback = traceback.format_exc()
        error_str = str(error)
        error_type = type(error).__name__
        
        # Log full error information to log file
        logger.error(f"Turn execution error: {error_type}: {error_str}\n{full_traceback}")
        
        # Identify BadGatewayError (litellm)
        if "BadGatewayError" in error_type or "BadGatewayError" in error_str:
            self.config.io.print_error(
                "Network Connection Error\n\n"
                "Unable to connect to AI model service. This is usually a temporary network issue.\n\n"
                "Suggested Actions:\n"
                "  1. Check your network connection\n"
                "  2. If using internal service, verify VPN connection status\n"
                "  3. Retry your request later\n"
                "  4. If the problem persists, contact your administrator\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle other network connection errors
        elif "Cannot connect to host" in error_str or "nodename nor servname" in error_str:
            self.config.io.print_error(
                "Network Connection Error\n\n"
                "Cannot connect to model server.\n\n"
                "Suggested Actions:\n"
                "  1. Check VPN connection (if using internal service)\n"
                "  2. Check network connectivity\n"
                "  3. Check DNS configuration\n"
                "  4. Verify server address is configured correctly\n\n"
                f"Error Details: {error_str}\n"
            )
        # Handle timeout errors
        elif "timeout" in error_str.lower() or "TimeoutError" in error_type:
            self.config.io.print_error(
                "Request Timeout\n\n"
                "Connection to AI model service timed out.\n\n"
                "Suggested Actions:\n"
                "  1. Check your network connection speed\n"
                "  2. Retry your request later\n"
                "  3. If the problem persists, contact your administrator\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle API rate limit errors
        elif "rate limit" in error_str.lower() or "429" in error_str:
            self.config.io.print_error(
                "API Rate Limit Exceeded\n\n"
                "Too many requests. Rate limit has been reached.\n\n"
                "Suggested Actions:\n"
                "  1. Wait a moment before retrying\n"
                "  2. Reduce request frequency\n"
                "  3. Contact your administrator to increase quota if needed\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle prompt too long errors
        elif "prompt" in error_str.lower() and ("too long" in error_str.lower() or "413" in error_str):
            self.config.io.print_error(
                "Input Too Long\n\n"
                "Your input or context exceeds the model's processing limit.\n\n"
                # "Suggested Actions:\n"
                # "  1. Reduce the length of your input text\n"
                # # "  2. Use /clear command to clear conversation history\n"
                # "  2. Process large tasks in batches\n"
                # "  4. Remove unnecessary context files\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle Agent-related errors
        elif isinstance(error, AgentsException):
            self.config.io.print_error(
                f"Agent Execution Error\n\n"
                f"{error_str}\n\n"
                f"Detailed Log: logs/errors.log"
            )
        # Handle version too low errors
        elif "minimum required version" in error_str or "below the minimum required version" in error_str:
            import re
            import json

            upgrade_cmd = None
            version_info = None

            # Extract JSON message body from error_str
            json_match = re.search(r"b'(\{.*?\})'", error_str)
            if json_match:
                try:
                    payload = json.loads(json_match.group(1))
                    msg = payload.get("message", "")
                    ver_match = re.search(
                        r"version \(([^)]+)\) is below the minimum required version \(([^)]+)\)", msg
                    )
                    if ver_match:
                        version_info = f"Current version: {ver_match.group(1)}  →  Required: {ver_match.group(2)}"
                    cmd_match = re.search(r"(curl\s+\S+.*)", msg)
                    if cmd_match:
                        upgrade_cmd = cmd_match.group(1)
                except (json.JSONDecodeError, AttributeError):
                    pass

            lines = ["Siada CLI Version Outdated\n"]
            if version_info:
                lines.append(f"{version_info}\n")
            lines.append("Please upgrade to the latest version:\n")
            if upgrade_cmd:
                lines.append(f"  {upgrade_cmd}\n")
            else:
                lines.append(
                    "  curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh\n"
                )
            self.config.io.print_error("".join(lines))
        # Handle other uncategorized errors
        else:
            self.config.io.print_error(
                f"An Error Occurred\n\n"
                f"Error Type: {error_type}\n"
                f"Error Message: {error_str}\n\n"
            )
        
        return TurnOutput(
            output=f"Error: {error_str}",
            metadata={"error_type": error_type},
            next_action=None,
        )


    def _get_timestamp(self) -> float:
        """Get current timestamp"""
        import time

        return time.time()