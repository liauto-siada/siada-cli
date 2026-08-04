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


class ImageNotSupportedError(Exception):
    """Raised when the bound model cannot process images and the user
    message has no meaningful text content.

    The error message is already printed to the frontend by the raiser,
    so handle_error() should return None silently instead of printing
    a generic "An Error Occurred" box.
    """
    pass


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

    def handle_error(self, error: Exception) -> Optional[TurnOutput]:
        self.error = error

        import traceback
        from siada.foundation.logging import logger

        full_traceback = traceback.format_exc()
        error_str = str(error)
        error_type = type(error).__name__

        # ImageNotSupportedError: print the user-facing error message
        # (not a generic "An Error Occurred" box) and return TurnOutput.
        if isinstance(error, ImageNotSupportedError):
            logger.info(f"Image not supported: {error_str}")
            self.config.io.print_error(
                "⚠️ The current model does not support image input. "
                "Please provide a text message or switch to a model "
                "that supports image understanding."
            )
            return TurnOutput(
                output=f"Error: {error_str}",
                metadata={"error_type": error_type},
                next_action=None,
            )

        # Log full error information to log file
        logger.error(f"Turn execution error: {error_type}: {error_str}\n{full_traceback}")

        # Extract li-mate server message from API error body (HTTP 403/429)
        # li-mate returns: {"error": ..., "code": <status>, "message": "<full message>"}
        li_mate_message = _extract_li_mate_message(error)
        if li_mate_message:
            self.config.io.print_error(f"{li_mate_message}\n")
        # Handle rate limit errors (e.g. Moonshot 429): only tell the user
        # the model is rate limited, don't show the raw provider error.
        elif "RateLimitError" in error_type:
            self.config.io.print_error("Model rate limited, please wait a moment and try again\n")
        # Identify BadGatewayError (litellm)
        elif "BadGatewayError" in error_type or "BadGatewayError" in error_str:
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
        # Handle transient upstream model errors (litellm mid-stream fallback /
        # provider InternalServerError, e.g. Vertex AI Gemini connection drop)
        elif "MidStreamFallbackError" in error_type or "InternalServerError" in error_type:
            structured_message = _extract_structured_message(error_str)
            self.config.io.print_error(
                "Model Service Temporary Error\n\n"
                "This is usually transient — please retry your request.\n\n"
                + (f"{structured_message}\n\n" if structured_message else "")
                + f"Error Type: {error_type}\n"
            )
        # Handle timeout errors
        elif "timeout" in error_str.lower() or "TimeoutError" in error_type:
            self.config.io.print_error(
                "Request Timeout\n\n"
                "Connection to AI model service timed out.\n\n"
                "Suggested Actions:\n"
                "  1. Check your network connection speed\n"
                "  2. Retry your request later\n"
                "  3. If the problem persists, contact  administrator\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle prompt too long errors
        elif "prompt" in error_str.lower() and ("too long" in error_str.lower() or "413" in error_str):
            self.config.io.print_error(
                "Input Too Long\n\n"
                "Your input or context exceeds the model's processing limit.\n\n"
                f"Error Type: {error_type}\n"
            )
        # Handle BadRequestError (e.g. li-mate/Anthropic model not connected)
        elif "BadRequestError" in error_type:
            structured_message = _extract_structured_message(error_str)
            self.config.io.print_error(
                "Request Parameter Error\n\n"
                + (structured_message or error_str)
                + "\n\n"
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
                from siada.services.auto_update import get_curl_install_flags

                lines.append(
                    f"  curl {get_curl_install_flags()} https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh\n"
                )

            self.config.io.print_error("".join(lines))
        # Handle other uncategorized errors
        else:
            structured_message = _extract_structured_message(error_str)
            self.config.io.print_error(
                f"An Error Occurred\n\n"
                f"Error Type: {error_type}\n"
                f"Error Message: {structured_message or error_str}\n\n"
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


def _extract_structured_message(error_str: str) -> str | None:
    """Extract a human-readable message from an error string containing a
    raw bytes-literal JSON body, e.g.:

        b'{"code":4000004,"message":"\\xe6\\xa8\\xa1...","data":"..."}'

    litellm/anthropic sometimes embeds the raw HTTP response body (as a
    Python bytes repr) inside the exception message. Non-ASCII text (e.g.
    Chinese) then shows up as escaped byte sequences instead of readable
    characters. This decodes the bytes literal as UTF-8 and extracts the
    "message"/"data" fields into a readable string.
    """
    import ast
    import json
    import re

    match = re.search(r"b'(\{.*\})'", error_str, re.DOTALL)
    if not match:
        return None

    try:
        raw_bytes = ast.literal_eval(match.group(0))
        decoded = raw_bytes.decode("utf-8") if isinstance(raw_bytes, bytes) else str(raw_bytes)
        payload = json.loads(decoded)
    except (ValueError, SyntaxError):
        return None

    if not isinstance(payload, dict):
        return None

    parts = []
    code = payload.get("code")
    message = payload.get("message")
    data = payload.get("data")
    if code is not None:
        parts.append(f"Code: {code}")
    if isinstance(message, str) and message.strip():
        parts.append(f"Info: {message.strip()}")
    if isinstance(data, str) and data.strip() and data.strip() != message:
        parts.append(f"Detailed: {data.strip()}")

    return "\n".join(parts) if parts else None


def _extract_li_mate_message(error: Exception) -> str | None:
    """Extract the user-facing message from a li-mate API error (HTTP 403/429).

    li-mate returns JSON bodies like:
      {"error": <str|obj>, "code": <status>, "message": "<full message>"}

    The openai/litellm SDK wraps this in APIStatusError subclasses
    (PermissionDeniedError for 403, RateLimitError for 429), where:
      - str(error) = error.message (may be truncated, not the full message)
      - error.body = the parsed JSON body (contains the full message)

    This function extracts the full message from error.body["message"]
    (or error.body["error"]["message"] as fallback).
    """
    body = getattr(error, 'body', None)
    if not isinstance(body, dict):
        return None

    # Primary: top-level "message" field
    message = body.get('message')
    if isinstance(message, str) and message.strip():
        return message.strip()

    # Fallback: nested error.message (li-mate quota format)
    error_field = body.get('error')
    if isinstance(error_field, dict):
        message = error_field.get('message')
        if isinstance(message, str) and message.strip():
            return message.strip()

    return None
