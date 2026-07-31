"""LarkStreamConsumer - Consumes RunResultStreaming events and renders to Lark.

Stream event consumption mirrors ConversationTurn.output_stream_content:
- Thinking (reasoning summary) -> sent as a collapsed section
- Answer (text delta) -> sent as streaming markdown
- Tool calls -> sent with name + formatted arguments
- Tool results -> sent after each tool execution
"""

import asyncio
import logging
from typing import Optional

from agents import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    RunResultStreaming,
    ToolCallOutputItem,
    ToolOutputImage,
    ToolOutputText,
)

from siada.im.feishu.card_sender import LarkCardSender
from siada.im.feishu.mention import build_mentioned_card_content
from siada.im.models import MentionTarget

logger = logging.getLogger("siada.im.lark.stream_consumer")


class LarkStreamConsumer:
    """Consumes agent streaming events and renders them as Lark cards/messages."""

    def __init__(self, card_sender: LarkCardSender, mode: str):
        self._card_sender = card_sender
        self._mode = mode

    async def consume_stream(
        self, result: RunResultStreaming, request_id: str, chat_id: str,
        default_workspace: str = "",
        mention_targets: list[MentionTarget] | None = None,
        verbose: bool = True,
    ) -> None:
        """Consume RunResultStreaming events and send outputs to Lark.

        In direct mode: uses CardKit streaming card (single card, in-place updates).
        In relay mode: sends streaming/reply messages via transport (server handles CardKit).

        Event types handled (same as ConversationTurn.output_stream_content):
        - ResponseCreatedEvent: reset state
        - ResponseReasoningSummaryTextDeltaEvent: thinking content
        - ResponseTextDeltaEvent: answer text
        - ResponseContentPartDoneEvent: answer section complete
        - ResponseOutputItemAddedEvent (FunctionToolCall): tool call start
        - ResponseFunctionCallArgumentsDeltaEvent: tool call args
        - ResponseOutputItemDoneEvent (FunctionToolCall): tool call complete
        - ResponseCompletedEvent: full response complete
        - RunItemStreamEvent (ToolCallOutputItem): tool execution result
        """
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
        from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
        from siada.tools.tool_call_format.tool_call_batcher import (
            ToolCallBatcher, ToolCallEntry, classify_tool,
        )

        cs = self._card_sender

        # Stream state
        reasoning_text = ""
        answer_text = ""
        tool_calls = {}  # call_id -> {name, arguments}
        item_id_to_call_id = {}  # item_id -> call_id for routing deltas
        got_reasoning = False
        got_content = False

        # Tool call batcher for grouped rendering
        batcher = ToolCallBatcher(default_workspace=default_workspace)

        # Static card for tool calls - sent once, updated via PATCH
        tool_card_msg_id: Optional[str] = None

        async def _ensure_tool_card_started():
            nonlocal tool_card_msg_id
            if tool_card_msg_id is None and cs._has_credentials():
                try:
                    content = batcher.render_current()
                    tool_card_msg_id = await cs.send_card_get_id(chat_id, content)
                except Exception as e:
                    logger.warning(f"Failed to send tool card: {e}")

        async def _update_tool_card():
            if tool_card_msg_id:
                try:
                    await cs.patch_card_content(tool_card_msg_id, batcher.render_current())
                except Exception as e:
                    logger.debug(f"Tool card patch failed: {e}")

        async def _close_tool_card():
            if tool_card_msg_id and batcher.has_pending:
                try:
                    await cs.patch_card_content(tool_card_msg_id, batcher.render_final())
                except Exception as e:
                    logger.warning(f"Failed to finalize tool card: {e}")
            elif not tool_card_msg_id and batcher.has_pending:
                content = batcher.render_final()
                if content:
                    await cs.send_card_message(
                        chat_id, title="🔧 Tool Execution",
                        content=content, header_template="blue", icon="",
                    )

        # Streaming cards for thinking and answer (direct mode only)
        thinking_card = cs.create_streaming_card(chat_id)
        thinking_card_started = False
        thinking_card_closed = False

        answer_card = cs.create_streaming_card(chat_id)
        answer_card_started = False
        answer_card_closed = False

        async def _ensure_thinking_card_started():
            nonlocal thinking_card_started
            if thinking_card and not thinking_card_started and not thinking_card_closed:
                try:
                    await thinking_card.start(
                        chat_id, initial_text="💭 ...",
                        header_title="💭 Thinking", header_template="purple",
                    )
                    thinking_card_started = True
                except Exception as e:
                    logger.warning(f"Failed to start thinking card: {e}")

        async def _close_thinking_card():
            nonlocal thinking_card_closed
            if thinking_card and thinking_card_started and not thinking_card_closed:
                thinking_card_closed = True
                try:
                    await thinking_card.close(reasoning_text if reasoning_text else None)
                except Exception as e:
                    logger.warning(f"Failed to close thinking card: {e}")

        async def _ensure_answer_card_started():
            nonlocal answer_card_started
            if answer_card and not answer_card_started and not answer_card_closed:
                try:
                    await answer_card.start(
                        chat_id, initial_text="💬 ...",
                        header_title="💬 Answer", header_template="green",
                    )
                    answer_card_started = True
                except Exception as e:
                    logger.warning(f"Failed to start answer card: {e}")

        async def _close_answer_card():
            nonlocal answer_card_closed
            if answer_card and answer_card_started and not answer_card_closed:
                answer_card_closed = True
                try:
                    await answer_card.close(answer_text if answer_text else None)
                except Exception as e:
                    logger.warning(f"Failed to close answer card: {e}")

        try:
            async for event in result.stream_events():
                if isinstance(event, RawResponsesStreamEvent):
                    data = event.data

                    if isinstance(data, ResponseCreatedEvent):
                        reasoning_text = ""
                        answer_text = ""
                        tool_calls = {}
                        got_reasoning = False
                        got_content = False

                        # Reset card lifecycle for new LLM turn
                        # (previous turn's cards may have been closed after tool calls)
                        if thinking_card_closed:
                            thinking_card = cs.create_streaming_card(chat_id)
                            thinking_card_started = False
                            thinking_card_closed = False
                        if answer_card_closed:
                            answer_card = cs.create_streaming_card(chat_id)
                            answer_card_started = False
                            answer_card_closed = False

                    elif isinstance(data, ResponseReasoningSummaryPartAddedEvent):
                        continue

                    elif isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
                        if data.delta:
                            # Close previous tool card group when reasoning appears
                            if not got_reasoning and batcher.has_pending:
                                if verbose:
                                    await _close_tool_card()
                                batcher = ToolCallBatcher(default_workspace=default_workspace)
                                tool_card_msg_id = None
                            got_reasoning = True
                            reasoning_text += data.delta
                            if verbose and thinking_card:
                                await _ensure_thinking_card_started()
                                if thinking_card_started:
                                    await thinking_card.update(reasoning_text)

                    elif isinstance(data, ResponseContentPartAddedEvent):
                        continue

                    elif isinstance(data, ResponseTextDeltaEvent):
                        if data.delta:
                            if not got_content and got_reasoning and reasoning_text:
                                if verbose:
                                    # Parallelize: close thinking card and start answer card concurrently.
                                    # They operate on independent card_ids so no shared state conflict.
                                    _parallel_tasks = [_close_thinking_card()]
                                    if answer_card and not answer_card_started and not answer_card_closed:
                                        _parallel_tasks.append(_ensure_answer_card_started())
                                    await asyncio.gather(*_parallel_tasks, return_exceptions=True)
                                    if not thinking_card:
                                        await cs.send_card_message(
                                            chat_id, title="💭 Thinking",
                                            content=reasoning_text, header_template="purple", icon="",
                                        )
                            if not got_content and batcher.has_pending:
                                if verbose:
                                    await _close_tool_card()
                                batcher = ToolCallBatcher(default_workspace=default_workspace)
                                tool_card_msg_id = None
                            got_content = True
                            answer_text += data.delta
                            if answer_card:
                                if not answer_card_started:
                                    await _ensure_answer_card_started()
                                if answer_card_started:
                                    await answer_card.update(answer_text)

                    elif isinstance(data, ResponseContentPartDoneEvent):
                        pass

                    elif isinstance(data, ResponseOutputItemAddedEvent):
                        if isinstance(data.item, ResponseFunctionToolCall):
                            if verbose:
                                await _close_thinking_card()
                                if answer_card_started:
                                    await _close_answer_card()
                                    answer_text = ""
                                elif answer_text:
                                    await cs.send_im(
                                        request_id, chat_id, answer_text,
                                        content_type="markdown", is_streaming=False,
                                    )
                                    answer_text = ""

                            call_id = data.item.call_id
                            item_id = data.item.id
                            tool_name = data.item.name
                            tool_calls[call_id] = {
                                "name": tool_name,
                                "arguments": "",
                            }
                            if item_id:
                                item_id_to_call_id[item_id] = call_id

                    elif isinstance(data, ResponseFunctionCallArgumentsDeltaEvent):
                        target_call_id = item_id_to_call_id.get(data.item_id)
                        if target_call_id and target_call_id in tool_calls:
                            tool_calls[target_call_id]["arguments"] += data.delta

                    elif isinstance(data, ResponseOutputItemDoneEvent):
                        if isinstance(data.item, ResponseFunctionToolCall):
                            call_id = data.item.call_id
                            if call_id in tool_calls:
                                tc = tool_calls[call_id]
                                tc["_done"] = True
                                tool_name = tc["name"]
                                full_args = tc["arguments"]

                                tool_cwd = ""
                                try:
                                    import json as _json
                                    _parsed = _json.loads(full_args) if full_args else {}
                                    tool_cwd = _parsed.get("cwd", "")
                                except Exception:
                                    pass

                                try:
                                    formatter = ToolCallFormatterFactory.get_formatter(tool_name)
                                    formatted, _ = formatter.format_input_im(
                                        call_id, tool_name, full_args,
                                        default_workspace=default_workspace,
                                    )
                                except Exception as fmt_err:
                                    logger.error(f"[ToolCall] Formatter error for {tool_name}: {fmt_err}", exc_info=True)
                                    formatted = f"**{tool_name}**\n```json\n{full_args[:500]}\n```"

                                logger.info(
                                    f"[ToolCall] tool_name={tool_name}, "
                                    f"formatted_len={len(formatted)}, "
                                    f"formatted_preview={formatted[:200]!r}"
                                )

                                entry = ToolCallEntry(
                                    call_id=call_id,
                                    tool_name=tool_name,
                                    formatted_input=formatted,
                                    category=classify_tool(tool_name, full_args),
                                    workspace=tool_cwd or default_workspace,
                                )
                                batcher.add_call(entry)

                                if verbose:
                                    await _ensure_tool_card_started()
                                    await _update_tool_card()

                    elif isinstance(data, ResponseCompletedEvent):
                        if verbose and got_reasoning and reasoning_text and not got_content:
                            if not thinking_card_started:
                                await cs.send_card_message(
                                    chat_id, title="💭 Thinking",
                                    content=reasoning_text, header_template="purple", icon="",
                                )

                elif isinstance(event, RunItemStreamEvent):
                    data = event.item
                    if isinstance(data, ToolCallOutputItem):
                        call_id = data.raw_item.get("call_id", "")
                        tool_name = tool_calls.get(call_id, {}).get("name", "unknown")

                        output = data.output
                        result_text = format_tool_output(output, tool_name)

                        batcher.add_result(call_id, result_text or "")
                        if verbose:
                            await _update_tool_card()

            # Final: close tool card if still open
            if verbose:
                await _close_tool_card()
                await _close_thinking_card()

            # Send final answer text (inject @ mentions in the final output)
            if answer_text:
                # Inject @mention tags for outbound reply (only in final card/text)
                final_answer = answer_text
                if mention_targets:
                    final_answer = build_mentioned_card_content(mention_targets, answer_text)

                if answer_card and not answer_card_started and not answer_card_closed:
                    await cs.send_card_message(
                        chat_id, title="💬 Answer",
                        content=final_answer, header_template="green", icon="",
                    )
                elif answer_card_started:
                    # Close the streaming card with mention-injected content
                    if mention_targets:
                        answer_card_closed = True
                        try:
                            await answer_card.close(final_answer)
                        except Exception as e:
                            logger.warning(f"Failed to close answer card with mentions: {e}")
                    else:
                        await _close_answer_card()
                else:
                    await cs.send_im(
                        request_id, chat_id, final_answer,
                        content_type="markdown", is_streaming=False,
                    )

        except Exception:
            # Ensure cards are closed on error
            if thinking_card_started and thinking_card and thinking_card.is_active():
                try:
                    await thinking_card.close(
                        reasoning_text if reasoning_text else "❌ Stream interrupted"
                    )
                except Exception:
                    pass
            if answer_card_started and answer_card and answer_card.is_active():
                try:
                    await answer_card.close(answer_text if answer_text else "❌ Stream interrupted")
                except Exception:
                    pass
            if tool_card_msg_id and batcher.has_pending:
                try:
                    await _close_tool_card()
                except Exception:
                    pass
            raise


def format_tool_output(output, tool_name: str) -> str:
    """Format tool output for display in Lark message.

    Handles the same output types as ConversationTurn:
    - FunctionCallResult: use format_for_display()
    - List[ToolOutputText/ToolOutputImage]: join text items
    - ToolOutputText/ToolOutputImage: single item
    - str: raw string
    """
    from siada.tools.coder.observation.observation import FunctionCallResult
    from siada.tools.coder.run_cmd import RunCmdResult

    # RunCmdResult has IM-specific formatting (clean output in code block)
    if isinstance(output, RunCmdResult):
        return output.format_for_display_im()
    if isinstance(output, FunctionCallResult):
        return output.format_for_display()
    elif isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, ToolOutputText):
                parts.append(item.text)
            elif isinstance(item, ToolOutputImage):
                parts.append("✓ Image loaded")
            else:
                parts.append(str(item))
        return "\n".join(parts)
    elif isinstance(output, ToolOutputText):
        return output.text
    elif isinstance(output, ToolOutputImage):
        return "✓ Image loaded"
    else:
        text = str(output)
        if len(text) > 2000:
            return text[:1997] + "..."
        return text
