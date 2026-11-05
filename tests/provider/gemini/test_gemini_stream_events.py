import json
from unittest.mock import Mock

import pytest
from agents import RawResponsesStreamEvent
from agents.exceptions import ModelBehaviorError

from siada.provider.gemini import GeminiModel
from siada.provider.gemini.replay import decode_replay
from tests.entrypoint.interaction.test_conversation_turn_native_apply_patch import _FakeResult, _RecordingIO, _turn

from test_gemini_model import native_response, request_args, sse


@pytest.mark.asyncio
async def test_native_text_and_reasoning_have_complete_part_lifecycles(endpoint, client):
    endpoint.responses = [(200, sse(
        native_response([{"text": "think", "thought": True}], finish=None),
        native_response([{"text": "answer"}], finish=None),
        native_response([{"text": " more"}]),
        native_response([{"thoughtSignature": "dGFpbA=="}], finish=None),
    ))]
    events = [event async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]

    assert [event.sequence_number for event in events] == list(range(len(events)))
    assert events[0].type == "response.created"
    assert events[-1].type == "response.completed"
    for index, item in enumerate(events[-1].response.output):
        related = [event for event in events if getattr(event, "output_index", None) == index]
        assert related[0].type == "response.output_item.added"
        assert related[-1].type == "response.output_item.done"
        assert related[-1].item == item
        if item.type == "message":
            assert related[0].item.content == []
            assert [event.type for event in related[1:-1]] == [
                "response.content_part.added", "response.output_text.delta", "response.output_text.delta",
                "response.output_text.done", "response.content_part.done",
            ]
            assert related[1].part.text == ""
            assert related[-3].text == related[-2].part.text == "answer more"
            assert decode_replay(item)["parts"][-1]["part"]["thought_signature"] == "dGFpbA=="
        else:
            assert related[0].item.summary == []
            assert [event.type for event in related[1:-1]] == [
                "response.reasoning_summary_part.added", "response.reasoning_summary_text.delta",
                "response.reasoning_summary_text.done", "response.reasoning_summary_part.done",
            ]
            assert related[1].part.text == ""
            assert related[-3].text == related[-2].part.text == "think"
        assert all(getattr(event, "item_id", item.id) == item.id for event in related)


@pytest.mark.asyncio
async def test_complete_native_function_args_map_to_one_delta_and_done(endpoint, client):
    arguments = {"command": "echo 完成"}
    endpoint.responses = [(200, sse(
        native_response([{"functionCall": {"name": "run_cmd", "args": arguments}}]),
        native_response([{"thoughtSignature": "dGFpbA=="}], finish=None),
    ))]
    events = [event async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]

    assert [event.type for event in events] == [
        "response.created", "response.output_item.added", "response.function_call_arguments.delta",
        "response.function_call_arguments.done", "response.output_item.done", "response.completed",
    ]
    started, delta, args_done, completed = events[1:5]
    assert started.item.arguments == ""
    assert started.item.status == "in_progress"
    assert delta.item_id == args_done.item_id == completed.item.id == started.item.id
    assert delta.delta == args_done.arguments == completed.item.arguments
    assert json.loads(delta.delta) == arguments
    assert args_done.name == "run_cmd"
    assert decode_replay(completed.item)["parts"][-1]["part"]["thought_signature"] == "dGFpbA=="
    assert events[-1].response.output == [completed.item]


@pytest.mark.asyncio
async def test_text_part_boundaries_initialize_and_finalize_pretty_terminal(endpoint, client):
    endpoint.responses = [(200, sse(native_response([{"text": "visible answer"}])))]
    events = [RawResponsesStreamEvent(data=event) async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]
    io = _RecordingIO()
    io.pretty = True
    turn = _turn(io)
    turn.mdstream = None
    mdstream = Mock()
    turn.get_response_mdstream = Mock(return_value=mdstream)
    turn._print_context_usage = Mock()

    await turn.output_stream_content(_FakeResult(events))

    turn.get_response_mdstream.assert_called_once()
    assert mdstream.update.call_count == 2
    assert mdstream.update.call_args.args[1] is True
    assert "visible answer" in mdstream.update.call_args.args[0]
    assert turn.mdstream is None
    assert turn._current_message_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("call_first", [False, True])
async def test_text_finishes_before_tool_display_without_reordering_native_output(endpoint, client, call_first):
    call = {"functionCall": {"name": "run_cmd", "args": {"command": "echo synthetic"}}}
    text = {"text": "visible answer"}
    parts = [call, text] if call_first else [text, call]
    endpoint.responses = [(200, sse(native_response(parts)))]
    events = [event async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]
    text_done = next(index for index, event in enumerate(events) if event.type == "response.content_part.done")
    call_started = next(index for index, event in enumerate(events) if event.type == "response.output_item.added" and event.item.type == "function_call")

    assert text_done < call_started
    output = events[-1].response.output
    assert [item.type for item in output] == (["function_call", "message"] if call_first else ["message", "function_call"])
    for index, item in enumerate(output):
        done = next(event for event in events if event.type == "response.output_item.done" and event.output_index == index)
        assert done.item == item
        assert decode_replay(item)["parts"][0]["part_index"] == index


@pytest.mark.asyncio
@pytest.mark.parametrize("part", [{"text": ""}, {"thoughtSignature": "dGFpbA=="}])
async def test_empty_text_and_signature_only_parts_keep_valid_event_boundaries(endpoint, client, part):
    endpoint.responses = [(200, sse(native_response([part])))]
    events = [event async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]
    item = events[-1].response.output[0]

    assert events[0].type == "response.created"
    assert events[-2].type == "response.output_item.done"
    assert events[-1].type == "response.completed"
    assert not any(event.type == "response.output_text.delta" for event in events)
    part_events = [event for event in events if event.type.startswith("response.content_part.")]
    assert len(part_events) == (2 if "text" in part else 0)
    assert decode_replay(item)["parts"][0]["part"] == ({"text": ""} if "text" in part else {"thought_signature": "dGFpbA=="})


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [
    {"name": "run_cmd", "willContinue": True},
    {"name": "run_cmd", "partialArgs": [{"jsonPath": "$.command", "stringValue": "echo"}], "willContinue": False},
])
async def test_unsupported_partial_function_calls_never_publish_tool_events(endpoint, client, call):
    endpoint.responses = [(200, sse(native_response([{"functionCall": call}])))]
    events = []
    with pytest.raises(ModelBehaviorError, match="incomplete function call"):
        async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args()):
            events.append(event)
    assert [event.type for event in events] == ["response.created"]


@pytest.mark.asyncio
@pytest.mark.parametrize("part", [
    {"executableCode": {"language": "PYTHON", "code": "print('synthetic')"}},
    {"codeExecutionResult": {"outcome": "OUTCOME_OK", "output": "synthetic"}},
    {"functionResponse": {"name": "synthetic", "response": {"output": "synthetic"}}},
    {"inlineData": {"mimeType": "image/png", "data": "c3ludGhldGlj"}},
    {"fileData": {"mimeType": "image/png", "fileUri": "gs://synthetic/file"}},
    {"toolCall": {"id": "synthetic", "args": {}}},
])
async def test_unsupported_native_parts_fail_explicitly_instead_of_being_dropped(endpoint, client, part):
    endpoint.responses = [(200, sse(native_response([part])))]
    events = []
    with pytest.raises(ModelBehaviorError, match="unsupported output Part"):
        async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args()):
            events.append(event)
    assert [event.type for event in events] == ["response.created"]
