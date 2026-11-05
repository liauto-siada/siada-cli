"""Edit argument completion and execution results share a stable ACP call identity."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from agents import Agent, RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
from openai.types.responses import (
    Response,
    ResponseCreatedEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
)

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.tools.coder.file_edit_presentation import FILE_EDIT_START, FILE_EDIT_END


def _data(content: str) -> dict:
    return json.loads(content.split(FILE_EDIT_START, 1)[1].split(FILE_EDIT_END, 1)[0])


def _created():
    response = Response.model_construct(id="synthetic-response", model="synthetic-model")
    return RawResponsesStreamEvent(data=ResponseCreatedEvent.model_construct(
        response=response, sequence_number=0, type="response.created",
    ))


def _call(call_id: str, *, truncated: bool = False):
    args = json.dumps({"command": "str_replace", "path": "example.rs", "old_str": "old", "new_str": "new"})
    if truncated:
        args = args[:-3]
    item = ResponseFunctionToolCall.model_construct(
        id=f"item-{call_id}", call_id=call_id, name="edit_file", arguments=args,
        type="function_call", status="completed",
    )
    return [
        RawResponsesStreamEvent(data=ResponseOutputItemAddedEvent.model_construct(
            item=item, output_index=0, sequence_number=1, type="response.output_item.added",
        )),
        RawResponsesStreamEvent(data=ResponseOutputItemDoneEvent.model_construct(
            item=item, output_index=0, sequence_number=2, type="response.output_item.done",
        )),
    ]


def _output(call_id: str, output):
    return RunItemStreamEvent(name="tool_output", item=ToolCallOutputItem(
        agent=Agent(name="file-edit-render-test"), output=output,
        raw_item={"type": "function_call_output", "call_id": call_id, "output": str(output)},
    ))


class _Result:
    def __init__(self, events, *, cancelled: bool = False):
        self.events = events
        self.cancelled = cancelled

    async def stream_events(self):
        for event in self.events:
            yield event
        if self.cancelled:
            raise asyncio.CancelledError()


def _turn():
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(io=SimpleNamespace(acp_enabled=True, pretty=False),
                                  llm_config=SimpleNamespace(model_name="synthetic-model"))
    turn.session = SimpleNamespace(spinner=None, state=SimpleNamespace(spinner=None, usage=None))
    turn._message_counter = 0
    turn._current_message_id = None
    turn._stream_start_id = None
    turn.current_result = None
    events = []
    turn._send_lifecycle_event = events.append
    return turn, events


@pytest.mark.parametrize("truncated,output,expected", [
    (True, "An error occurred while running the tool. Error: Invalid JSON input for tool edit_file", "failed"),
    (False, "ERROR: No match.", "failed"),
    (False, "Hook blocked this tool call.", "failed"),
    (False, "The file example.rs has been edited. Check the changes.", "completed"),
])
def test_done_arguments_are_authoritative_and_execution_updates_same_call(truncated, output, expected):
    turn, events = _turn()
    # No arguments delta: call-done's full arguments must still reach the renderer.
    asyncio.run(turn.output_stream_content(_Result([_created(), *_call("call", truncated=truncated), _output("call", output)])))
    updates = [_data(event["delta"]) for event in events if event["type"] == "tool_use"]
    assert len(updates) == 2
    assert [update["callId"] for update in updates] == ["call", "call"]
    assert updates[-1]["status"] == expected
    assert updates[-1]["executionStatus"] == expected
    assert updates[-1]["argumentsComplete"] is not truncated
    if not truncated:
        assert updates[0]["status"] == "pending" and "newString" not in updates[0]
    if expected == "failed":
        assert "newString" not in updates[-1]
        if not truncated:
            assert updates[-1]["error"] == output
    assert all(event.get("chunk_index") == 0 for event in events if event["type"] == "tool_use")


def test_custom_result_text_survives_execution_update():
    turn, events = _turn()
    output = "Policy forbids editing this file."
    asyncio.run(turn.output_stream_content(_Result([_created(), *_call("call"), _output("call", output)])))
    updates = [_data(event["delta"]) for event in events if event["type"] == "tool_use"]
    assert updates[-1]["status"] == "unverified"
    assert output in updates[-1]["details"]
    assert "newString" not in updates[-1]


def test_results_are_correlated_for_interleaved_calls():
    turn, events = _turn()
    asyncio.run(turn.output_stream_content(_Result([
        _created(), *_call("a"), *_call("b"), _output("b", "File edited."), _output("a", "ERROR: No match."),
    ])))
    updates = [_data(event["delta"]) for event in events if event["type"] == "tool_use"]
    assert [(update["callId"], update["status"]) for update in updates] == [
        ("a", "pending"), ("b", "pending"), ("b", "completed"), ("a", "failed"),
    ]


@pytest.mark.parametrize("cancelled", [False, True])
def test_missing_result_finalizes_as_unverified_and_preserves_cancellation(cancelled):
    turn, events = _turn()
    operation = turn.output_stream_content(_Result([_created(), *_call("call")], cancelled=cancelled))
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(operation)
    else:
        asyncio.run(operation)
    updates = [_data(event["delta"]) for event in events if event["type"] == "tool_use"]
    assert [update["status"] for update in updates] == ["pending", "unverified"]
    assert "newString" not in updates[-1]
    assert updates[-1]["executionStatus"] == "unknown"
