"""Unit tests for the shared stream-event translator (TurnEvent)."""

import pytest
from types import SimpleNamespace
from typing import Any

from agents import RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
from openai.types.responses import (
    ResponseApplyPatchToolCall,
    ResponseApplyPatchToolCallOutput,
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

from siada.entrypoint.runtime.turn_event import (
    CONTENT_PART_ADDED,
    CONTENT_PART_DONE,
    REASONING_DELTA,
    REASONING_PART_ADDED,
    RESPONSE_COMPLETED,
    RESPONSE_CREATED,
    TEXT_DELTA,
    TOOL_ARGS_DELTA,
    TOOL_CALL_DONE,
    TOOL_CALL_START,
    TOOL_OUTPUT,
    TurnEvent,
    classify_stream_event,
    translate_stream_events,
)
from siada.tools.coder.apply_patch_presentation import APPLY_PATCH_CUSTOM_DATA_KEY

_BASE = dict(logprobs=[], sequence_number=0)


class _DummyAgent:
    """ToolCallOutputItem.__post_init__ builds a weak reference to the agent,
    which requires a weakref-able instance (not None / SimpleNamespace)."""


def _raw(data: Any) -> RawResponsesStreamEvent:
    return RawResponsesStreamEvent(data=data)


def _tool_call() -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id="item_1", call_id="call_1", name="run_cmd",
        arguments='{"cmd":"ls"}', type="function_call", status="completed",
    )


def _apply_patch_call() -> ResponseApplyPatchToolCall:
    return ResponseApplyPatchToolCall.model_construct(
        id="item_patch_1", call_id="call_patch_1",
        operation={"type": "update_file", "path": "src/service.py", "diff": "@@\n"},
        status="completed", type="apply_patch_call",
    )


def test_text_delta_translates_with_delta_payload():
    event = _raw(ResponseTextDeltaEvent(
        type="response.output_text.delta", item_id="i1",
        output_index=0, content_index=0, delta="hello", **_BASE,
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(kind=TEXT_DELTA, delta="hello")


def test_reasoning_delta_translates_with_delta_payload():
    event = _raw(ResponseReasoningSummaryTextDeltaEvent(
        type="response.reasoning_summary_text.delta", item_id="i2",
        output_index=0, summary_index=0, delta="think", **_BASE,
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(kind=REASONING_DELTA, delta="think")


def test_tool_call_start_carries_call_id_item_id_and_name():
    event = _raw(ResponseOutputItemAddedEvent(
        type="response.output_item.added", output_index=0,
        item=_tool_call(), sequence_number=0,
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(
        kind=TOOL_CALL_START, call_id="call_1", item_id="item_1", name="run_cmd",
    )


def test_tool_args_delta_routes_by_item_id():
    event = _raw(ResponseFunctionCallArgumentsDeltaEvent(
        type="response.function_call_arguments.delta", item_id="item_1",
        output_index=0, delta='{"cmd"', sequence_number=0,
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(kind=TOOL_ARGS_DELTA, item_id="item_1", delta='{"cmd"')


def test_tool_call_done_carries_full_arguments_from_sdk_item():
    event = _raw(ResponseOutputItemDoneEvent(
        type="response.output_item.done", output_index=0,
        item=_tool_call(), sequence_number=0,
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(
        kind=TOOL_CALL_DONE, call_id="call_1", name="run_cmd",
        arguments='{"cmd":"ls"}',
    )


def test_tool_output_translates_with_raw_observation():
    # ToolCallOutputItem.__post_init__ builds a weak reference to the agent,
    # so a plain object (not None) must be passed.
    item = ToolCallOutputItem(
        agent=_DummyAgent(), raw_item={"call_id": "call_1"}, output="the output",
    )
    te = classify_stream_event(RunItemStreamEvent(name="tool_call_output", item=item))
    assert te == TurnEvent(kind=TOOL_OUTPUT, call_id="call_1", output="the output")


def test_marker_events_translate_without_payload():
    created = classify_stream_event(_raw(ResponseCreatedEvent.model_construct(response=None)))
    assert created == TurnEvent(kind=RESPONSE_CREATED)
    reasoning_part = classify_stream_event(
        _raw(ResponseReasoningSummaryPartAddedEvent.model_construct())
    )
    assert reasoning_part == TurnEvent(kind=REASONING_PART_ADDED)
    content_part = classify_stream_event(
        _raw(ResponseContentPartAddedEvent.model_construct())
    )
    assert content_part == TurnEvent(kind=CONTENT_PART_ADDED)
    content_done = classify_stream_event(
        _raw(ResponseContentPartDoneEvent.model_construct())
    )
    assert content_done == TurnEvent(kind=CONTENT_PART_DONE)


def test_response_completed_extracts_usage():
    event = _raw(ResponseCompletedEvent.model_construct(
        response=SimpleNamespace(usage="usage-object"),
    ))
    te = classify_stream_event(event)
    assert te == TurnEvent(kind=RESPONSE_COMPLETED, usage="usage-object")


def test_irrelevant_events_translate_to_none():
    unknown_raw = _raw(SimpleNamespace(unrelated=True))
    assert classify_stream_event(unknown_raw) is None
    # Output item added/done for a NON function-tool-call item is irrelevant.
    plain_item = SimpleNamespace(id="item_2", call_id=None, name=None, arguments=None)
    added = _raw(ResponseOutputItemAddedEvent.model_construct(item=plain_item, output_index=0))
    assert classify_stream_event(added) is None
    # Non-ToolCallOutputItem run items are irrelevant.
    other_item = RunItemStreamEvent(name="message_output_created", item=SimpleNamespace())
    assert classify_stream_event(other_item) is None
    # A raw string is not a stream event at all.
    assert classify_stream_event("not-an-event") is None


def test_tool_output_without_call_id_translates_with_empty_call_id():
    """Frontends keep their own policy for call-id-less outputs, so the
    translator must not silently drop them."""
    item = ToolCallOutputItem(
        agent=_DummyAgent(), raw_item={"no_call_id": True}, output="out"
    )
    te = classify_stream_event(RunItemStreamEvent(name="tool_call_output", item=item))
    assert te == TurnEvent(kind=TOOL_OUTPUT, call_id="", output="out")
    non_dict_raw = ToolCallOutputItem(
        agent=_DummyAgent(), raw_item="not-a-dict", output="out"
    )
    te2 = classify_stream_event(
        RunItemStreamEvent(name="tool_call_output", item=non_dict_raw)
    )
    assert te2 == TurnEvent(kind=TOOL_OUTPUT, call_id="", output="out")


def test_native_apply_patch_call_translates_with_raw_item():
    call = _apply_patch_call()
    added = _raw(ResponseOutputItemAddedEvent(
        type="response.output_item.added", output_index=0,
        item=call, sequence_number=0,
    ))
    te = classify_stream_event(added)

    assert te.kind == TOOL_CALL_START
    assert te.call_id == "call_patch_1"
    assert te.item_id == "item_patch_1"
    assert te.name == "apply_patch"
    assert te.is_apply_patch is True
    assert te.raw_item is call


def test_native_apply_patch_done_carries_completed_call_item():
    call = _apply_patch_call()
    done = _raw(ResponseOutputItemDoneEvent(
        type="response.output_item.done", output_index=0,
        item=call, sequence_number=1,
    ))
    te = classify_stream_event(done)

    assert te.kind == TOOL_CALL_DONE
    assert te.call_id == "call_patch_1"
    assert te.name == "apply_patch"
    assert te.is_apply_patch is True
    assert te.raw_item is call


def test_native_apply_patch_output_translates_with_custom_data():
    """The patch display renders from the SDK-collected editor text, which only
    the tool-output event carries."""
    custom_data = {APPLY_PATCH_CUSTOM_DATA_KEY: {"version": 1, "operations": []}}
    item = ToolCallOutputItem(
        agent=_DummyAgent(),
        raw_item={
            "type": "apply_patch_call_output",
            "call_id": "call_patch_1",
            "status": "completed",
        },
        output="Updated src/service.py",
        custom_data=custom_data,
    )
    te = classify_stream_event(RunItemStreamEvent(name="tool_call_output", item=item))

    assert te.kind == TOOL_OUTPUT
    assert te.call_id == "call_patch_1"
    assert te.is_apply_patch is True
    assert te.custom_data is custom_data
    assert te.output == "Updated src/service.py"


def test_native_apply_patch_output_model_keeps_call_id():
    """Newer Agents SDK builds hand the result over as an SDK model instead of
    a mapping; the call id must survive either shape."""
    raw_output = ResponseApplyPatchToolCallOutput.model_construct(
        id="item_patch_out_1", call_id="call_patch_1", status="completed",
        type="apply_patch_call_output", output="Updated src/service.py",
    )
    item = ToolCallOutputItem(
        agent=_DummyAgent(), raw_item=raw_output, output="Updated src/service.py",
    )
    te = classify_stream_event(RunItemStreamEvent(name="tool_call_output", item=item))

    assert te.kind == TOOL_OUTPUT
    assert te.call_id == "call_patch_1"
    assert te.is_apply_patch is True


async def _to_async_iter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_translate_stream_events_drops_irrelevant_and_keeps_order():
    text = _raw(ResponseTextDeltaEvent(
        type="response.output_text.delta", item_id="i1",
        output_index=0, content_index=0, delta="a", **_BASE,
    ))
    noise = _raw(SimpleNamespace(unrelated=True))
    tool_start = _raw(ResponseOutputItemAddedEvent(
        type="response.output_item.added", output_index=0,
        item=_tool_call(), sequence_number=0,
    ))
    translated = [
        te async for te in translate_stream_events(_to_async_iter([text, noise, tool_start]))
    ]
    assert [te.kind for te in translated] == [TEXT_DELTA, TOOL_CALL_START]
    assert translated[0].delta == "a"
    assert translated[1].name == "run_cmd"
