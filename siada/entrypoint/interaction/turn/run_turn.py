"""
Run Turn Module

Manages individual interaction turns between user and AI, including command processing
and model conversations. Encapsulates the logic for a single interaction cycle.
"""

import grep_ast
from siada.foundation.logging import logger
import re
import siada.io.components.mdstream
from typing import Optional, Dict, Any, Tuple

from agents import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    RunResultStreaming,
    ToolCallOutputItem,
)

from siada.support.spinner import WaitingSpinner
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory

# Import existing InteractionConfig
from ..config import RunningConfig

# Import models and interface from the same directory
from .models import TurnType, TurnInput, TurnOutput
from .interface import RunTurn
from rich.markdown import Markdown
from rich.text import Text


# Standard tag identifier
REASONING_TAG = "thinking-content-" + "7bbeb8e1441453ad999a0bbba8a46d4b"

SPLIT_TAG = "\n--------------\n"
# Output formatting

REASONING_START = "► **THINKING**"

REASONING_END = "► **ANSWER**"

TOOL_CALL_START = "► **TOOL USE**"


class ConversationTurn(RunTurn):
    """Handles regular AI conversation turns"""

    mdstream: siada.io.components.mdstream.MarkdownRender = None

    def _process_thinking_tags(self, text: str) -> Tuple[str, bool]:
        """
        Process thinking tags and return (processed_text, should_render)
        
        Args:
            text (str): Streaming input text
            
        Returns:
            tuple: (processed_text, should_render)
                - If text ends with incomplete thinking tag, return (previous_safe_text, False)
                - Otherwise remove all thinking tags (preserve content) and return (clean_text, True)
        """
        # Define complete tags
        thinking_start = '<thinking>'
        thinking_end = '</thinking>'

        # Check if text ends with incomplete thinking tag
        def is_partial_tag_at_end(text: str, full_tag: str) -> bool:
            """Check if text ends with incomplete part of specified tag"""
            for i in range(1, len(full_tag)):
                if text.endswith(full_tag[:i]):
                    return True
            return False

        # If text ends with incomplete <thinking> or </thinking> part, pause rendering
        if is_partial_tag_at_end(text, thinking_start) or is_partial_tag_at_end(text, thinking_end):
            # Find the last complete tag position and get safe part
            safe_end = len(text)
            for i in range(len(text) - 1, -1, -1):
                if text[i] == '<':
                    # Check if this position might be start of incomplete thinking tag
                    remaining = text[i:]
                    if thinking_start.startswith(remaining) or thinking_end.startswith(remaining):
                        safe_end = i
                        break

            safe_text = text[:safe_end]
            clean_text = self._remove_thinking_content(safe_text)
            return clean_text, False

        # No incomplete tags, remove all thinking tags
        clean_text = self._remove_thinking_content(text)
        return clean_text, True

    def _remove_thinking_content(self, text: str) -> str:
        """
        Remove thinking tags from text but preserve content inside
        
        Args:
            text (str): Input text
            
        Returns:
            str: Text with thinking tags removed
        """
        # Remove start tag <thinking> and possible whitespace
        text = re.sub(r'<thinking>\s?', '', text)

        # Remove end tag </thinking> and possible surrounding whitespace
        text = re.sub(r'\s?</thinking>', '', text)

        return text
    tool_calls: Dict[str, Dict[str, Any]] = None
    tool_call_mdstreams: Dict[str, siada.io.components.mdstream.MarkdownRender] = None
    response_content: str = None
    current_active_call_id: Optional[str] = None
    got_content_part: bool = False
    got_reasoning_part: bool = False
    got_tool_result_part: bool = False
    got_function_call_part: bool = False

    # Class-level dedicated event loop and thread, shared by all instances
    _dedicated_loop = None
    _dedicated_thread = None
    _loop_ready = None

    def __init__(self, config: RunningConfig, session: Any, slash_commands: Any):
        super().__init__(config, session, slash_commands)
        self.mdargs = dict(
            style=self.config.running_color_settings.split_line_color,
            code_theme=self.config.running_color_settings.code_theme,
            inline_code_lexer="text",
        )

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
                name="ConversationTurn-AsyncLoop",
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
            ResponseOutputItemDoneEvent,
            ResponseContentPartDoneEvent,
        )
        from openai.types.responses.response_input_item_param import FunctionCallOutput

        stream_iterator = None
        try:
            stream_iterator = result.stream_events()
            async for event in stream_iterator:
                if isinstance(event, RawResponsesStreamEvent):
                    self._stop_waiting_spinner()

                    # Handle the raw response stream event
                    stream_data = event.data

                    # Handle different types of stream events
                    if isinstance(stream_data, ResponseCreatedEvent):
                        # Response started
                        self.response_content = ""
                        self.tool_calls = {}
                        self.tool_call_mdstreams = {}
                        self.got_content_part = False
                        self.got_reasoning_part = False
                        self.current_active_call_id = None
                        self.got_tool_result_part = False
                        self.got_function_call_part = False

                    elif isinstance(
                        stream_data, ResponseReasoningSummaryPartAddedEvent
                    ):
                        if self.mdstream is None:
                            self.mdstream = (
                                self.get_response_mdstream()
                                if self.config.io.pretty
                                else None
                            )
                        continue

                    elif isinstance(
                        stream_data, ResponseReasoningSummaryTextDeltaEvent
                    ):
                        if not self.got_reasoning_part and stream_data.delta:
                            self.got_reasoning_part = True
                            self.print_split_line()
                            delta_text = f"\n{REASONING_START}\n\n{stream_data.delta}"
                            self.response_content += delta_text
                        else:
                            delta_text = stream_data.delta
                            self.response_content += delta_text
                        self._live_incremental_response(
                            delta_text, self.response_content
                        )

                    elif isinstance(stream_data, ResponseContentPartAddedEvent):
                        if self.mdstream is None:
                            self.mdstream = (
                                self.get_response_mdstream()
                                if self.config.io.pretty
                                else None
                            )
                        continue

                    elif isinstance(stream_data, ResponseTextDeltaEvent):
                        if not self.got_content_part and stream_data.delta:
                            self.got_content_part = True
                            if not self.got_reasoning_part:
                                self.print_split_line()
                            delta_text = f"\n\n{REASONING_END}\n\n{stream_data.delta}"
                            self.response_content += delta_text
                        else:
                            delta_text = stream_data.delta
                            self.response_content += delta_text
                        self._live_incremental_response(
                            delta_text, self.response_content
                        )

                    elif isinstance(stream_data, ResponseContentPartDoneEvent):
                        if not self.got_function_call_part:
                            # if not got function call part, flush the response content
                            self._live_incremental_response(
                                "\n", self.response_content, final=True
                            )
                            self.mdstream = None

                    elif isinstance(stream_data, ResponseOutputItemAddedEvent):
                        if isinstance(stream_data.item, ResponseFunctionToolCall):
                            # if have got the function call part, must flush the response before the tool call
                            if not self.got_function_call_part:
                                self.got_function_call_part = True
                                # flush the response content
                                self._live_incremental_response(
                                    "\n", self.response_content, final=True
                                )
                                self.mdstream = None

                            call_id = stream_data.item.call_id
                            tool_name = stream_data.item.name
                            self.tool_calls[call_id] = {
                                "name": tool_name,
                                "arguments": "",
                                "arguments_render": "",
                            }

                            tool_call_formatter = ToolCallFormatterFactory.get_formatter(tool_name)

                            if (
                                self.config.io.pretty
                                and tool_call_formatter.supports_streaming()
                            ):
                                self.tool_call_mdstreams[call_id] = (
                                    self.get_response_mdstream()
                                )

                            # process the previous tool call stream, stop the live
                            if (
                                self.current_active_call_id
                                and self.current_active_call_id
                                in self.tool_call_mdstreams
                            ):
                                self.tool_call_mdstreams[
                                    self.current_active_call_id
                                ].update(
                                    tool_call_formatter.format_input(
                                        self.current_active_call_id,
                                        self.tool_calls[self.current_active_call_id]["name"],
                                        self.tool_calls[self.current_active_call_id][
                                            "arguments"
                                        ],
                                    )[0],
                                    final=True,
                                )
                                if self.current_active_call_id in self.tool_call_mdstreams:
                                    del self.tool_call_mdstreams[
                                        self.current_active_call_id
                                    ]

                            self.current_active_call_id = call_id
                            self.print_split_line()
                            self.config.io.print_tool_call(
                                f"{TOOL_CALL_START}\n\nSiada wants to use the tool: {tool_name}\n"
                            )

                    elif isinstance(
                        stream_data, ResponseFunctionCallArgumentsDeltaEvent
                    ):
                        delta = stream_data.delta
                        if self.current_active_call_id:
                            self.tool_calls[self.current_active_call_id][
                                "arguments"
                            ] += delta

                        tool_call_formatter = ToolCallFormatterFactory.get_formatter(
                            self.tool_calls[self.current_active_call_id]["name"]
                        )

                        # if supports streaming, update the tool call mdstream
                        if tool_call_formatter.supports_streaming():
                            content, is_complete = tool_call_formatter.format_input(
                                    self.current_active_call_id,
                                    self.tool_calls[self.current_active_call_id][
                                        "name"
                                    ],
                                    self.tool_calls[self.current_active_call_id][
                                        "arguments"
                                    ],
                                )

                            # compute the content_delta
                            arguments_delta = content[len(self.tool_calls[self.current_active_call_id]["arguments_render"]):]
                            self.tool_calls[self.current_active_call_id]["arguments_render"] = content

                            if self.current_active_call_id in self.tool_call_mdstreams:
                                self.tool_call_mdstreams[
                                    self.current_active_call_id
                                ].update(content, final=False)
                            else:
                                self.config.io.console.print(
                                    arguments_delta, sep="", end=""
                                )

                    elif isinstance(stream_data, ResponseOutputItemDoneEvent):
                        if isinstance(stream_data.item, ResponseFunctionToolCall):
                            call_id = stream_data.item.call_id
                            if call_id in self.tool_calls:
                                tool_name = self.tool_calls[call_id]["name"]
                                full_arguments = self.tool_calls[call_id]["arguments"]

                                tool_call_formatter = (
                                    ToolCallFormatterFactory.get_formatter(tool_name)
                                )
                                content, _ = tool_call_formatter.format_input(
                                    call_id, tool_name, full_arguments
                                )
                                style = tool_call_formatter.get_style()
                                # if not streaming, only create the mdstream and update the final content
                                if tool_call_formatter.supports_streaming():
                                    # process the last tool call stream, stop the live
                                    if call_id in self.tool_call_mdstreams:
                                        self.tool_call_mdstreams[call_id].update(
                                            content,
                                            final=True,
                                        )
                                    if call_id in self.tool_call_mdstreams:
                                        del self.tool_call_mdstreams[call_id]
                                else:
                                    if style == "markdown" and self.config.io.pretty:
                                        self.tool_call_mdstreams[call_id] = (
                                            self.get_response_mdstream()
                                        )
                                        self.tool_call_mdstreams[call_id].update(
                                            content, final=True
                                        )
                                        if call_id in self.tool_call_mdstreams:
                                            del self.tool_call_mdstreams[call_id]
                                    else:
                                        self.config.io.print_tool_call(content)

                    elif isinstance(stream_data, ResponseCompletedEvent):
                        pass

                elif isinstance(event, RunItemStreamEvent):
                    stream_data = event.item
                    if isinstance(stream_data, ToolCallOutputItem):
                        call_id = stream_data.raw_item.get("call_id", None)
                        if call_id:
                            if call_id in self.tool_calls:
                                tool_name = self.tool_calls[call_id]["name"]
                                self.print_split_line()
                                output = stream_data.output
                                if isinstance(output, FunctionCallResult):
                                    self.config.io.print_tool_result(
                                        output.format_for_display()
                                    )
                                else:
                                    self.config.io.print_tool_result(str(output))

        except Exception as e:
            # Clean up MarkdownStream if it exists on stream error
            if hasattr(self, "mdstream") and self.mdstream is not None:
                try:
                    self.mdstream.close()  # Direct close, no need to render on error
                    self.mdstream = None
                except Exception:
                    pass  # Ignore cleanup errors

            # Clean up tool call streams on error
            if hasattr(self, "tool_call_mdstreams") and self.tool_call_mdstreams:
                try:
                    for stream in self.tool_call_mdstreams.values():
                        if stream:
                            try:
                                stream.close()  # Direct close, no need to render on error
                            except Exception:
                                pass  # Ignore individual stream cleanup errors
                    self.tool_call_mdstreams.clear()
                except Exception:
                    pass  # Ignore cleanup errors
            raise e

    def _live_incremental_response(
        self,
        delta_text: str,
        response_content: str,
        final: bool = False,
    ):
        if self.mdstream:
            # Process thinking tags
            processed_content, should_render = self._process_thinking_tags(response_content)

            if should_render or final:
                self.mdstream.update(processed_content if processed_content else "", final)
            # If should_render is False, pause mdstream.update temporarily
        else:
            if not self.config.io.pretty:
                # For non-pretty mode, also need to process thinking tags
                processed_delta, should_render = self._process_thinking_tags(delta_text)
                if should_render or final:
                    self.config.io.console.print(processed_delta, sep="", end="")

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute AI conversation turn

        Args:
            turn_input: User input for conversation

        Returns:
            TurnOutput: AI response
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()
        self.spinner = None
        if self.config.io.pretty:
            self.spinner = WaitingSpinner(f"Waiting for Agent {self.config.agent_name}...")
            self.spinner.start()

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
            future = asyncio.run_coroutine_threadsafe(
                _async_execute(), self._dedicated_loop
            )
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
            return self.handle_error(e)

    def print_split_line(self):
        if self.config.io.pretty:
            self.config.io.rule(color=self.config.running_color_settings.split_line_color)
        else:
            self.config.io.console.print(SPLIT_TAG, end="")

    def get_response_mdstream(self):
        mdargs = dict(
            style=self.config.running_color_settings.assistant_output_color,
            code_theme=self.config.running_color_settings.code_theme,
            inline_code_lexer="text",
        )
        mdStream = siada.io.components.mdstream.MarkdownRender(mdargs=mdargs)
        return mdStream
    
    def _stop_waiting_spinner(self):
        """Stop and clear the waiting spinner if it is running."""
        spinner = getattr(self, "spinner", None)
        if spinner:
            try:
                spinner.stop()
            finally:
                self.spinner = None


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
        config: RunningConfig, session: Any, slash_commands: Any, user_input: str
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
