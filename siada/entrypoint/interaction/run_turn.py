"""
Run Turn Module

Manages individual interaction turns between user and AI, including command processing
and model conversations. Encapsulates the logic for a single interaction cycle.
"""

from siada.foundation.logging import logger
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


# Standard tag identifier
REASONING_TAG = "thinking-content-" + "7bbeb8e1441453ad999a0bbba8a46d4b"
# Output formatting
REASONING_START = "--------------\n► **THINKING**"
REASONING_END = "------------\n► **ANSWER**"

DEFAULT_REASONING_TAG = "thinking"


class ConversationTurn(RunTurn):
    """Handles regular AI conversation turns"""

    mdstream: siada.io.components.mdstream.MarkdownStream = None
    response_content: str = None
    tool_call: str = None
    tool_call_output: str = None
    got_tool_call_arguments: bool = False
    
    # Class-level dedicated event loop and thread, shared by all instances
    _dedicated_loop = None
    _dedicated_thread = None
    _loop_ready = None

    @classmethod
    def _ensure_dedicated_loop(cls):
        """Ensure dedicated event loop is started"""
        if cls._dedicated_loop is None or cls._dedicated_loop.is_closed():
            import threading
            import asyncio
            
            # Detect if main thread has a running event loop (prompt_toolkit might be using it)
            try:
                main_loop = asyncio.get_running_loop()
                logger.info(f"📋 Detected main thread event loop: {id(main_loop)}")
            except RuntimeError:
                logger.info("📋 No event loop in main thread")  # Normal case
            
            # Create event for synchronization
            cls._loop_ready = threading.Event()
            
            def run_dedicated_loop():
                """Run event loop in dedicated thread"""
                # Create new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._dedicated_loop = loop
                
                # Notify main thread that loop is ready
                cls._loop_ready.set()
                
                try:
                    # Run event loop until stopped
                    loop.run_forever()
                finally:
                    # Cleanup
                    loop.close()
                    cls._dedicated_loop = None
            
            # Start dedicated thread
            cls._dedicated_thread = threading.Thread(
                target=run_dedicated_loop, 
                daemon=True,  # Daemon thread, auto-terminate when main program exits
                name="ConversationTurn-AsyncLoop"
            )
            cls._dedicated_thread.start()
            
            # Wait for event loop to be ready
            cls._loop_ready.wait()
    
    @classmethod
    def _cleanup_dedicated_loop(cls):
        """Cleanup dedicated event loop (optional, mainly for testing or graceful shutdown)"""
        if cls._dedicated_loop and not cls._dedicated_loop.is_closed():
            cls._dedicated_loop.call_soon_threadsafe(cls._dedicated_loop.stop)
            if cls._dedicated_thread and cls._dedicated_thread.is_alive():
                cls._dedicated_thread.join(timeout=5.0)

    def get_turn_type(self) -> TurnType:
        return TurnType.CONVERSATION

    def can_handle(self, user_input: str) -> bool:
        """Handle non-command input"""
        return not self.slash_commands.is_command(user_input)

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

        stream_iterator = None
        try:
            stream_iterator = result.stream_events()
            async for event in stream_iterator:
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
                        self._live_incremental_response("", self.response_content, final=True)
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

        except Exception as e:
            # Clean up MarkdownStream if it exists on stream error
            if hasattr(self, 'mdstream') and self.mdstream is not None:
                try:
                    if hasattr(self, 'response_content') and self.response_content:
                        self.mdstream.update(self.response_content, final=True)
                    self.mdstream = None
                except Exception:
                    pass  # Ignore cleanup errors
            raise e

    def _live_incremental_response(self, delta_text: str, response_content: str, final: bool = False):
        if self.mdstream:
            response_content = self.replace_reasoning_tag(response_content, DEFAULT_REASONING_TAG)
            self.mdstream.update(response_content, final)
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
            import asyncio

            # Define async execution logic
            async def _async_execute():
                # Run agent for conversation
                result: RunResultStreaming = await SiadaRunner.run_agent(
                    agent_name=self.config.agent_name,
                    user_input=turn_input.use_input,
                    workspace=self.config.workspace,
                    session=self.session,
                    stream=True,
                )

                await self.output_stream_content(result)
                return result

            # Use dedicated event loop to execute async tasks (reuse loop, maintain connection pool advantages)
            self._ensure_dedicated_loop()
            
            # Execute async task in dedicated loop
            future = asyncio.run_coroutine_threadsafe(_async_execute(), self._dedicated_loop)
            result = future.result()

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
            
            # Clean up MarkdownStream if it exists
            if hasattr(self, 'mdstream') and self.mdstream is not None:
                try:
                    # Force final output of any accumulated content
                    if hasattr(self, 'response_content') and self.response_content:
                        self.mdstream.update(self.response_content, final=True)
                    self.mdstream = None
                except Exception:
                    pass  # Ignore cleanup errors
            
            return self.handle_error(e)
        

    def replace_reasoning_tag(self, text, tag_name):
        """
        Replace opening and closing reasoning tags with standard formatting.
        Ensures exactly one blank line before START and END markers.

        Args:
            text (str): The text containing the tags
            tag_name (str): The name of the tag to replace

        Returns:
            str: Text with reasoning tags replaced with standard format
        """
        if not text:
            return text

        # Replace opening tag with thinking format
        text = re.sub(f"\\s*<{tag_name}>\\s*", "\n```thinking\n", text)

        # Replace closing tag with thinking format
        text = re.sub(f"\\s*</{tag_name}>\\s*", "\n```\n\n", text)

        return text


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
