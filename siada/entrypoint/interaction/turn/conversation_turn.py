"""
Conversation Turn Module

Handles AI conversation turns including streaming responses and tool calls.
"""

from siada.foundation.logging import logger
import re
import asyncio
import time
import siada.io.components.mdstream
from typing import AsyncIterator, List, Optional, Dict, Any, Tuple

from agents import (
    RawResponsesStreamEvent,
    ReasoningItem,
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
from siada.tools.coder.apply_patch_presentation import render_apply_patch_display
from siada.tools.coder.file_edit_presentation import (
    is_file_edit_write,
    render_file_edit_display,
)
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
from siada.models.model_base_config import supports_image_input
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
from .models import (
    TurnType,
    TurnInput,
    TurnOutput,
    RETRY_REASON_METADATA_KEY,
    RETRY_REASON_REPETITIVE_STREAM,
)
from .interface import RunTurn, ImageNotSupportedError
from .stream_repetition import (
    RepetitiveStreamError,
    StreamRepetitionDetector,
    is_repetition_guard_model,
)


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
    _MAX_STREAM_RECOVERIES = 2
    _STREAM_RECOVERY_INPUT = (
        "<system-reminder>\n"
        "The previous model response was interrupted. Continue the original task "
        "from the saved conversation and completed tool results. Do not repeat "
        "completed operations. Check the current state before repeating any "
        "operation whose outcome is uncertain. Any unfinished tool call was "
        "not executed; generate it again if it is still needed.\n"
        "</system-reminder>"
    )

    async def _run_stream_with_recovery(self, user_input: str | list) -> RunResultStreaming:
        """Continue durable history after EOF or a transport interruption."""
        import asyncio
        from siada.provider.retry import MissingFinalResponseError, is_retryable_transport_error
        from siada.services.siada_runner import SiadaRunner

        store = self.session.openai_session
        read_history = getattr(store, "get_history_items", store.get_items)
        initial_history = await read_history()
        original_items = (
            [{"role": "user", "content": user_input}]
            if isinstance(user_input, str) else user_input
        )
        next_input = user_input
        for attempt in range(self._MAX_STREAM_RECOVERIES + 1):
            try:
                result = await SiadaRunner.run_agent(
                    agent_name=self.config.agent_name,
                    user_input=next_input,
                    workspace=self.config.workspace,
                    session=self.session,
                    stream=True,
                )
                self.current_result = result
                await self.output_stream_content(result)
                return result
            except Exception as error:
                if (
                    attempt == self._MAX_STREAM_RECOVERIES
                    or not (
                        isinstance(error, MissingFinalResponseError)
                        or is_retryable_transport_error(error)
                    )
                ):
                    raise
                # Read failures must propagate: recovery requires durable state.
                history = await read_history()
                # A rewrite makes admission uncertain; never replay on a guess.
                if history[:len(initial_history)] != initial_history:
                    raise
                additions = history[len(initial_history):]

                def content_parts(item):
                    if not isinstance(item, dict):
                        return None
                    content = item.get("content")
                    if isinstance(content, str):
                        return [{"type": "input_text", "text": content}]
                    if not isinstance(content, list):
                        return None
                    parts = []
                    for part in content:
                        if not isinstance(part, dict):
                            return None
                        if part.get("type") in {"input_text", "text"}:
                            parts.append({"type": "input_text", "text": part.get("text")})
                        else:
                            parts.append(part)
                    return parts

                # Unsupported input/history shapes cannot establish admission.
                if any(not isinstance(item, dict) for item in additions) or any(
                    content_parts(item) is None for item in original_items
                ):
                    raise

                def contains_input(original):
                    if original in additions:
                        return True
                    parts = content_parts(original)
                    return bool(parts) and any(
                        item.get("role") == original.get("role")
                        and content_parts(item) is not None
                        and all(part in content_parts(item) for part in parts)
                        for item in additions
                    )

                input_admitted = bool(original_items) and all(
                    contains_input(item) for item in original_items
                )
                next_input = (
                    self._STREAM_RECOVERY_INPUT if input_admitted
                    else user_input
                )
                if self._current_message_id is not None:
                    message_type = (
                        "tool_call" if self.got_function_call_part
                        else "answer" if self.got_content_part else "thinking"
                    )
                    self._emit_message_end(message_type)
                self._stream_start_id = None
                self.current_active_call_id = None
                self.current_result = None
                delay = 2 ** attempt
                logger.warning(
                    "[ConversationTurn] Recovering interrupted response: "
                    "attempt=%s/%s error=%s delay=%ss",
                    attempt + 1, self._MAX_STREAM_RECOVERIES, type(error).__name__, delay,
                )
                self.config.io.print_warning(
                    f"模型响应中断，正在从已保存的进度继续"
                    f"（{attempt + 1}/{self._MAX_STREAM_RECOVERIES}）。"
                )
                await asyncio.sleep(delay)
        raise AssertionError("Unreachable stream recovery state")

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

    def __init__(
        self, config: RunningConfig, session: Any, slash_commands: Any,
        *, render_stream: bool = True,
    ):
        super().__init__(config, session, slash_commands)
        self.render_stream = render_stream
        self.mdargs = dict(
            style=self.config.running_color_settings.split_line_color,
            code_theme=self.config.running_color_settings.code_theme,
            inline_code_lexer="text",
        ) if render_stream else {}
        # Instance variable to store current running result for cancellation
        self.current_result: Optional[RunResultStreaming] = None
        # Message tracking
        self._message_counter = 0
        self._current_message_id = None
        self._stream_start_id = None  # Track the start ID of current stream
        # Repetition guard (whitelisted models only, see stream_repetition.py)
        self._repetition_detector: Optional[StreamRepetitionDetector] = None
        self._stream_retry_reason: Optional[str] = None
    
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

    def get_turn_type(self) -> TurnType:
        return TurnType.CONVERSATION

    def can_handle(self, user_input: str | List[Any]) -> bool:
        """Handle non-command input"""
        if isinstance(user_input, list):
            return True
        return not self.slash_commands.is_command(user_input)

    def _is_truncated_reasoning_only_completion(self, result: RunResultStreaming) -> bool:
        """Detect a Chat Completions/LiteLLM "fake completion".

        On the Responses API path, a stream that gets cut off mid-turn
        surfaces as an explicit incomplete/error status the agents SDK can
        react to. On the Chat Completions/LiteLLM path there is no such
        signal: a connection that drops right after the model's reasoning
        delta -- but before any message or tool-call delta ever arrives --
        produces a ``RunResultStreaming`` that looks *identical* to "the
        model genuinely decided to say nothing": ``final_output`` is empty
        and the only generated item is a bare ``ReasoningItem``.

        Only the LAST item in ``new_items`` is checked here, not "no
        MessageOutputItem/ToolCallItem exists at all" -- a normal, healthy
        turn can legitimately contain a ``ReasoningItem`` followed by a
        ``MessageOutputItem``/``ToolCallItem``. It's specifically a turn
        that *ends* on a bare reasoning step with nothing after it that
        indicates the stream was truncated.

        Returns:
            bool: True if this looks like a truncated fake completion that
                should be retried, rather than a genuine (if unhelpful)
                empty response from the model.
        """
        final_output = result.final_output
        is_empty_output = final_output is None or (
            isinstance(final_output, str) and final_output.strip() == ""
        )
        if not is_empty_output:
            return False

        new_items = getattr(result, "new_items", None)
        if not new_items:
            return False

        return isinstance(new_items[-1], ReasoningItem)

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
        if not getattr(self, "render_stream", True) or not self.config.io.acp_enabled:
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

    def _feed_repetition_guard(self, delta_text: str) -> None:
        """Feed a text delta into the repetition guard (guarded models only).

        No-op unless the detector was armed on ResponseCreatedEvent. On
        detection: notify the UI to drop the stream (``stream_aborted``
        lifecycle event), cancel the underlying request, and raise
        ``RepetitiveStreamError`` -- caught in ``_async_execute`` which flags
        the turn for an automatic retry via RETRY_REASON_REPETITIVE_STREAM.
        """
        detector = self._repetition_detector
        if detector is None or detector.fired:
            return
        hit = detector.feed(delta_text)
        if not hit:
            return
        unit, repeats = hit
        unit_preview = unit[:80].replace("\n", "\\n")
        logger.warning(
            f"[ConversationTurn] Repetitive stream detected "
            f"(kind={detector.kind}, unit_length={len(unit)}, repeats={repeats}, "
            f"unit={unit_preview!r}) -- aborting request for retry"
        )
        # Tell the UI this stream is confirmed bad so it can discard whatever
        # it held back (or already rendered) for it.
        # NOTE: metadata is merged into ACP params by build_session_update --
        # a "reason" key here would overwrite the message's own
        # reason="lifecycle_event" routing field, so use "abort_reason".
        self._send_lifecycle_event({
            "type": "stream_aborted",
            "abort_reason": "repetition",
            "stream_start_id": self._stream_start_id or "",
            "timestamp": time.time(),
        })
        self._stream_start_id = None
        self._stream_retry_reason = RETRY_REASON_REPETITIVE_STREAM
        # Stop the underlying HTTP stream so the model doesn't keep burning
        # tokens on the loop.
        try:
            if self.current_result is not None and not self.current_result.is_complete:
                self.current_result.cancel()
        except Exception as e:
            logger.debug(f"[ConversationTurn] cancel() after repetition failed: {e}")
        raise RepetitiveStreamError(unit_preview, repeats, len(unit))

    def _cancel_failed_stream(self, result: RunResultStreaming) -> None:
        """Stop an abandoned producer before SDK stream closure waits for it."""
        try:
            if not result.is_complete:
                result.cancel()
        except Exception as error:
            logger.debug(f"[ConversationTurn] cancel() after stream failure failed: {error}")

    async def _guarded_stream_events(self, result: RunResultStreaming) -> AsyncIterator[Any]:
        """Apply incremental execution guards independently of presentation."""
        from siada.entrypoint.runtime.turn_event import (
            RESPONSE_CREATED, REASONING_DELTA, TEXT_DELTA, classify_stream_event,
        )

        stream = result.stream_events()
        stream_failed = False
        try:
            async for event in stream:
                te = classify_stream_event(event)
                if te is not None:
                    if te.kind == RESPONSE_CREATED:
                        model_name = getattr(
                            getattr(self.config, "llm_config", None), "model_name", "",
                        )
                        self._repetition_detector = (
                            StreamRepetitionDetector()
                            if is_repetition_guard_model(model_name) else None
                        )
                    elif te.kind in {REASONING_DELTA, TEXT_DELTA}:
                        self._feed_repetition_guard(te.delta)
                yield event
        except BaseException:
            stream_failed = True
            self._cancel_failed_stream(result)
            raise
        finally:
            try:
                await stream.aclose()
            except Exception as error:
                if not stream_failed:
                    raise
                logger.warning(f"[ConversationTurn] Stream cleanup after failure failed: {error}")

    async def output_stream_content(self, result: RunResultStreaming) -> None:
        """Consume the same guarded stream, optionally rendering its events."""
        from siada.entrypoint.runtime.turn_event import (
            RESPONSE_CREATED,
            REASONING_PART_ADDED,
            REASONING_DELTA,
            CONTENT_PART_ADDED,
            TEXT_DELTA,
            CONTENT_PART_DONE,
            TOOL_CALL_START,
            TOOL_ARGS_DELTA,
            TOOL_CALL_DONE,
            RESPONSE_COMPLETED,
            TOOL_OUTPUT,
            classify_stream_event,
        )

        stream_iterator = None
        stream_failed = False
        pending_file_edits: dict[str, str] = {}
        try:
            stream_iterator = self._guarded_stream_events(result)
            async for event in stream_iterator:
                if not getattr(self, "render_stream", True):
                    continue
                if isinstance(event, RawResponsesStreamEvent):
                    self._stop_waiting_spinner()

                te = classify_stream_event(event)
                if te is None:
                    continue

                if te.kind == RESPONSE_CREATED:
                    # A transport retry can start while thinking is still open.
                    # Finish that display before the next attempt gets new IDs.
                    if (
                        getattr(self, "got_reasoning_part", False)
                        and not getattr(self, "got_content_part", False)
                        and not getattr(self, "got_function_call_part", False)
                        and self._current_message_id is not None
                    ):
                        self._emit_message_end("thinking")
                        if self.mdstream is not None:
                            self.mdstream.close()
                            self.mdstream = None
                        self._stream_start_id = None
                    # Response started
                    self.response_content = ""
                    self.tool_calls = {}
                    self.tool_call_mdstreams = {}
                    self.got_content_part = False
                    self.got_reasoning_part = False
                    self.current_active_call_id = None
                    self.got_tool_result_part = False
                    self.got_function_call_part = False

                elif te.kind == REASONING_PART_ADDED:
                    if self.mdstream is None:
                        self.mdstream = (
                            self.get_response_mdstream()
                            if self.config.io.pretty
                            else None
                        )
                    continue

                elif te.kind == REASONING_DELTA:
                    if not self.got_reasoning_part and te.delta:
                        self.got_reasoning_part = True
                        # Emit message start marker for thinking
                        self._emit_message_start("thinking")
                        # self.print_split_line()
                        delta_text = f"\n{REASONING_START}: {te.delta}"
                        self.response_content += delta_text
                    else:
                        delta_text = te.delta
                        self.response_content += delta_text
                    self._live_incremental_response(
                        delta_text, self.response_content
                    )

                elif te.kind == CONTENT_PART_ADDED:
                    if self.mdstream is None:
                        self.mdstream = (
                            self.get_response_mdstream()
                            if self.config.io.pretty
                            else None
                        )
                    continue

                elif te.kind == TEXT_DELTA:
                    if not self.got_content_part and te.delta:
                        self.got_content_part = True
                        # End thinking message if it was started
                        if self.got_reasoning_part:
                            self._emit_message_end("thinking")
                        # Start answer message
                        self._emit_message_start("answer")
                        # if not self.got_reasoning_part:
                        #     self.print_split_line()
                        delta_text = f"\n\n{REASONING_END}\n\n{te.delta}"
                        self.response_content += delta_text
                    else:
                        delta_text = te.delta
                        self.response_content += delta_text
                    self._live_incremental_response(
                        delta_text, self.response_content
                    )

                elif te.kind == CONTENT_PART_DONE:
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

                elif te.kind == TOOL_CALL_START:
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

                    call_id = te.call_id
                    tool_name = te.name
                    if te.is_apply_patch:
                        # Native Responses apply_patch calls are not function
                        # calls: they contain an ``operation`` instead of JSON
                        # ``arguments``.  Keep the raw call for result
                        # correlation, but defer rendering until the local
                        # editor has captured actual file before/after text on
                        # the tool output event.
                        self.tool_calls[call_id] = {
                            "name": "apply_patch",
                            "native_apply_patch": True,
                            "raw_item": te.raw_item,
                        }
                        continue

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

                elif te.kind == TOOL_ARGS_DELTA:
                    delta = te.delta
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

                elif te.kind == TOOL_CALL_DONE:
                    call_id = te.call_id
                    if te.is_apply_patch:
                        # A native patch call has no JSON arguments to format:
                        # keep the completed item, whose operation is the
                        # authoritative fallback for the render, and emit the
                        # patch once on its output event.
                        if call_id in self.tool_calls:
                            self.tool_calls[call_id]["raw_item"] = te.raw_item
                    elif call_id in self.tool_calls:
                        tool_name = self.tool_calls[call_id]["name"]
                        full_arguments = self.tool_calls[call_id]["arguments"]

                        if tool_name == "edit_file":
                            full_arguments = te.arguments
                            self.tool_calls[call_id]["arguments"] = full_arguments
                        if tool_name == "edit_file" and is_file_edit_write(full_arguments):
                            pending_file_edits[call_id] = full_arguments
                            content = render_file_edit_display(call_id, full_arguments)
                            if self.config.io.acp_enabled:
                                self._send_lifecycle_event({
                                    "type": "tool_use", "delta": content,
                                    "chunk_index": 0, "is_final": True,
                                    "stream_end": True, "timestamp": time.time(),
                                })
                            self._emit_message_end("tool_call")
                            continue

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

                elif te.kind == RESPONSE_COMPLETED:
                    # Stage 3: Close the Live+Panel display without adding token info
                    usage = te.usage
                    
                    # Close the Live+Panel display (don't add token info to panel)
                    # if hasattr(self.config.io, '_tool_call_stages') and self.config.io._tool_call_stages:
                    #     # Just close the panel without adding token info
                    #     self.config.io.print_tool_call_all_stages("", final=True, append=False)
                    
                    # Print context usage using original method (outside the panel)
                    self._print_context_usage(usage=usage)

                elif te.kind == TOOL_OUTPUT:
                    if te.call_id:
                        if te.is_apply_patch:
                            call = self.tool_calls.get(te.call_id, {})
                            content = render_apply_patch_display(
                                custom_data=te.custom_data,
                                raw_call=call.get("raw_item"),
                                output=te.output,
                            )
                            # The existing ACP lifecycle path transports this
                            # text as one final ``tool_use`` message.  No ACP
                            # schema/storage change is necessary; the UI
                            # recognises the stable sentinels and turns the
                            # block into a multi-file diff view.
                            self._emit_message_start("tool_call")
                            self.config.io.advance_tool_call_stage()
                            self.config.io.print_tool_call_all_stages(
                                content, final=True
                            )
                            self._emit_message_end("tool_call")
                        elif te.call_id in self.tool_calls:
                            tool_name = self.tool_calls[te.call_id]["name"]
                            arguments = self.tool_calls[te.call_id].get("arguments", "")
                            if tool_name == "edit_file" and is_file_edit_write(arguments):
                                pending_file_edits.pop(te.call_id, None)
                                content = render_file_edit_display(
                                    te.call_id, arguments, output=te.output,
                                    structured=self.config.io.acp_enabled,
                                )
                                if self.config.io.acp_enabled:
                                    self._send_lifecycle_event({
                                        "type": "tool_use", "delta": content,
                                        "chunk_index": 0, "is_final": True,
                                        "stream_end": True, "timestamp": time.time(),
                                    })
                                else:
                                    self.config.io.advance_tool_call_stage()
                                    self.config.io.print_tool_call_all_stages(content, final=True)
                                continue
                            # self.print_split_line()
                            
                            # Start tool_result message
                            self._emit_message_start("tool_result")
                            
                            output = te.output
                            if isinstance(output, list) and tool_name == "browser_operate":
                                # Special handling for browser_operate to show concise UI display
                                self._display_browser_operate_result(output)
                            else:
                                render_tool_call_output(self.config.io, output, tool_name)
                            self._emit_message_end("tool_result")
        except BaseException:
            stream_failed = True
            self._cancel_failed_stream(result)
            raise
        finally:
            if stream_iterator is not None:
                try:
                    await stream_iterator.aclose()
                except Exception as error:
                    if not stream_failed:
                        raise
                    logger.warning(f"[ConversationTurn] Stream cleanup after failure failed: {error}")
            if self.config.io.acp_enabled:
                for call_id, arguments in pending_file_edits.items():
                    self._send_lifecycle_event({
                        "type": "tool_use",
                        "delta": render_file_edit_display(call_id, arguments, history=True),
                        "chunk_index": 0, "is_final": True,
                        "stream_end": True, "timestamp": time.time(),
                    })
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
        - Vision-bridge models (deepseek-v4 family) have the images
          transcribed by a vision engine and receive the text evidence
          instead; falls back to strip/reject when transcription fails.
        - Image-only messages (no text) raise ImageNotSupportedError after
          printing an error to the frontend.
        - Text+image messages have their images stripped; returns the text only.

        When the model supports images, builds a multimodal input list.

        Only an explicit ``supports_images=False`` declaration counts as
        "cannot process images"; an undeclared model (``None``, see
        :func:`siada.models.model_base_config.supports_image_input`) is
        treated as capable and the gateway decides.

        Args:
            user_input: The raw text input from the user.
            pending_images: List of image file paths from the IO layer.

        Returns:
            - The original user_input (str) if images were stripped.
            - user_input + transcribed image evidence (str) for bridge models.
            - A multimodal input list if images were attached.

        Raises:
            ImageNotSupportedError: if the model cannot process images and
                the message has no meaningful text.
        """
        io = getattr(self.config, "io", None)
        io._pending_image_paths = None  # always clear the pending slot

        supports_images = supports_image_input(
            getattr(self.config.llm_config, "supports_images", None)
        )
        if supports_images is False:
            # modlens-style vision bridge: text-only models (deepseek-v4
            # family) get image content as transcribed text evidence instead
            # of native image parts (the gateway silently drops those).
            from siada.services import vision_bridge

            if vision_bridge.supports_vision_bridge(self.config.llm_config):
                transcriptions = vision_bridge.transcribe_images_sync(
                    pending_images, user_hint=user_input
                )
                if transcriptions:
                    logger.info(
                        "[ConversationTurn] vision bridge transcribed %d/%d image(s)",
                        len(transcriptions), len(pending_images),
                    )
                    evidence = vision_bridge.build_evidence_text(transcriptions)
                    return f"{user_input}\n\n{evidence}" if user_input else evidence
                logger.info(
                    "[ConversationTurn] vision bridge unavailable/failed; "
                    "falling back to strip/reject"
                )

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

    async def execute(self, turn_input: TurnInput) -> Optional[TurnOutput]:
        """Execute AI conversation turn

        Args:
            turn_input: User input for conversation

        Returns:
            AI response, or None when a hook intentionally stops the turn.
        """
        _exec_start = time.perf_counter()
        logger.debug(f"[PERF][turn] execute() start")
        self.input_data = turn_input
        self.start_time = self._get_timestamp()
        
        # Reset per-turn state; execution stays on the entry-point loop.
        self.error = None
        self._stream_retry_reason = None
        self._repetition_detector = None

        try:
            async def _async_execute():
                try:
                    # Memory work belongs to this session and the entry-point loop.
                    pending = getattr(self.session.state, "pending_memory_task", None)
                    if pending is not None:
                        self.session.state.pending_memory_task = None
                        try:
                            if not pending.cancelled():
                                await asyncio.wait_for(asyncio.shield(pending), timeout=15.0)
                        except asyncio.CancelledError:
                            if asyncio.current_task().cancelling():
                                raise
                        except Exception as exc:
                            logger.info("[ConversationTurn] Previous memory save: %s", exc)

                    user_input = turn_input.use_input

                    # Wrap raw, literal user-typed text in a <user_input> tag
                    # so downstream consumers (frontend history display,
                    # memory review) can unambiguously recover exactly what
                    # the human typed, distinct from synthesized context
                    # injected alongside it (goal reminders, IM context
                    # blocks, holographic prefetch, ...). See
                    # ``siada.services.memory.holographic.marker`` for the
                    # full rationale. List-shaped inputs (multimodal / /goal
                    # payloads) are left untouched here.
                    if isinstance(user_input, str):
                        from siada.services.memory.holographic.marker import (
                            wrap_user_input,
                        )

                        user_input = wrap_user_input(user_input)

                    # If there are pending image paths from the IO layer, build
                    # a multimodal input (with image-support guard).
                    io = getattr(self.config, "io", None)
                    pending_images = getattr(io, "_pending_image_paths", None)
                    if pending_images and isinstance(user_input, str):
                        user_input = self._resolve_image_input(
                            user_input, pending_images
                        )

                    # Run agent for conversation
                    _stream_start = time.perf_counter()
                    logger.debug("[PERF][turn] streamed execution start")
                    try:
                        result = await self._run_stream_with_recovery(user_input)
                    except RepetitiveStreamError as rep_exc:
                        result = self.current_result
                        # Repetition-loop guard fired (deepseek-v4-flash family
                        # only). The request was already cancelled and the UI
                        # notified via `stream_aborted`. Fall through with the
                        # partial result -- execute() flags the turn with
                        # RETRY_REASON_REPETITIVE_STREAM and Controller
                        # transparently retries it.
                        logger.warning(
                            f"[ConversationTurn] Stream aborted due to repetition, "
                            f"will retry: {rep_exc}"
                        )
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
                        hook_event = (
                            "PreToolUse"
                            if isinstance(hook_exc, ToolInputGuardrailTripwireTriggered)
                            else "PostToolUse"
                        )
                        self.config.io.print_hook(stop_reason, hook_event, status="stopped")
                        return None
                    logger.debug(f"[PERF][turn] streamed execution done | +{(time.perf_counter()-_stream_start)*1000:.0f}ms")

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
                        if getattr(self, "render_stream", True) and getattr(self.config, 'enable_notification', True):
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
                    
                    if getattr(self, "render_stream", True):
                        self.session.state.pending_memory_task = asyncio.create_task(
                            _background_memory_save(), name="session-memory-save",
                        )
                    else:
                        # A one-shot surface has no next turn to drain this work.
                        await _background_memory_save()
                    
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
                        if getattr(self, "render_stream", True) and getattr(self.config, 'enable_notification', True):
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
                    # Cancellation cleanup still needs the active stream handle.

            try:
                result = await _async_execute()
            except asyncio.CancelledError:
                try:
                    from siada.tools.coder.cmd_runner import cancel_current_command
                    cancel_current_command()
                except Exception as e:
                    logger.error(f"[ConversationTurn] Error calling cancel_current_command: {e}")
                try:
                    from siada.tools.agent.subagent_async import (
                        cancel_session_background_subtasks,
                        shutdown_session_background_subtasks,
                    )
                    cancel_session_background_subtasks(self.session.session_id)
                    await shutdown_session_background_subtasks(self.session.session_id)
                except Exception as e:
                    logger.error(f"[ConversationTurn] Error cancelling background sub-agent tasks: {e}")
                try:
                    if self.current_result:
                        self.current_result.cancel()
                        task = self.current_result.run_loop_task
                        if task is not None:
                            await asyncio.gather(task, return_exceptions=True)
                        async for _ in self.current_result.stream_events():
                            pass
                except Exception as exc:
                    logger.warning("[ConversationTurn] Cancelled stream cleanup failed: %s", exc)
                try:
                    await self.handle_interrupt()
                except Exception as exc:
                    logger.warning("[ConversationTurn] Interrupt history cleanup failed: %s", exc)
                raise

            self.end_time = self._get_timestamp()

            # A hook stop is an intentional end of the turn. Preserve None so
            # turn policy skips retries, goal verification and continuation.
            if result is None:
                self.output_data = None
                return None

            # Chat Completions/LiteLLM truncated-stream guard: just flag a
            # truncated fake completion here (see
            # _is_truncated_reasoning_only_completion) via the generic
            # RETRY_REASON_METADATA_KEY -- the retry decision/execution
            # belongs to TurnPolicy._maybe_retry_turn, so this method's
            # contract stays simple (always return one TurnOutput, never
            # decide whether/how many times to retry).
            metadata = {
                "agent_used": self.config.agent_name,
                "execution_time": self.end_time - self.start_time,
            }
            if self._is_truncated_reasoning_only_completion(result):
                from .models import RETRY_REASON_TRUNCATED_REASONING_ONLY
                metadata[RETRY_REASON_METADATA_KEY] = RETRY_REASON_TRUNCATED_REASONING_ONLY
            # Repetition guard takes precedence: the stream was aborted
            # mid-flight, so the truncated check above may also match on the
            # partial result -- the retry reason must stay "repetitive_stream".
            if self._stream_retry_reason is not None:
                metadata[RETRY_REASON_METADATA_KEY] = self._stream_retry_reason

            output = TurnOutput(
                output=result.final_output,
                metadata=metadata,
                next_action=None,
            )

            self.output_data = output
            return output

        except KeyboardInterrupt as e:
            # Restore cursor in TTY mode only — in ACP mode stdout carries
            # JSON-RPC and ANSI escape codes would corrupt the protocol stream.
            if getattr(self, "render_stream", True) and not self.config.acp_mode:
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
        except asyncio.CancelledError:
            self.end_time = self._get_timestamp()
            raise
        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)
        finally:
            self.current_result = None
            if getattr(self, "render_stream", True) and self.config.acp_mode:
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
        if not getattr(self, "render_stream", True):
            return
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
            context = SiadaRunner.find_session_context(self.session)
            if context is not None:
                return bool(getattr(context, "memory_tools_enabled", True))
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
            context = SiadaRunner.find_session_context(self.session)
            if context is not None:
                goal = getattr(context, "goal", None)
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
        usage_obj = usage if usage and hasattr(usage, 'input_tokens') else self.session.state.usage
        
        if usage_obj and hasattr(usage_obj, 'input_tokens'):
            # Context window usage = input tokens (including cached) only, not output tokens
            cached_tokens = 0
            if hasattr(usage_obj, 'input_tokens_details') and usage_obj.input_tokens_details:
                cached_tokens = getattr(usage_obj.input_tokens_details, 'cached_tokens', 0) or 0
            context_size = usage_obj.input_tokens + cached_tokens
        else:
            context_size = 0
        
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

    async def handle_interrupt(self, input_restored: "bool | None" = None):
        """Handle user interruption by adding appropriate interrupt marker to session.

        Args:
            input_restored: Outcome of the early restore check run by
                the cancellation handler:
                - True: the input was already handed back to the input box —
                  nothing left to do (no note: the turn left no trace).
                - False: persistence was already confirmed — skip the restore
                  check and go straight to the interrupt-note logic.
                - None: early check never ran (error path) — run the full
                  restore check here.
        """
        history = await self.session.openai_session.get_items()

        # If the current user input never made it into the session (Ctrl+C
        # landed before the SDK persisted it), hand it back to the frontend
        # input box instead of losing it. No interrupt note is added in this
        # case: the turn left no trace in history, so there is nothing to
        # mark as interrupted.
        if input_restored is True:
            return
        if input_restored is None and self._restore_unpersisted_input(history):
            return

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

    def _restore_unpersisted_input(self, history: list) -> bool:
        """Hand the current user input back to the ACP input box if it was
        never persisted to the session.

        The SDK persists the turn input (``save_result_to_session``) right
        before the first LLM call. A Ctrl+C landing earlier than that — agent
        loading, context/checkpoint preparation, guardrails — leaves no trace
        of the input in ``api_history.json``, so without this the text would
        be lost.

        Returns True when the input was handed back (caller must skip the
        interrupt note), False otherwise.
        """
        if not getattr(self.config, "acp_mode", False):
            return False

        user_input = None
        if self.input_data is not None:
            user_input = getattr(self.input_data, "use_input", None)
        if not isinstance(user_input, str) or not user_input.strip():
            return False

        if self._input_persisted_in_history(user_input, history):
            return False

        self._send_restore_input_notification(user_input)
        return True

    def _input_persisted_in_history(
        self, user_input: str, history: list
    ) -> bool:
        """Whether the raw user input already appears in the session history.

        A goal reminder may be merged into the persisted turn input
        (``_maybe_merge_goal_reminder``), so a persisted user item whose text
        merely *contains* the raw input still counts as persisted.
        """
        needle = user_input.strip()
        for item in reversed(history):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            haystack = self._extract_user_item_text(item).strip()
            if haystack and (needle == haystack or needle in haystack):
                return True
        return False

    @staticmethod
    def _extract_user_item_text(item: dict) -> str:
        """Extract text from a persisted user message (plain or multimodal)."""
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_text":
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return ""

    def _send_restore_input_notification(self, text: str) -> None:
        """Notify the ACP frontend to put ``text`` back into the input box."""
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder

            adapter = getattr(self.config.io, "acp_adapter", None)
            if adapter is None:
                return
            builder = ACPMessageBuilder()
            msg = builder.build_session_update(
                reason="restore_input", content=text, metadata={}
            )
            # Use the robust sender: the turn's event loop may already be
            # torn down by the time the interrupt is handled.
            adapter._send_if_acp_robust(lambda: msg)
            logger.info(
                "[ConversationTurn] Restored unpersisted user input to input box"
            )
        except Exception as e:
            logger.debug(
                "[ConversationTurn] Failed to send restore_input notification: %s",
                e,
            )
