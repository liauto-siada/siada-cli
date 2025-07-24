"""
Run Turn Module

Manages individual interaction turns between user and AI, including command processing
and model conversations. Encapsulates the logic for a single interaction cycle.
"""

import re
from siada.support.slash_commands import SwitchEvent
import sys
import siada.io.components.mdstream
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum

from agents import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    RunResultStreaming,
    StreamEvent,
    ToolCallOutputItem,
)

# Import existing InteractionConfig
from .config import InteractionConfig


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


class RunTurn(ABC):
    """Abstract base class for interaction turns"""

    def __init__(self, config: InteractionConfig, session: Any, slash_commands: Any):
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
        return TurnInput(use_input=raw_input, turn_type=self.get_turn_type())

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
        self.config.io.print_error(str(error))

        return TurnOutput(
            output=f"Error: {str(error)}",
            metadata={"error_type": type(error).__name__},
        )

    def _get_timestamp(self) -> float:
        """Get current timestamp"""
        import time

        return time.time()


# Standard tag identifier
REASONING_TAG = "thinking-content-" + "7bbeb8e1441453ad999a0bbba8a46d4b"
# Output formatting
REASONING_START = "--------------\n► **THINKING**"
REASONING_END = "------------\n► **ANSWER**"


class ConversationTurn(RunTurn):
    """Handles regular AI conversation turns"""

    mdstream: siada.io.components.mdstream.MarkdownStream = None
    response_content: str = None
    tool_call: str = None
    tool_call_output: str = None
    got_tool_call_arguments: bool = False

    def get_turn_type(self) -> TurnType:
        return TurnType.CONVERSATION

    def can_handle(self, user_input: str) -> bool:
        """Handle non-command input"""
        return not self.config.slash_commands.is_command(user_input)

    async def output_stream_content(self, result: RunResultStreaming) -> None:
        """Process stream events and handle real-time output"""
        from openai.types.responses import (
            ResponseTextDeltaEvent,
            ResponseReasoningSummaryTextDeltaEvent,
            ResponseFunctionCallArgumentsDeltaEvent,
            ResponseContentPartAddedEvent,
            ResponseOutputItemAddedEvent,
            ResponseCompletedEvent,
            ResponseCreatedEvent,
            ResponseReasoningSummaryPartAddedEvent,
            ResponseFunctionToolCall,
        )

        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent):

                # Handle the raw response stream event
                stream_data = event.data

                # Handle different types of stream events
                if isinstance(stream_data, ResponseCreatedEvent):
                    # Response started
                    self.mdstream = (
                        self.config.io.get_assistant_mdstream()
                        if self.config.io.pretty
                        else None
                    )
                    self.response_content = ""
                    self.tool_call = ""
                    self.tool_call_output = ""
                    self.got_tool_call_arguments = False

                elif isinstance(stream_data, ResponseReasoningSummaryPartAddedEvent):
                    delta_text = f"\n{REASONING_START}\n\n"
                    self.response_content += delta_text

                    self._live_incremental_response(delta_text, self.response_content)

                elif isinstance(stream_data, ResponseReasoningSummaryTextDeltaEvent):
                    delta_text = stream_data.delta
                    self.response_content += delta_text
                    self._live_incremental_response(delta_text, self.response_content)

                elif isinstance(stream_data, ResponseContentPartAddedEvent):
                    delta_text = f"\n\n{REASONING_END}\n\n"
                    self.response_content += delta_text
                    self._live_incremental_response(delta_text, self.response_content)

                elif isinstance(stream_data, ResponseTextDeltaEvent):
                    self.response_content += stream_data.delta
                    self._live_incremental_response(
                        stream_data.delta, self.response_content
                    )

                elif isinstance(stream_data, ResponseOutputItemAddedEvent):
                    if isinstance(stream_data.item, ResponseFunctionToolCall):
                        self.tool_call = f"Siadahub wants to call the following function:  {stream_data.item.name}\n"
                        self._live_incremental_response(self.tool_call, self.tool_call)

                elif isinstance(stream_data, ResponseFunctionCallArgumentsDeltaEvent):
                    delta_text = ""
                    if not self.got_tool_call_arguments:
                        delta_text = f"Arguments: \n{stream_data.delta}\n"
                        self.got_tool_call_arguments = True
                    else:
                        delta_text = stream_data.delta
                    self._live_incremental_response(delta_text, self.tool_call)

                # elif isinstance(stream_data, ResponseOutputItemDoneEvent):
                #     if isinstance(stream_data.item, ResponseFunctionToolCall):
                #         self.config.io.print_tool_call(self.tool_call)

                elif isinstance(stream_data, ResponseCompletedEvent):
                    delta_text = f"\n\n✅ Response completed\n\n"
                    self.response_content += delta_text
                    self._live_incremental_response(delta_text, self.response_content)
                    self.mdstream = None
                    self.response_content = None
                    self.tool_call = None
                    self.tool_call_output = None
                    self.got_tool_call_arguments = False

            elif isinstance(event, RunItemStreamEvent):
                stream_data = event.item
                if isinstance(stream_data, ToolCallOutputItem):
                    self.tool_call_output = f"Tool call output: \n{stream_data.output}"
                    self.config.io.print_tool_result(self.tool_call_output)

    def _live_incremental_response(self, delta_text: str, response_content: str):
        if self.mdstream:
            self.mdstream.update(response_content)
        else:
            self.config.io.print_info(delta_text)

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute AI conversation turn

        Args:
            turn_input: User input for conversation

        Returns:
            TurnOutput: AI response
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()

        try:
            # Import here to avoid circular imports
            from siada.services.siada_runner import SiadaRunner

            # Run agent for conversation
            result: RunResultStreaming = SiadaRunner.run_agent(
                agent_name=self.config.agent_name,
                user_input=turn_input.use_input,
                workspace=self.config.workspace,
                session=self.session,
                stream=True,
            )

            result.stream_events()

            self.end_time = self._get_timestamp()

            output = TurnOutput(
                output=result.final_output,
                metadata={
                    "agent_used": self.config.agent_name,
                    "execution_time": self.end_time - self.start_time,
                },
                next_action=None,
            )

            self.output_data = output
            return output

        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)


class CommandTurn(RunTurn):
    """Handles slash command turns"""

    def get_turn_type(self) -> TurnType:
        return TurnType.COMMAND

    def can_handle(self, user_input: str) -> bool:
        """Handle slash commands"""
        return self.slash_commands.is_command(user_input)

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute slash command

        Args:
            turn_input: Command input

        Returns:
            TurnOutput: Command result
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()

        try:
            result = self.slash_commands.run(self.session, turn_input.use_input)
            self.end_time = self._get_timestamp()

            output = TurnOutput(
                output=result,
                metadata={"execution_time": self.end_time - self.start_time},
                next_action=None,
            )

            return output

        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)


class TurnFactory:
    """Factory for creating appropriate turn instances"""

    @staticmethod
    def create_turn(
        config: InteractionConfig, session: Any, slash_commands: Any, user_input: str
    ) -> RunTurn:
        """Create appropriate turn for user input

        Args:
            user_input: Raw user input

        Returns:
            RunTurn: Appropriate turn handler
        """
        # Always create new instances to avoid state pollution
        turn_types = [
            CommandTurn,
            ConversationTurn,
        ]

        for turn_class in turn_types:
            # Create a temporary instance to test if it can handle the input
            temp_turn = turn_class(config, session, slash_commands)
            if temp_turn.can_handle(user_input):
                return temp_turn

        raise ValueError(f"No turn can handle the input: {user_input}")
