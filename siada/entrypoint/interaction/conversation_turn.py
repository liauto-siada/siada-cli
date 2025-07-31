import re
import asyncio
import threading
from typing import Optional, Dict, Any

from agents import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    RunResultStreaming,
    ToolCallOutputItem,
)
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
)

import siada.io.components.mdstream
from siada.entrypoint.interaction.base_turn import RunTurn
from siada.entrypoint.interaction.turn_models import TurnInput, TurnOutput, TurnType
from siada.foundation.logging import logger
from siada.services.siada_runner import SiadaRunner
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory

# Standard tag identifier
REASONING_TAG = "thinking-content-" + "7bbeb8e1441453ad999a0bbba8a46d4b"
# Output formatting
REASONING_START = "--------------\n► **THINKING**"
REASONING_END = "------------\n► **ANSWER**"
TOOL_CALL_START = "--------------\n► **TOOL USE**"
DEFAULT_REASONING_TAG = "thinking"


class ConversationTurn(RunTurn):
    """Handles regular AI conversation turns"""

    mdstream: siada.io.components.mdstream.MarkdownRender = None
    tool_calls: Dict[str, Dict[str, Any]] = None
    tool_call_mdstreams: Dict[str, siada.io.components.mdstream.MarkdownRender] = None
    response_content: str = None
    current_active_call_id: Optional[str] = None
    got_content_part: bool = False
    got_reasoning_part: bool = False
    got_tool_result_part: bool = False

    # Class-level dedicated event loop and thread, shared by all instances
    _dedicated_loop = None
    _dedicated_thread = None
    _loop_ready = None

    @classmethod
    def _ensure_dedicated_loop(cls):
        """Ensure dedicated event loop is started"""
        if cls._dedicated_loop is None or cls._dedicated_loop.is_closed():
            try:
                main_loop = asyncio.get_running_loop()
                logger.info(f"📋 Detected main thread event loop: {id(main_loop)}")
            except RuntimeError:
                logger.info("📋 No event loop in main thread")  # Normal case

            cls._loop_ready = threading.Event()

            def run_dedicated_loop():
                """Run event loop in dedicated thread"""
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._dedicated_loop = loop
                cls._loop_ready.set()
                try:
                    loop.run_forever()
                finally:
                    loop.close()
                    cls._dedicated_loop = None

            cls._dedicated_thread = threading.Thread(
                target=run_dedicated_loop,
                daemon=True,
                name="ConversationTurn-AsyncLoop"
            )
            cls._dedicated_thread.start()
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
        stream_iterator = None
        try:
            stream_iterator = result.stream_events()
            async for event in stream_iterator:
                if isinstance(event, RawResponsesStreamEvent):
                    stream_data = event.data
                    if isinstance(stream_data, ResponseCreatedEvent):
                        self.mdstream = (
                            self.config.io.get_assistant_mdstream()
                            if self.config.io.pretty
                            else None
                        )
                        self.response_content = ""
                        self.tool_calls = {}
                        self.tool_call_mdstreams = {}
                        self.got_content_part = False
                        self.got_reasoning_part = False
                        self.current_active_call_id = None
                        self.got_tool_result_part = False
                    elif isinstance(stream_data, ResponseReasoningSummaryPartAddedEvent):
                        continue
                    elif isinstance(stream_data, ResponseReasoningSummaryTextDeltaEvent):
                        if not self.got_reasoning_part and stream_data.delta:
                            self.got_reasoning_part = True
                            delta_text = f"\n{REASONING_START}\n\n{stream_data.delta}"
                            self.response_content += delta_text
                        else:
                            delta_text = stream_data.delta
                            self.response_content += delta_text
                        self._live_incremental_response(delta_text, self.response_content)
                    elif isinstance(stream_data, ResponseContentPartAddedEvent):
                        continue
                    elif isinstance(stream_data, ResponseTextDeltaEvent):
                        if not self.got_content_part and stream_data.delta:
                            self.got_content_part = True
                            delta_text = f"\n\n{REASONING_END}\n\n{stream_data.delta}"
                            self.response_content += delta_text
                        else:
                            delta_text = stream_data.delta
                            self.response_content += delta_text
                        self._live_incremental_response(delta_text, self.response_content)
                    elif isinstance(stream_data, ResponseOutputItemAddedEvent):
                        if isinstance(stream_data.item, ResponseFunctionToolCall):
                            call_id = stream_data.item.id
                            tool_name = stream_data.item.name
                            self.tool_calls[call_id] = {"name": tool_name, "arguments": ""}
                            self.current_active_call_id = call_id
                            self.config.io.print_tool_call(
                                f"{TOOL_CALL_START}\n\nSiada wants to use the tool: {tool_name}"
                            )
                    elif isinstance(stream_data, ResponseFunctionCallArgumentsDeltaEvent):
                        delta = stream_data.delta
                        if self.current_active_call_id:
                            self.tool_calls[self.current_active_call_id]["arguments"] += delta
                    elif isinstance(stream_data, ResponseOutputItemDoneEvent):
                        if isinstance(stream_data.item, ResponseFunctionToolCall):
                            call_id = stream_data.item.id
                            if call_id in self.tool_calls:
                                tool_name = self.tool_calls[call_id]["name"]
                                full_arguments = self.tool_calls[call_id]["arguments"]
                                tool_call_formatter = ToolCallFormatterFactory.get_formatter(tool_name)
                                style, content = tool_call_formatter.format_input(
                                    call_id, tool_name, full_arguments
                                )
                                if style == "markdown":
                                    if call_id not in self.tool_call_mdstreams:
                                        self.tool_call_mdstreams[call_id] = self.config.io.get_assistant_mdstream()
                                    self.tool_call_mdstreams[call_id].update(content, final=True)
                                    del self.tool_call_mdstreams[call_id]
                                else:
                                    self.config.io.print_tool_call(content)
                            if self.current_active_call_id == call_id:
                                self.current_active_call_id = None
                    elif isinstance(stream_data, ResponseCompletedEvent):
                        self._live_incremental_response("", self.response_content, final=True)
                        self.mdstream = None
                        self.response_content = None
                        self.tool_calls = None
                        self.tool_call_mdstreams = None
                        self.got_content_part = False
                        self.got_reasoning_part = False
                        self.current_active_call_id = None
                elif isinstance(event, RunItemStreamEvent):
                    stream_data = event.item
                    if isinstance(stream_data, ToolCallOutputItem):
                        if hasattr(stream_data.raw_item, "call_id"):
                            call_id = stream_data.raw_item.call_id
                            if call_id in self.tool_calls:
                                tool_name = self.tool_calls[call_id]["name"]
                                self.config.io.print_tool_result(
                                    f"Siada has used the tool: {tool_name}"
                                )
                                output = stream_data.output
                                if isinstance(output, FunctionCallResult):
                                    self.config.io.print_tool_result(
                                        output.format_for_display()
                                    )
                                else:
                                    self.config.io.print_tool_result(str(output))
        except Exception as e:
            if hasattr(self, 'mdstream') and self.mdstream is not None:
                try:
                    if hasattr(self, 'response_content') and self.response_content:
                        self.mdstream.update(self.response_content, final=True)
                    self.mdstream = None
                except Exception:
                    pass
            raise e

    def _live_incremental_response(self, delta_text: str, response_content: str, final: bool = False):
        if self.mdstream:
            response_content = self.replace_reasoning_tag(response_content, DEFAULT_REASONING_TAG)
            self.mdstream.update(response_content, final)
        else:
            self.config.io.print_info(delta_text)

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute AI conversation turn"""
        self.input_data = turn_input
        self.start_time = self._get_timestamp()
        try:
            async def _async_execute():
                result: RunResultStreaming = await SiadaRunner.run_agent(
                    agent_name=self.config.agent_name,
                    user_input=turn_input.use_input,
                    workspace=self.config.workspace,
                    session=self.session,
                    stream=True,
                )
                await self.output_stream_content(result)
                return result
            self._ensure_dedicated_loop()
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
            if hasattr(self, 'mdstream') and self.mdstream is not None:
                try:
                    if hasattr(self, 'response_content') and self.response_content:
                        self.mdstream.update(self.response_content, final=True)
                    self.mdstream = None
                except Exception:
                    pass
            return self.handle_error(e)

    def replace_reasoning_tag(self, text, tag_name):
        """Replace opening and closing reasoning tags with standard formatting."""
        if not text:
            return text
        text = re.sub(f"\\s*<{tag_name}>\\s*", "\n```thinking\n", text)
        text = re.sub(f"\\s*</{tag_name}>\\s*", "\n```\n\n", text)
        return text 