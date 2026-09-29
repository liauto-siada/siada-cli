"""Surface-neutral translation of agent stream events into TurnEvents.

Every frontend that renders a streaming agent turn — the terminal
``ConversationTurn.output_stream_content``, the Lark ``LarkStreamConsumer``
and the ACP runtime's ``_stream_turn`` — used to carry its own
isinstance-dispatch over the ``agents``/``openai`` stream-event types. This
module is the single source of that classification: ``classify_stream_event``
turns one SDK stream event into at most one :class:`TurnEvent`; each frontend
keeps its own rendering state machine but dispatches on ``TurnEvent.kind``
instead of SDK types.

Surfaces that need per-raw-event side hooks (e.g. the terminal stops its
waiting spinner on EVERY raw event) should iterate the raw stream themselves
and call ``classify_stream_event`` per event; ``translate_stream_events`` is
the convenience wrapper for surfaces without such hooks.
"""

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

# TurnEvent kinds — one per SDK event shape the frontends consume.
RESPONSE_CREATED = "response_created"
REASONING_PART_ADDED = "reasoning_part_added"
REASONING_DELTA = "reasoning_delta"
CONTENT_PART_ADDED = "content_part_added"
TEXT_DELTA = "text_delta"
CONTENT_PART_DONE = "content_part_done"
TOOL_CALL_START = "tool_call_start"
TOOL_ARGS_DELTA = "tool_args_delta"
TOOL_CALL_DONE = "tool_call_done"
RESPONSE_COMPLETED = "response_completed"
TOOL_OUTPUT = "tool_output"


@dataclass(frozen=True)
class TurnEvent:
    """One surface-neutral stream event.

    Only the fields relevant to ``kind`` are populated. The raw SDK event
    objects are deliberately NOT carried along so frontends stay decoupled
    from the ``agents``/``openai`` event types — with two exceptions:
    ``output`` holds the raw observation object for ``TOOL_OUTPUT``, because
    tool outputs are rendered from the observation itself (text, images,
    FunctionCallResult subclasses with their own display formatting); and the
    native Responses apply_patch events carry what
    ``siada.tools.coder.apply_patch_presentation`` renders — ``raw_item`` is
    the call item whose ``operation`` feeds the fallback render, and
    ``custom_data`` is the SDK-only payload recording the file text the local
    editor actually applied.
    """

    kind: str
    delta: str = ""        # REASONING_DELTA / TEXT_DELTA / TOOL_ARGS_DELTA
    call_id: str = ""      # TOOL_CALL_START / TOOL_CALL_DONE / TOOL_OUTPUT
    item_id: str = ""      # TOOL_CALL_START / TOOL_ARGS_DELTA
    name: str = ""         # TOOL_CALL_START / TOOL_CALL_DONE
    arguments: str = ""    # TOOL_CALL_DONE: full args string from the SDK item
    output: Any = None     # TOOL_OUTPUT: raw observation object
    usage: Any = None      # RESPONSE_COMPLETED
    # Native apply_patch: set on the call events (TOOL_CALL_START /
    # TOOL_CALL_DONE) and on the result event (TOOL_OUTPUT). A native patch
    # call has no JSON ``arguments``; its render fallback needs the call item.
    is_apply_patch: bool = False
    raw_item: Any = None     # TOOL_CALL_START / TOOL_CALL_DONE: SDK call item
    custom_data: Any = None  # TOOL_OUTPUT: SDK-collected apply_patch payload


def classify_stream_event(event: Any) -> Optional[TurnEvent]:
    """Classify one agent stream event into a TurnEvent.

    Returns None for event shapes no frontend renders (unknown raw events,
    output items that are neither function tool calls nor native apply_patch
    calls, non-ToolCallOutputItem run items). Call-id-less tool outputs DO
    translate (with ``call_id=""``) so each frontend keeps its own policy for
    them.
    """
    from agents import RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
    from openai.types.responses import (
        ResponseCompletedEvent,
        ResponseContentPartAddedEvent,
        ResponseContentPartDoneEvent,
        ResponseCreatedEvent,
        ResponseFunctionCallArgumentsDeltaEvent,
        ResponseFunctionToolCall,
        ResponseOutputItemAddedEvent,
        ResponseOutputItemDoneEvent,
        ResponseReasoningSummaryPartAddedEvent,
        ResponseReasoningSummaryTextDeltaEvent,
        ResponseTextDeltaEvent,
    )
    from siada.tools.coder.apply_patch_presentation import (
        is_apply_patch_call,
        is_apply_patch_output,
    )

    if isinstance(event, RawResponsesStreamEvent):
        data = event.data
        if isinstance(data, ResponseCreatedEvent):
            return TurnEvent(kind=RESPONSE_CREATED)
        if isinstance(data, ResponseReasoningSummaryPartAddedEvent):
            return TurnEvent(kind=REASONING_PART_ADDED)
        if isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
            return TurnEvent(kind=REASONING_DELTA, delta=data.delta)
        if isinstance(data, ResponseContentPartAddedEvent):
            return TurnEvent(kind=CONTENT_PART_ADDED)
        if isinstance(data, ResponseTextDeltaEvent):
            return TurnEvent(kind=TEXT_DELTA, delta=data.delta)
        if isinstance(data, ResponseContentPartDoneEvent):
            return TurnEvent(kind=CONTENT_PART_DONE)
        if isinstance(data, ResponseOutputItemAddedEvent) and isinstance(
            data.item, ResponseFunctionToolCall
        ):
            return TurnEvent(
                kind=TOOL_CALL_START,
                call_id=data.item.call_id,
                item_id=data.item.id,
                name=data.item.name,
            )
        if isinstance(data, ResponseOutputItemAddedEvent) and is_apply_patch_call(
            data.item
        ):
            # A native apply_patch call carries an ``operation`` instead of JSON
            # ``arguments``; frontends keep the call item and render the patch
            # once its output arrives.
            return TurnEvent(
                kind=TOOL_CALL_START,
                call_id=data.item.call_id,
                item_id=data.item.id,
                name="apply_patch",
                is_apply_patch=True,
                raw_item=data.item,
            )
        if isinstance(data, ResponseFunctionCallArgumentsDeltaEvent):
            return TurnEvent(
                kind=TOOL_ARGS_DELTA, item_id=data.item_id, delta=data.delta
            )
        if isinstance(data, ResponseOutputItemDoneEvent) and isinstance(
            data.item, ResponseFunctionToolCall
        ):
            return TurnEvent(
                kind=TOOL_CALL_DONE,
                call_id=data.item.call_id,
                name=data.item.name,
                arguments=data.item.arguments,
            )
        if isinstance(data, ResponseOutputItemDoneEvent) and is_apply_patch_call(
            data.item
        ):
            # The completed item's operation is authoritative for the fallback
            # render when the SDK carried no custom display data.
            return TurnEvent(
                kind=TOOL_CALL_DONE,
                call_id=data.item.call_id,
                name="apply_patch",
                is_apply_patch=True,
                raw_item=data.item,
            )
        if isinstance(data, ResponseCompletedEvent):
            usage = data.response.usage if getattr(data, "response", None) else None
            return TurnEvent(kind=RESPONSE_COMPLETED, usage=usage)
        return None

    if isinstance(event, RunItemStreamEvent) and isinstance(event.item, ToolCallOutputItem):
        raw_item = event.item.raw_item
        if is_apply_patch_output(raw_item):
            # Native apply_patch results are SDK models in current Agents SDK
            # builds and plain mappings in older ones; beyond the call id only
            # the SDK-collected display payload matters.
            call_id = (
                raw_item.get("call_id")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "call_id", None)
            )
            return TurnEvent(
                kind=TOOL_OUTPUT,
                call_id=call_id or "",
                output=event.item.output,
                is_apply_patch=True,
                custom_data=getattr(event.item, "custom_data", None),
            )
        call_id = raw_item.get("call_id") if isinstance(raw_item, dict) else None
        return TurnEvent(kind=TOOL_OUTPUT, call_id=call_id or "", output=event.item.output)
    return None


async def translate_stream_events(
    events: AsyncIterator[Any],
) -> AsyncIterator[TurnEvent]:
    """Yield the TurnEvents of an agent stream, dropping irrelevant events."""
    async for event in events:
        turn_event = classify_stream_event(event)
        if turn_event is not None:
            yield turn_event
