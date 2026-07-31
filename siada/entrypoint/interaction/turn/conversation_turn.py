"""
Conversation Turn Module

Handles AI conversation turns including streaming responses and tool calls.
"""

from siada.foundation.logging import logger
import re
import threading
import time
import siada.io.components.mdstream
from typing import List, Optional, Dict, Any, Tuple

from agents import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    RunResultStreaming,
    ToolCallOutputItem,
    ToolOutputImage,
    ToolOutputText
)
from agents.exceptions import (
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)

from siada.io.stream_utils import render_tool_call_output
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
# BrowserOperateResult is lazy-imported inside _display_browser_operate_result()
# to avoid pulling in gymnasium/numpy at module load time (very slow on Windows).


def _build_multimodal_input(text: str, image_paths: list) -> list:
    """Build a multimodal TResponseInputItem list from text + image file paths.


    Returns a list with a single user message containing text and image content
    in the format expected by the OpenAI Agents SDK.
    """
    import base64
    import mimetypes
    import os

    content = []
    if text:
        content.append({"type": "input_text", "text": text})

    for path in image_paths:
        try:
            if not os.path.exists(path):
                logger.warning(f"[multimodal] Image path not found, skipping: {path}")
                continue
            mime_type, _ = mimetypes.guess_type(path)
            if not mime_type:
                mime_type = "image/png"
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{data}",
            })
            logger.info(f"[multimodal] Attached image: {path} ({mime_type})")
        except Exception as exc:
            logger.warning(f"[multimodal] Failed to read image {path}: {exc}")

    return [{"role": "user", "content": content}]

# Import existing InteractionConfig
from ..running_config import RunningConfig

# Import models and interface from the same directory
from .models import TurnType, TurnInput, TurnOutput
from .interface import RunTurn, ImageNotSupportedError


# Standard tag identifier
REASONING_TAG = "thinking-content-" + "7bbeb8e1441453ad999a0bbba8a46d4b"

SPLIT_TAG = "\n--------------\n"
# Output formatting

REASONING_START = "THINKING" # ► ▶ **THINKING**

REASONING_END = "▶ **ANSWER**"

TOOL_CALL_START = "▶ **TOOL USE**"

# Structured message markers for siada-cli-ui integration
# Format: __SIADA_MSG_START__:type:id
# Format: __SIADA_MSG_END__:type:id
MESSAGE_START_MARKER = "__SIADA_MSG_START__"
MESSAGE_END_MARKER = "__SIADA_MSG_END__"


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
        thinking_start = "<thinking>"
        thinking_end = "</thinking>"

        # Check if text ends with incomplete thinking tag
        def is_partial_tag_at_end(text: str, full_tag: str) -> bool:
            """Check if text ends with incomplete part of specified tag"""
            for i in range(1, len(full_tag)):
                if text.endswith(full_tag[:i]):
                    return True
            return False

        # If text ends with incomplete <thinking> or </thinking> part, pause rendering
        if is_partial_tag_at_end(text, thinking_start) or is_partial_tag_at_end(
            text, thinking_end
        ):
            # Find the last complete tag position and get safe part
            safe_end = len(text)
            for i in range(len(text) - 1, -1, -1):
                if text[i] == "<":
                    # Check if this position might be start of incomplete thinking tag
                    remaining = text[i:]
                    if thinking_start.startswith(remaining) or thinking_end.startswith(
                        remaining
                    ):
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
        text = re.sub(r"<thinking>\s?", "", text)

        # Remove end tag </thinking> and possible surrounding whitespace
        text = re.sub(r"\s?</thinking>", "", text)

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
    _pending_memory_task: "asyncio.Task | None" = None  # Background memory save from previous turn

    def __init__(self, config: RunningConfig, session: Any, slash_commands: Any):
        super().__init__(config, session, slash_commands)
        self.mdargs = dict(
            style=self.config.running_color_settings.split_line_color,
            code_theme=self.config.running_color_settings.code_theme,
            inline_code_lexer="text",
        )
        # Instance variable to store current running result for cancellation
        self.current_result: Optional[RunResultStreaming] = None
        # Thread synchronization events for proper cleanup handling
        self._cleanup_done = threading.Event()
        self._result_ready = threading.Event()
        # Message tracking
        self._message_counter = 0
        self._current_message_id = None
        self._stream_start_id = None  # Track the start ID of current stream
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID"""
        self._message_counter += 1
        return f"msg_{self._message_counter}_{int(time.time() * 1000)}"
    
    def _emit_message_start(self, msg_type: str):
        """Emit message start marker
        
        Args:
            msg_type: Type of message (thinking, answer, tool_call, tool_result)
        """
        # Generate message ID
        self._current_message_id = self._generate_message_id()
        
        # Set stream start ID (first message in the stream)
        if self._stream_start_id is None:
            self._stream_start_id = self._current_message_id
        
        if not self.config.io.acp_enabled:
            # Non-ACP mode: print text marker
            marker = f"{MESSAGE_START_MARKER}:{msg_type}:{self._current_message_id}"
            # self.config.io.console.print(marker)
            logger.debug(f"Emitted message start: {marker}")
        else:
            # ACP mode: send lifecycle event
            self._send_lifecycle_event({
                "type": "message_start",
                "message_type": msg_type,
                "message_id": self._current_message_id,
                "timestamp": time.time()
            })
            logger.debug(f"Sent lifecycle message_start event: {msg_type}")
    
    def _emit_message_end(self, msg_type: str):
        """Emit message end marker
        
        Args:
            msg_type: Type of message (thinking, answer, tool_call, tool_result)
        """
        if not self._current_message_id:
            return
        
        if not self.config.io.acp_enabled:
            # Non-ACP mode: print text marker
            marker = f"{MESSAGE_END_MARKER}:{msg_type}:{self._current_message_id}"
            # self.config.io.console.print(marker)
            logger.debug(f"Emitted message end: {marker}")
        else:
            # ACP mode: send lifecycle event
            self._send_lifecycle_event({
                "type": "message_end",
                "message_type": msg_type,
                "message_id": self._current_message_id,
                "timestamp": time.time()
            })
            logger.debug(f"Sent lifecycle message_end event: {msg_type}")
        
        self._current_message_id = None

    @classmethod
    def _ensure_dedicated_loop(cls):
        """Ensure dedicated event loop is started"""
        if cls._dedicated_loop is None or cls._dedicated_loop.is_closed():
            start_time = time.time()
            logger.debug("[ConversationTurn] Starting dedicated event loop initialization")
            
            import threading
            import asyncio

            # Detect if main thread has a running event loop (prompt_toolkit might be using it)
            try:
                main_loop = asyncio.get_running_loop()
                logger.debug(f"Detected main thread event loop: {id(main_loop)}")
            except RuntimeError:
                pass  # Normal case - no event loop in main thread

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
            
            elapsed_time = time.time() - start_time
            logger.debug(f"[ConversationTurn] Dedicated event loop initialized (took {elapsed_time:.2f}s)")

    @classmethod
    def _cleanup_dedicated_loop(cls):
        """Cleanup dedicated event loop (optional, mainly for testing or graceful shutdown)"""
        if cls._dedicated_loop and not cls._dedicated_loop.is_closed():
            cls._dedicated_loop.call_soon_threadsafe(cls._dedicated_loop.stop)
            if cls._dedicated_thread and cls._dedicated_thread.is_alive():
                cls._dedicated_thread.join(timeout=5.0)

    @classmethod
    def _force_abandon_dedicated_loop(cls):
        """Force abandon the current dedicated event loop and thread.
        
        Called when Ctrl+C cleanup times out, indicating the event loop thread
        is blocked by a synchronous operation (e.g., run_cmd executing a shell
        command via subprocess.read(1) which blocks indefinitely).
        
        We set class variables to None so _ensure_dedicated_loop() will create
        a fresh loop+thread on the next turn. The old thread is a daemon thread
        and will eventually terminate when the blocking operation completes or
        when the main process exits.
        """
        old_loop = cls._dedicated_loop
        old_thread = cls._dedicated_thread
        
        # Abandon references - next _ensure_dedicated_loop() will create new ones
        cls._dedicated_loop = None
        cls._dedicated_thread = None
        cls._loop_ready = None
        
        logger.warning(
            f"[ConversationTurn] Force abandoned dedicated loop "
            f"(loop={id(old_loop) if old_loop else None}, "
            f"thread={old_thread.name if old_thread else None}). "
            f"A new loop will be created for the next turn."
        )
        
        # Best-effort: try to stop the old loop (may not work if thread is blocked)
        if old_loop and not old_loop.is_closed():
            try:
                old_loop.call_soon_threadsafe(old_loop.stop)
            except RuntimeError:
                pass  # Loop might already be closed or thread dead

    def get_turn_type(self) -> TurnType:
        return TurnType.CONVERSATION

    def can_handle(self, user_input: str | List[Any]) -> bool:
        """Handle non-command input"""
        if isinstance(user_input, list):
            return True
        return not self.slash_commands.is_command(user_input)

    # ============================================================================
    # Lifecycle Event Methods (Agent Lifecycle Integration)
    # ============================================================================
    
    def _send_lifecycle_event(self, event_data: dict):
        """
        Send lifecycle event to ACP
        
        Args:
            event_data: Event data dictionary
        """
        # Only send in ACP mode
        if not self.config.io.acp_enabled:
            logger.debug(f"🔍 [DEBUG] Skipping lifecycle event - ACP not enabled")
            return
        
        if not hasattr(self.config.io, 'acp_adapter') or not self.config.io.acp_adapter:
            logger.warn(f"⚠️ [DEBUG] Skipping lifecycle event - no acp_adapter")
            return
        
        try:
            # 🔍 Debug: Log before building message
            # logger.info(f"🔍 [DEBUG] Building lifecycle event message", extra={
            #     "event_type": event_data.get("type"),
            #     "event_data": event_data,
            # })
            
            # Use acp_adapter's builder to create custom message
            message = self.config.io.acp_adapter.builder.build_session_update(
                reason="lifecycle_event",
                metadata=event_data
            )
            
            # logger.info(f"🔍 [DEBUG] Lifecycle message built", extra={
            #     "message_id": message.id if hasattr(message, 'id') else 'unknown',
            #     "message_method": message.method if hasattr(message, 'method') else 'unknown',
            # })
            
            # Send message
            adapter = self.config.io.acp_adapter
            if adapter.transport and adapter.transport.is_connected:
                # Use send_sync() directly, no event loop needed
                # transport.send() internally calls send_sync(), no need to wrap in async
                adapter.transport.send_sync(message)
                # logger.info(f"✅ [DEBUG] Lifecycle message sent successfully")
            else:
                logger.warn(f"[DEBUG] Transport not available or not connected", extra={
                    "has_transport": bool(adapter.transport),
                    "is_connected": adapter.transport.is_connected if adapter.transport else False,
                })
                
        except Exception as e:
            # Silent failure, don't break conversation flow
            logger.error(f" [DEBUG] Failed to send lifecycle event: {e}", exc_info=True)
    
    # ============================================================================
    # End of Lifecycle Event Methods
    # ============================================================================

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
                            # Emit message start marker for thinking
                            self._emit_message_start("thinking")
                            # self.print_split_line()
                            delta_text = f"\n{REASONING_START}: {stream_data.delta}"
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
                            # End thinking message if it was started
                            if self.got_reasoning_part:
                                self._emit_message_end("thinking")
                            # Start answer message
                            self._emit_message_start("answer")
                            # if not self.got_reasoning_part:
                            #     self.print_split_line()
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
                            # Mark stream_end=True to indicate this is the last chunk of the answer stream
                            self._live_incremental_response(
                                "\n", self.response_content, final=True, stream_end=True
                            )
                            self.mdstream = None
                            # End answer message
                            if self.got_content_part:
                                self._emit_message_end("answer")
                            # Reset stream_start_id after stream ends
                            self._stream_start_id = None

                    elif isinstance(stream_data, ResponseOutputItemAddedEvent):
                        if isinstance(stream_data.item, ResponseFunctionToolCall):
                            # Flush answer content before tool call only if not already flushed.
                            # ResponseContentPartDoneEvent fires before this event and sets
                            # mdstream=None; if it already flushed, skip to avoid double output.
                            if not self.got_function_call_part:
                                self.got_function_call_part = True
                                if self.mdstream is not None:
                                    # flush the response content
                                    self._live_incremental_response(
                                        "\n", self.response_content, final=True
                                    )
                                    self.mdstream = None
                                    # End answer message if it was started
                                    if self.got_content_part:
                                        self._emit_message_end("answer")

                            call_id = stream_data.item.call_id
                            tool_name = stream_data.item.name
                            self.tool_calls[call_id] = {
                                "name": tool_name,
                                "arguments": "",
                                "arguments_render": "",
                            }

                            tool_call_formatter = (
                                ToolCallFormatterFactory.get_formatter(tool_name)
                            )

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
                                        self.tool_calls[self.current_active_call_id][
                                            "name"
                                        ],
                                        self.tool_calls[self.current_active_call_id][
                                            "arguments"
                                        ],
                                    )[0],
                                    final=True,
                                )
                                if (
                                    self.current_active_call_id
                                    in self.tool_call_mdstreams
                                ):
                                    del self.tool_call_mdstreams[
                                        self.current_active_call_id
                                    ]

                            self.current_active_call_id = call_id
                            # self.print_split_line()
                            
                            # Start tool_call message
                            self._emit_message_start("tool_call")
                            
                            # Stage 1: Print tool name (use append=False to avoid accumulating the header)
                            # self.config.io.print_tool_call_all_stages(
                            #     f"Siada wants to use the tool: {tool_name}.\n",
                            #     final=False,
                            #     append=True
                            # )
                            
                            # Original method (commented out for reference)
                            # self.config.io.print_tool_call(
                            #     f"{TOOL_CALL_START}\n\nSiada wants to use the tool: {tool_name}\n"
                            # )

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
                        # if tool_call_formatter.supports_streaming():
                        #     content, is_complete = tool_call_formatter.format_input(
                        #         self.current_active_call_id,
                        #         self.tool_calls[self.current_active_call_id]["name"],
                        #         self.tool_calls[self.current_active_call_id][
                        #             "arguments"
                        #         ],
                        #     )

                        #     # compute the content_delta
                        #     arguments_delta = content[
                        #         len(
                        #             self.tool_calls[self.current_active_call_id][
                        #                 "arguments_render"
                        #             ]
                        #         ) :
                        #     ]
                        #     self.tool_calls[self.current_active_call_id][
                        #         "arguments_render"
                        #     ] = content

                        #     if self.current_active_call_id in self.tool_call_mdstreams:
                        #         self.tool_call_mdstreams[
                        #             self.current_active_call_id
                        #         ].update(content, final=False)
                        #     else:
                        #         self.config.io.console.print(
                        #             arguments_delta, sep="", end=""
                        #         )

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
                                
                                # Stage 2: Print tool description/parameters
                                self.config.io.advance_tool_call_stage()
                                self.config.io.print_tool_call_all_stages(
                                    content,
                                    final=True
                                )
                                
                                # End tool_call message
                                self._emit_message_end("tool_call")
                                
                                # Original streaming/non-streaming handling (commented out)
                                # if not streaming, only create the mdstream and update the final content
                                # if tool_call_formatter.supports_streaming():
                                #     # process the last tool call stream, stop the live
                                #     if call_id in self.tool_call_mdstreams:
                                #         self.tool_call_mdstreams[call_id].update(
                                #             content,
                                #             final=True,
                                #         )
                                #     if call_id in self.tool_call_mdstreams:
                                #         del self.tool_call_mdstreams[call_id]
                                # else:
                                #     if style == "markdown" and self.config.io.pretty:
                                #         self.tool_call_mdstreams[call_id] = (
                                #             self.get_response_mdstream()
                                #         )
                                #         self.tool_call_mdstreams[call_id].update(
                                #             content, final=True
                                #         )
                                #         if call_id in self.tool_call_mdstreams:
                                #             del self.tool_call_mdstreams[call_id]
                                #     else:
                                #         self.config.io.print_tool_call(content)

                    elif isinstance(stream_data, ResponseCompletedEvent):
                        # Stage 3: Close the Live+Panel display without adding token info
                        usage = stream_data.response.usage if hasattr(stream_data, 'response') and stream_data.response else None
                        
                        # Close the Live+Panel display (don't add token info to panel)
                        # if hasattr(self.config.io, '_tool_call_stages') and self.config.io._tool_call_stages:
                        #     # Just close the panel without adding token info
                        #     self.config.io.print_tool_call_all_stages("", final=True, append=False)
                        
                        # Print context usage using original method (outside the panel)
                        self._print_context_usage(usage=usage)

                elif isinstance(event, RunItemStreamEvent):
                    stream_data = event.item
                    if isinstance(stream_data, ToolCallOutputItem):
                        call_id = stream_data.raw_item.get("call_id", None)
                        if call_id:
                            if call_id in self.tool_calls:
                                tool_name = self.tool_calls[call_id]["name"]
                                # self.print_split_line()
                                
                                # Start tool_result message
                                self._emit_message_start("tool_result")
                                
                                output = stream_data.output
                                if isinstance(output, list) and tool_name == "browser_operate":
                                    # Special handling for browser_operate to show concise UI display
                                    self._display_browser_operate_result(output)
                                else:
                                    render_tool_call_output(self.config.io, output, tool_name)
                                self._emit_message_end("tool_result")
        finally:
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

    def _live_incremental_response(
        self,
        delta_text: str,
        response_content: str,
        final: bool = False,
        stream_end: bool = False,
    ):
        if self.config.io.acp_enabled and self.config.io.acp_adapter:
            if delta_text:
                self._send_lifecycle_event({
                    "type": "content_delta",
                    "delta": delta_text,
                    "is_final": final,
                    "stream_end": stream_end,
                    "stream_start_id": self._stream_start_id or "", 
                    "timestamp": time.time()
                })
                            
            if final:
                # Send complete response via ACP with stream_end flag.
                # Thinking content was already streamed via content_delta lifecycle events;
                # only send the answer portion to avoid rendering it twice.
                processed_content, _ = self._process_thinking_tags(response_content)
                answer_content = processed_content or response_content
                if REASONING_END in answer_content:
                    answer_content = answer_content.split(REASONING_END, 1)[1].lstrip()
                self.config.io.assistant_output(
                    answer_content,
                    stream_end=stream_end,
                    stream_start_id=self._stream_start_id
                )
            # For non-final chunks, do nothing more (accumulate in response_content)
            return
        
        # Text mode: streaming output
        if self.mdstream:
            # Process thinking tags
            processed_content, should_render = self._process_thinking_tags(
                response_content
            )

            if should_render or final:
                content_to_update = processed_content if processed_content else ""
                # When final is True, ensure content ends with newline
                if final and content_to_update and not content_to_update.endswith('\n'):
                    content_to_update += '\n'
                self.mdstream.update(content_to_update, final)
            # If should_render is False, pause mdstream.update temporarily
        else:
            if not self.config.io.pretty:
                # For non-pretty mode, also need to process thinking tags
                processed_delta, should_render = self._process_thinking_tags(delta_text)
                if should_render or final:
                    self.config.io.console.print(processed_delta, sep="", end="")

    # ── Image-support guard ───────────────────────────────────────────

    def _resolve_image_input(
        self, user_input: str, pending_images: list
    ) -> "str | list":
        """Resolve user input with pending image paths, applying image-support guard.

        When the bound model cannot process images:
        - Image-only messages (no text) raise ImageNotSupportedError after
          printing an error to the frontend.
        - Text+image messages have their images stripped; returns the text only.

        When the model supports images, builds a multimodal input list.

        Args:
            user_input: The raw text input from the user.
            pending_images: List of image file paths from the IO layer.

        Returns:
            - The original user_input (str) if images were stripped.
            - A multimodal input list if images were attached.

        Raises:
            ImageNotSupportedError: if the model cannot process images and
                the message has no meaningful text.
        """
        io = getattr(self.config, "io", None)
        io._pending_image_paths = None  # always clear the pending slot

        supports_images = getattr(self.config.llm_config, "supports_images", True)
        if not supports_images:
            # The frontend sends placeholder text like "[Image #1]" when
            # the user pastes only images. Strip these placeholders and
            # check if any real text remains.
            import re
            stripped = re.sub(
                r"\[Image\s*#\d+\]", "", user_input
            ).strip()
            if not stripped:
                logger.info(
                    "[ConversationTurn] model does not support images and "
                    "message has no text content; rejecting image-only input"
                )
                raise ImageNotSupportedError(
                    "model does not support images and message has no text"
                )
            # Has text — strip images, keep text only
            logger.info(
                "[ConversationTurn] model does not support images; "
                "stripped %d image(s), proceeding with text only",
                len(pending_images),
            )
            return user_input

        return _build_multimodal_input(user_input, pending_images)

    # ── Turn execution ────────────────────────────────────────────────

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute AI conversation turn

        Args:
            turn_input: User input for conversation

        Returns:
            TurnOutput: AI response
        """
        _exec_start = time.perf_counter()
        logger.debug(f"[PERF][turn] execute() start")
        self.input_data = turn_input
        self.start_time = self._get_timestamp()
        
        # Initialize spinner and inject into session for external access
        # if self.config.io.pretty:
        #     spinner = WaitingSpinner(
        #         f"Waiting for Agent {self.config.agent_name}...", text_color="#79B8FF"
        #     )
        #     # Inject spinner into session state for external access (e.g., stop from outside)
        #     self.session.state.spinner = spinner

        # Reset event flags at the beginning of each execution
        self._cleanup_done.clear()
        self._result_ready.clear()

        try:
            # Import here to avoid circular imports
            from siada.services.siada_runner import SiadaRunner
            import asyncio

            # Define async execution logic
            async def _async_execute():
                try:
                    # Await any pending memory save from the previous turn to ensure
                    # data consistency before starting a new turn.
                    # Drain previous turn's best-effort memory save task. Key design
                    # points (each learned the hard way):
                    #
                    # 1) NEVER `await` a task that may be bound to a different event
                    #    loop. If the dedicated loop was abandoned/recreated between
                    #    turns (see _force_abandon_dedicated_loop), the old task is
                    #    still attached to the dead loop; awaiting it from the new
                    #    loop raises RuntimeError/CancelledError that propagates all
                    #    the way up to the user's error box.
                    # 2) The memory save is best-effort; the new turn should never
                    #    block on it. If it's not done yet, just detach and move on.
                    # 3) CancelledError inherits from BaseException (Py3.8+), so
                    #    `except Exception` cannot catch it — we explicitly handle it.
                    pending = ConversationTurn._pending_memory_task
                    if pending is not None:
                        ConversationTurn._pending_memory_task = None
                        try:
                            current_loop = asyncio.get_running_loop()
                            task_loop = getattr(pending, "_loop", None)
                            same_loop = (task_loop is None) or (task_loop is current_loop)
                            logger.info(
                                "[ConversationTurn] pending_memory_task: done=%s cancelled=%s same_loop=%s",
                                pending.done(), pending.cancelled(), same_loop,
                            )

                            if not same_loop:
                                # Cross-loop: never await. Just inspect completion state.
                                if pending.done():
                                    exc = pending.exception() if not pending.cancelled() else None
                                    if exc is not None:
                                        logger.info(
                                            f"[ConversationTurn] Previous memory task (cross-loop) failed: "
                                            f"{type(exc).__name__}: {exc}"
                                        )
                                else:
                                    logger.info(
                                        "[ConversationTurn] Previous memory task (cross-loop) still pending — detaching"
                                    )
                            elif pending.done():
                                if not pending.cancelled():
                                    exc = pending.exception()
                                    if exc is not None:
                                        logger.info(
                                            f"[ConversationTurn] Previous memory task failed: "
                                            f"{type(exc).__name__}: {exc}"
                                        )
                            else:
                                # Same loop + still pending → safe to await briefly.
                                #
                                # Timeout sizing: the first-ever memory save calls the
                                # slug-generation LLM which usually takes 3–8s, while
                                # subsequent saves are pure IO (<0.5s). 15s comfortably
                                # covers the slow first turn without ever blocking normal
                                # turns, and asyncio.shield() ensures the task itself is
                                # NOT cancelled when we time out — it keeps running in
                                # the background so memory stays consistent.
                                try:
                                    await asyncio.wait_for(
                                        asyncio.shield(pending), timeout=15.0
                                    )
                                except asyncio.TimeoutError:
                                    logger.info(
                                        "[ConversationTurn] Previous memory task did not finish in 15s — "
                                        "leaving it running in the background and proceeding"
                                    )
                                except asyncio.CancelledError as e:
                                    logger.info(
                                        f"[ConversationTurn] Previous memory task was cancelled (ignored): {e}"
                                    )
                                except Exception as e:
                                    logger.info(
                                        f"[ConversationTurn] Previous memory task failed (ignored): {e}"
                                    )
                        except BaseException as e:
                            # Guard against anything unexpected (e.g. no running loop).
                            # Must NOT let this drain block the new turn.
                            logger.warning(
                                f"[ConversationTurn] Error while draining previous memory task "
                                f"(ignored): {type(e).__name__}: {e}"
                            )

                    user_input = turn_input.use_input

                    # If there are pending image paths from the IO layer, build
                    # a multimodal input (with image-support guard).
                    io = getattr(self.config, "io", None)
                    pending_images = getattr(io, "_pending_image_paths", None)
                    if pending_images and isinstance(user_input, str):
                        user_input = self._resolve_image_input(
                            user_input, pending_images
                        )

                    # Run agent for conversation
                    _run_start = time.perf_counter()
                    logger.debug(f"[PERF][turn] SiadaRunner.run_agent start")
                    result: RunResultStreaming = await SiadaRunner.run_agent(
                        agent_name=self.config.agent_name,
                        user_input=user_input,
                        workspace=self.config.workspace,
                        session=self.session,
                        stream=True,
                    )
                    logger.debug(f"[PERF][turn] SiadaRunner.run_agent returned | +{(time.perf_counter()-_run_start)*1000:.0f}ms")

                    # Store result immediately for potential cancellation
                    self.current_result = result
                    # Set result ready flag to ensure memory visibility
                    self._result_ready.set()

                    _stream_start = time.perf_counter()
                    logger.debug(f"[PERF][turn] output_stream_content start")
                    try:
                        await self.output_stream_content(result)
                    except (
                        ToolInputGuardrailTripwireTriggered,
                        ToolOutputGuardrailTripwireTriggered,
                    ) as hook_exc:
                        stop_reason = (
                            (hook_exc.output.output_info or "")
                            if hook_exc.output.output_info
                            else "Hook stopped this turn."
                        )
                        logger.info(f"[ConversationTurn] Hook tripwire triggered: {stop_reason}")
                        self.config.io.print_warning(f"[Hook] {stop_reason}")
                        return None
                    logger.debug(f"[PERF][turn] output_stream_content done | +{(time.perf_counter()-_stream_start)*1000:.0f}ms")

                    # Show system notification on task completion (non-blocking)
                    # Only notify if enabled and the agent ran for a while.
                    #
                    # While a /goal task is still active, this per-turn round is
                    # just one intermediate step in the verifier's retry loop
                    # (see siada.services.goal.turn_hooks.maybe_run_goal_verifier)
                    # -- not the real end of the task. So this generic "waiting
                    # for input" notification must be suppressed here; the goal
                    # verifier fires its own completion notification only once
                    # the goal is actually achieved (or blocked).
                    try:
                        if getattr(self.config, 'enable_notification', True):
                            elapsed = time.perf_counter() - _exec_start
                            if elapsed > 60 and not self._has_active_goal():
                                from siada.notifications import show_completion_notification
                                # Reuse the same title shown in the terminal tab (see
                                # Controller._send_session_title_async) as the notification
                                # title so the user can tell which window just finished.
                                session_title = self.session.state.session_title
                                show_completion_notification(
                                    title="Siada 已完成任务",
                                    message=session_title or "Siada"
                                )
                    except Exception:
                        pass


                    # Fire memory save as a background task (non-blocking).
                    # This allows _async_execute to return immediately so the
                    # finally block can send stop:animation without waiting for
                    # memory save (which can take ~2s on first save due to slug LLM call).
                    # The task will be awaited at the start of the next turn.
                    async def _background_memory_save():
                        _mem_start = time.perf_counter()
                        await self._save_session_memory_if_needed()
                        logger.debug(f"[PERF][turn] save_session_memory done (background) | +{(time.perf_counter()-_mem_start)*1000:.0f}ms")
                    
                    ConversationTurn._pending_memory_task = asyncio.create_task(_background_memory_save())
                    
                    logger.debug(f"[PERF][turn] _async_execute total | +{(time.perf_counter()-_exec_start)*1000:.0f}ms")
                    return result
                except Exception:
                    # Error path: the completion notification above only fires on
                    # success. Mirror it here so a long-running turn that crashes
                    # still produces an OS-level signal identifying which window
                    # died. Same gating as the completion path (enable flag,
                    # elapsed > 60s, no active goal). Re-raise afterwards so the
                    # existing error-display flow is unchanged.
                    try:
                        if getattr(self.config, 'enable_notification', True):
                            elapsed = time.perf_counter() - _exec_start
                            if elapsed > 60 and not self._has_active_goal():
                                from siada.notifications import show_completion_notification
                                session_title = self.session.state.session_title
                                show_completion_notification(
                                    title="Siada 任务异常中止",
                                    message=session_title or "Siada",
                                )
                    except Exception:
                        pass
                    raise
                finally:
                    self._stop_waiting_spinner()
                    # Clear current_result after execution completes
                    self.current_result = None
                    # Set cleanup done flag to notify main thread
                    self._cleanup_done.set()

            # Use dedicated event loop to execute async tasks (reuse loop, maintain connection pool advantages)
            self._ensure_dedicated_loop()

            try:
                # Execute async task in dedicated loop
                future = asyncio.run_coroutine_threadsafe(
                    _async_execute(), self._dedicated_loop
                )
                # IMPORTANT: Use polling loop with timeout instead of blocking
                # future.result(). Without timeout, future.result() blocks at
                # C level (Condition.wait → Lock.acquire) which cannot be
                # interrupted by _thread.interrupt_main() or SIGINT on some
                # platforms (especially Windows). Polling every 0.5s ensures
                # Python bytecode runs between iterations, giving the signal
                # handler a chance to fire and raise KeyboardInterrupt.
                import concurrent.futures
                while True:
                    try:
                        result = future.result(timeout=0.5)
                        break
                    except concurrent.futures.TimeoutError:
                        continue
            except KeyboardInterrupt:
                # CRITICAL: Signal the dedicated loop thread to stop any blocking
                # operations (e.g., _poll_stdin_with_timeout_check waiting for
                # interactive input like sudo password). This sets the global
                # _cancel_event and kills the child process from the main thread.
                try:
                    from siada.tools.coder.cmd_runner import cancel_current_command
                    cancel_current_command()
                except Exception as e:
                    logger.error(f"[ConversationTurn] Error calling cancel_current_command: {e}")
                
                # Use thread-safe event mechanism to check and cancel result
                if self._result_ready.wait(timeout=0.1):  # Non-blocking check with 100ms timeout
                    if self.current_result and not self.current_result.is_complete:
                        self.current_result.cancel()
                # Cancel the future and wait for actual cleanup completion
                if not future.done():
                    future.cancel()

                    # Wait for the background thread's cleanup to actually complete
                    cleanup_completed = self._cleanup_done.wait(timeout=2.0)

                    if cleanup_completed:
                        pass
                    else:
                        logger.warning("[ConversationTurn] Cleanup did not complete within 2 seconds timeout, proceeding anyway")
                        # The dedicated loop thread is likely blocked by a synchronous
                        # operation (e.g., run_cmd). Abandon it so the next turn gets
                        # a fresh event loop instead of hanging on the blocked one.
                        self._force_abandon_dedicated_loop()
                else:
                    pass

                asyncio.run(self.handle_interrupt())
                raise

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

        except KeyboardInterrupt as e:
            from rich.console import Console

            Console().show_cursor(True)
            
            # Send ACP message to stop all animations after interrupt
            # if self.config.acp_mode:
            #     from siada.io.acp.message_builder import ACPMessageBuilder
            #     builder = ACPMessageBuilder()
            #     stop_animation_msg = builder.build_session_update(
            #         reason="input_ready",
            #         content="",
            #         metadata={"animation_control": "stop"}
            #     )
            #     self.config.io.acp_adapter._send_if_acp(lambda: stop_animation_msg)
            # else:
            # self.config.io.print_warning("Conversation interrupted by user.")
            
            self.end_time = self._get_timestamp()
            raise e
        except BaseException as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)
        finally:
            if self.config.acp_mode:
                from siada.io.acp.message_builder import ACPMessageBuilder
                builder = ACPMessageBuilder()
                stop_animation_msg = builder.build_session_update(
                    reason="input_ready",
                    content="",
                    metadata={"animation_control": "stop"}
                )
                # Use _send_if_acp_robust instead of _send_if_acp
                # Reason: when finally block executes, the original event loop may be closed
                # _send_if_acp_robust uses an independent loop to ensure message delivery
                self.config.io.acp_adapter._send_if_acp_robust(lambda: stop_animation_msg)
            # else:
            #     self.config.io.print_warning("Conversation interrupted by user.")

    def print_split_line(self):
        if self.config.io.pretty:
            self.config.io.rule(
                color=self.config.running_color_settings.split_line_color
            )
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
        if self.session.spinner:
            try:
                self.session.spinner.stop()
            finally:
                self.session.state.spinner = None

    def _is_memory_enabled(self) -> bool:
        """Resolve the live memory master-switch state.

        The ``/memory`` slash command toggles the live CodeAgentContext's
        ``memory_tools_enabled`` flag (and persists to conf.yaml) but does NOT
        update ``RunningConfig.memory_enabled`` (which is only a startup mirror).
        So we prefer the live context value when available, mirroring the
        status-resolution logic in ``slash_commands`` and the memory-update
        scheduler, and fall back to the startup mirror otherwise.
        """
        try:
            from siada.services.siada_runner import SiadaRunner
            workspace = self.config.workspace
            for (_, ws), ctx in SiadaRunner._context_cache.items():
                if ws == workspace:
                    return bool(getattr(ctx, "memory_tools_enabled", True))
        except Exception as e:
            logger.debug(f"[ConversationTurn] Failed to resolve live memory switch: {e}")
        # Fall back to the startup mirror on RunningConfig.
        return bool(getattr(self.config, "memory_enabled", True))

    def _has_active_goal(self) -> bool:
        """Check whether this workspace currently has an active ``/goal``.

        Used to suppress the generic per-turn "waiting for input" completion
        notification while a goal is being auto-retried: each round here is
        just an intermediate step of the verifier loop (see
        ``siada.services.goal.turn_hooks.maybe_run_goal_verifier``), not the
        real end of the task. The goal verifier fires its own notification
        once the goal is actually achieved (or gives up as "blocked").
        """
        try:
            from siada.services.siada_runner import SiadaRunner
            workspace = self.config.workspace
            for (_, ws), ctx in SiadaRunner._context_cache.items():
                if ws == workspace:
                    goal = getattr(ctx, "goal", None)
                    return goal is not None and getattr(goal, "status", None) == "active"
        except Exception as e:
            logger.debug(f"[ConversationTurn] Failed to resolve active goal state: {e}")
        return False

    async def _save_session_memory_if_needed(self):
        """Save session memory to file after conversation turn completes.
        
        This method is called after all streaming and session updates are complete,
        ensuring that the final assistant message has been persisted to the session
        before we save the memory to file.
        """
        try:
            # Respect the memory master switch: when memory is disabled, skip
            # the raw session archival entirely so no conversation markdown is
            # written to disk or indexed into SQLite.
            if not self._is_memory_enabled():
                logger.debug("[ConversationTurn] Memory disabled — skipping session memory save")
                return

            if (self.session and 
                hasattr(self.session, 'openai_session') and 
                self.session.openai_session):
                
                from siada.services.memory import MemoryService
                memory_service = MemoryService()
                await memory_service.save_session_memory(
                    self.session.openai_session,
                    workspace=self.config.workspace,
                )
                logger.debug("[ConversationTurn] Session memory saved successfully")
        except Exception as e:
            logger.debug(f"[ConversationTurn] Failed to save session memory: {e}")

    def _display_browser_operate_result(self, output: List[Any]):
        """Display browser_operate tool result in a UI-friendly format.
        
        Deserializes the JSON content from browser_operate tool using 
        BrowserOperateResult.from_json() and calls format_for_display() for UI output.
        
        Args:
            output: List of ToolOutputText and ToolOutputImage items from browser_operate tool
        """
        # Extract text content and screenshot from output
        text_content = ""
        screenshot = None
        
        for item in output:
            if isinstance(item, ToolOutputText):
                text_content = item.text
            elif isinstance(item, ToolOutputImage):
                screenshot = item.image_url
        
        if not text_content:
            self.config.io.print_tool_result("✓ Browser operation completed")
            return
        
        try:
            # Deserialize JSON content and use format_for_display() for UI output
            from siada.tools.browser.models import BrowserOperateResult
            browser_result = BrowserOperateResult.from_json(text_content, screenshot)
            self.config.io.print_tool_result(browser_result.format_for_display())
        except Exception as e:
            # Fallback: if JSON parsing fails, show original text (truncated)
            logger.warning(f"Failed to parse browser result as JSON: {e}")
            display_text = text_content if len(text_content) <= 200 else text_content[:197] + "..."
            self.config.io.print_tool_result(f"✓ Browser operation completed\n{display_text}")

    def _print_context_usage(self, usage=None):
        """
        Print context usage information.
        
        Args:
            usage: Optional usage object from the response. If not provided, will use session state.
        """
        # Try to get usage from parameter first, then fall back to session state
        if usage and hasattr(usage, 'total_tokens'):
            context_size = usage.total_tokens if usage.total_tokens else 0
        else:
            context_size = self.session.state.usage.total_tokens if self.session.state.usage and self.session.state.usage.total_tokens else 0
        
        context_max = self.config.llm_config.context_window
        message = f"{context_size:,} / {context_max:,} tokens"
        
        # Send token usage event in ACP mode
        if self.config.io.acp_enabled:
            self._send_lifecycle_event({
                "type": "token_usage",
                "context_size": context_size,
                "context_max": context_max,
                "message": message,
                "timestamp": time.time()
            })
        else:
            # Use console to print with right alignment in non-ACP mode
            from rich.align import Align
            from rich.text import Text

            # Create styled text with a dim style for subtle display
            text = Text(message, style="dim #5B9BD5") # rule
            aligned_text = Align.right(text)

            self.config.io.console.print(aligned_text)

    async def handle_interrupt(self):
        """Handle user interruption by adding appropriate interrupt marker to session."""
        history = await self.session.openai_session.get_items()
        if not history:
            return

        from agents.models.chatcmpl_converter import Converter

        last_item = history[-1]
        interrupt_note = {
            "role": "user",
            "content": "Note: This Conversation Was Interrupted By User",
        }

        # Check if we need to add interrupt note based on last item type
        should_add_note = any(
            [
                Converter.maybe_input_message(last_item),
                Converter.maybe_easy_input_message(last_item),
                Converter.maybe_function_tool_call_output(last_item),
            ]
        )

        if should_add_note:
            await self.session.openai_session.add_items([interrupt_note])

        # Note: Assistant messages don't need interrupt notes
        # They are handled by checking maybe_response_output_message
