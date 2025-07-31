from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response_reasoning_item import Summary
from openai.types.responses.response_reasoning_summary_part_added_event import (
    Part as AddedEventPart,
)
from openai.types.responses.response_reasoning_summary_part_done_event import Part as DoneEventPart
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from siada.provider.li.domian.complete_usage import LiCompletionUsage
from siada.provider.li.domian.li_chat_complete_chunk import LiChatCompletionChunk, LiReasoningContent
from siada.provider.li.stream.__stream import AsyncStream

from agents.items import TResponseStreamEvent
from agents.models.fake_id import FAKE_RESPONSES_ID


# Define a Part class for internal use
class Part:
    def __init__(self, text: str, type: str):
        self.text = text
        self.type = type


@dataclass
class StreamingState:
    started: bool = False
    text_content_index_and_output: tuple[int, ResponseOutputText] | None = None
    refusal_content_index_and_output: tuple[int, ResponseOutputRefusal] | None = None
    reasoning_content_index_and_output: tuple[int, ResponseReasoningItem] | None = None
    function_calls: dict[int, ResponseFunctionToolCall] = field(default_factory=dict)
    # 用于处理没有index但有call_id的情况：映射call_id到分配的index
    call_id_to_index: dict[str, int] = field(default_factory=dict)
    # 下一个可用的函数调用index（用于没有index的情况）
    next_function_call_index: int = 0


class SequenceNumber:
    def __init__(self):
        self._sequence_number = 0

    def get_and_increment(self) -> int:
        num = self._sequence_number
        self._sequence_number += 1
        return num


class ChatCmplStreamHandler:
    @classmethod
    async def handle_stream(
        cls,
        response: Response,
        stream: AsyncStream[LiChatCompletionChunk],
    ) -> AsyncIterator[TResponseStreamEvent]:
        usage: LiCompletionUsage | None = None
        state = StreamingState()
        sequence_number = SequenceNumber()
        async for chunk in stream:
            if not state.started:
                state.started = True
                yield ResponseCreatedEvent(
                    response=response,
                    type="response.created",
                    sequence_number=sequence_number.get_and_increment(),
                )

            # This is always set by the OpenAI API, but not by others e.g. LiteLLM
            usage = chunk.usage if hasattr(chunk, "usage") else None

            if not chunk.choices or not chunk.choices[0].delta:
                continue

            delta = chunk.choices[0].delta

            # Handle reasoning content
            if hasattr(delta, "reasoning_content"):
                reasoning_content = delta.reasoning_content

                # Extract text content from reasoning_content
                reasoning_text = ""
                signature = ""
                if reasoning_content:
                    if isinstance(reasoning_content, str):
                        reasoning_text = reasoning_content
                    elif isinstance(reasoning_content, LiReasoningContent):
                        # Extract text from ReasoningContent object
                        if reasoning_content.thinking:
                            reasoning_text = reasoning_content.thinking
                        elif reasoning_content.data:
                            reasoning_text = reasoning_content.data
                        elif reasoning_content.signature:
                            signature += reasoning_content.signature

                        # If neither thinking nor data is available, use empty string

                if signature:
                    state.reasoning_content_index_and_output[1].encrypted_content = (
                        signature
                    )

                if reasoning_text and not state.reasoning_content_index_and_output:
                    state.reasoning_content_index_and_output = (
                        0,
                        ResponseReasoningItem(
                            id=FAKE_RESPONSES_ID,
                            summary=[Summary(text="", type="summary_text")],
                            type="reasoning",
                        ),
                    )
                    yield ResponseOutputItemAddedEvent(
                        item=ResponseReasoningItem(
                            id=FAKE_RESPONSES_ID,
                            summary=[Summary(text="", type="summary_text")],
                            type="reasoning",
                        ),
                        output_index=0,
                        type="response.output_item.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )

                    yield ResponseReasoningSummaryPartAddedEvent(
                        item_id=FAKE_RESPONSES_ID,
                        output_index=0,
                        summary_index=0,
                        part=AddedEventPart(text="", type="summary_text"),
                        type="response.reasoning_summary_part.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )

                if reasoning_text and state.reasoning_content_index_and_output:
                    yield ResponseReasoningSummaryTextDeltaEvent(
                        delta=reasoning_text,
                        item_id=FAKE_RESPONSES_ID,
                        output_index=0,
                        summary_index=0,
                        type="response.reasoning_summary_text.delta",
                        sequence_number=sequence_number.get_and_increment(),
                    )

                    # Create a new summary with updated text
                    current_summary = state.reasoning_content_index_and_output[1].summary[0]
                    updated_text = current_summary.text + reasoning_text
                    new_summary = Summary(text=updated_text, type="summary_text")
                    state.reasoning_content_index_and_output[1].summary[0] = new_summary

            # Handle regular content
            if delta.content is not None:
                if not state.text_content_index_and_output:
                    content_index = 0
                    if state.reasoning_content_index_and_output:
                        content_index += 1
                    if state.refusal_content_index_and_output:
                        content_index += 1

                    state.text_content_index_and_output = (
                        content_index,
                        ResponseOutputText(
                            text="",
                            type="output_text",
                            annotations=[],
                        ),
                    )
                    # Start a new assistant message stream
                    assistant_item = ResponseOutputMessage(
                        id=FAKE_RESPONSES_ID,
                        content=[],
                        role="assistant",
                        type="message",
                        status="in_progress",
                    )
                    # Notify consumers of the start of a new output message + first content part
                    yield ResponseOutputItemAddedEvent(
                        item=assistant_item,
                        output_index=state.reasoning_content_index_and_output
                        is not None,  # fixed 0 -> 0 or 1
                        type="response.output_item.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )
                    yield ResponseContentPartAddedEvent(
                        content_index=state.text_content_index_and_output[0],
                        item_id=FAKE_RESPONSES_ID,
                        output_index=state.reasoning_content_index_and_output
                        is not None,  # fixed 0 -> 0 or 1
                        part=ResponseOutputText(
                            text="",
                            type="output_text",
                            annotations=[],
                        ),
                        type="response.content_part.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )
                # Emit the delta for this segment of content
                yield ResponseTextDeltaEvent(
                    content_index=state.text_content_index_and_output[0],
                    delta=delta.content,
                    item_id=FAKE_RESPONSES_ID,
                    output_index=state.reasoning_content_index_and_output
                    is not None,  # fixed 0 -> 0 or 1
                    type="response.output_text.delta",
                    sequence_number=sequence_number.get_and_increment(),
                    logprobs=[],
                )
                # Accumulate the text into the response part
                state.text_content_index_and_output[1].text += delta.content

            # Handle refusals (model declines to answer)
            # This is always set by the OpenAI API, but not by others e.g. LiteLLM
            if hasattr(delta, "refusal") and delta.refusal:
                if not state.refusal_content_index_and_output:
                    refusal_index = 0
                    if state.reasoning_content_index_and_output:
                        refusal_index += 1
                    if state.text_content_index_and_output:
                        refusal_index += 1

                    state.refusal_content_index_and_output = (
                        refusal_index,
                        ResponseOutputRefusal(refusal="", type="refusal"),
                    )
                    # Start a new assistant message if one doesn't exist yet (in-progress)
                    assistant_item = ResponseOutputMessage(
                        id=FAKE_RESPONSES_ID,
                        content=[],
                        role="assistant",
                        type="message",
                        status="in_progress",
                    )
                    # Notify downstream that assistant message + first content part are starting
                    yield ResponseOutputItemAddedEvent(
                        item=assistant_item,
                        output_index=state.reasoning_content_index_and_output
                        is not None,  # fixed 0 -> 0 or 1
                        type="response.output_item.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )
                    yield ResponseContentPartAddedEvent(
                        content_index=state.refusal_content_index_and_output[0],
                        item_id=FAKE_RESPONSES_ID,
                        output_index=state.reasoning_content_index_and_output
                        is not None,  # fixed 0 -> 0 or 1
                        part=ResponseOutputText(
                            text="",
                            type="output_text",
                            annotations=[],
                        ),
                        type="response.content_part.added",
                        sequence_number=sequence_number.get_and_increment(),
                    )
                # Emit the delta for this segment of refusal
                yield ResponseRefusalDeltaEvent(
                    content_index=state.refusal_content_index_and_output[0],
                    delta=delta.refusal,
                    item_id=FAKE_RESPONSES_ID,
                    output_index=state.reasoning_content_index_and_output
                    is not None,  # fixed 0 -> 0 or 1
                    type="response.refusal.delta",
                    sequence_number=sequence_number.get_and_increment(),
                )
                # Accumulate the refusal string in the output part
                state.refusal_content_index_and_output[1].refusal += delta.refusal

            # Handle tool calls
            # Because we don't know the name of the function until the end of the stream, we'll
            # save everything and yield events at the end
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    # 确定使用的index
                    if tc_delta.index is not None:
                        # 原有逻辑：使用提供的index
                        index = tc_delta.index
                    elif tc_delta.id and tc_delta.id in state.call_id_to_index:
                        # 已存在的call_id，使用已分配的index
                        index = state.call_id_to_index[tc_delta.id]
                    elif tc_delta.id:
                        # 新的call_id，分配新的index
                        index = state.next_function_call_index
                        state.call_id_to_index[tc_delta.id] = index
                        state.next_function_call_index += 1
                    else:
                        # 既没有index也没有id，使用默认index（这种情况较少见）
                        if state.function_calls:
                            index = max(state.function_calls.keys())
                        else:
                            # 如果还没有function call，使用0并标记下一个为1
                            index = 0
                            state.next_function_call_index = 1

                    # 使用确定的index处理function call
                    if index not in state.function_calls:
                        state.function_calls[index] = ResponseFunctionToolCall(
                            id=FAKE_RESPONSES_ID,
                            arguments="",
                            name="",
                            type="function_call",
                            call_id="",
                        )
                    tc_function = tc_delta.function

                    state.function_calls[index].arguments += (
                        tc_function.arguments if tc_function else ""
                    ) or ""
                    state.function_calls[index].name += (
                        tc_function.name if tc_function else ""
                    ) or ""
                    state.function_calls[index].call_id += tc_delta.id if tc_delta.id else ""

        if state.reasoning_content_index_and_output:
            yield ResponseReasoningSummaryPartDoneEvent(
                item_id=FAKE_RESPONSES_ID,
                output_index=0,
                summary_index=0,
                part=DoneEventPart(
                    text=state.reasoning_content_index_and_output[1].summary[0].text,
                    type="summary_text",
                ),
                type="response.reasoning_summary_part.done",
                sequence_number=sequence_number.get_and_increment(),
            )
            yield ResponseOutputItemDoneEvent(
                item=state.reasoning_content_index_and_output[1],
                output_index=0,
                type="response.output_item.done",
                sequence_number=sequence_number.get_and_increment(),
            )

        function_call_starting_index = 0
        if state.reasoning_content_index_and_output:
            function_call_starting_index += 1

        if state.text_content_index_and_output:
            function_call_starting_index += 1
            # Send end event for this content part
            yield ResponseContentPartDoneEvent(
                content_index=state.text_content_index_and_output[0],
                item_id=FAKE_RESPONSES_ID,
                output_index=state.reasoning_content_index_and_output
                is not None,  # fixed 0 -> 0 or 1
                part=state.text_content_index_and_output[1],
                type="response.content_part.done",
                sequence_number=sequence_number.get_and_increment(),
            )

        if state.refusal_content_index_and_output:
            function_call_starting_index += 1
            # Send end event for this content part
            yield ResponseContentPartDoneEvent(
                content_index=state.refusal_content_index_and_output[0],
                item_id=FAKE_RESPONSES_ID,
                output_index=state.reasoning_content_index_and_output
                is not None,  # fixed 0 -> 0 or 1
                part=state.refusal_content_index_and_output[1],
                type="response.content_part.done",
                sequence_number=sequence_number.get_and_increment(),
            )

        # Actually send events for the function calls
        for function_call in state.function_calls.values():
            # First, a ResponseOutputItemAdded for the function call
            yield ResponseOutputItemAddedEvent(
                item=ResponseFunctionToolCall(
                    id=FAKE_RESPONSES_ID,
                    call_id=function_call.call_id,
                    arguments=function_call.arguments,
                    name=function_call.name,
                    type="function_call",
                ),
                output_index=function_call_starting_index,
                type="response.output_item.added",
                sequence_number=sequence_number.get_and_increment(),
            )
            # Then, yield the args
            yield ResponseFunctionCallArgumentsDeltaEvent(
                delta=function_call.arguments,
                item_id=FAKE_RESPONSES_ID,
                output_index=function_call_starting_index,
                type="response.function_call_arguments.delta",
                sequence_number=sequence_number.get_and_increment(),
            )
            # Finally, the ResponseOutputItemDone
            yield ResponseOutputItemDoneEvent(
                item=ResponseFunctionToolCall(
                    id=FAKE_RESPONSES_ID,
                    call_id=function_call.call_id,
                    arguments=function_call.arguments,
                    name=function_call.name,
                    type="function_call",
                ),
                output_index=function_call_starting_index,
                type="response.output_item.done",
                sequence_number=sequence_number.get_and_increment(),
            )

        # Finally, send the Response completed event
        outputs: list[ResponseOutputItem] = []

        # include Reasoning item if it exists
        if state.reasoning_content_index_and_output:
            outputs.append(state.reasoning_content_index_and_output[1])

        # include text or refusal content if they exist
        if state.text_content_index_and_output or state.refusal_content_index_and_output:
            assistant_msg = ResponseOutputMessage(
                id=FAKE_RESPONSES_ID,
                content=[],
                role="assistant",
                type="message",
                status="completed",
            )
            if state.text_content_index_and_output:
                assistant_msg.content.append(state.text_content_index_and_output[1])
            if state.refusal_content_index_and_output:
                assistant_msg.content.append(state.refusal_content_index_and_output[1])
            outputs.append(assistant_msg)

            # send a ResponseOutputItemDone for the assistant message
            yield ResponseOutputItemDoneEvent(
                item=assistant_msg,
                output_index=state.reasoning_content_index_and_output
                is not None,  # fixed 0 -> 0 or 1
                type="response.output_item.done",
                sequence_number=sequence_number.get_and_increment(),
            )

        for function_call in state.function_calls.values():
            outputs.append(function_call)

        final_response = response.model_copy()
        final_response.output = outputs
        final_response.usage = (
            ResponseUsage(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                output_tokens_details=OutputTokensDetails(
                    reasoning_tokens=usage.completion_tokens_details.reasoning_tokens
                    if usage.completion_tokens_details
                    and usage.completion_tokens_details.reasoning_tokens
                    else 0
                ),
                input_tokens_details=InputTokensDetails(
                    cached_tokens=usage.prompt_tokens_details.cached_tokens
                    if usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens
                    else 0
                ),
            )
            if usage
            else None
        )

        yield ResponseCompletedEvent(
            response=final_response,
            type="response.completed",
            sequence_number=sequence_number.get_and_increment(),
        )
