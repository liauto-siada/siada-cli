"""Regression coverage for deployment disconnects after empty stream headers."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from agents import Agent, RunConfig, Runner
from openai import AsyncOpenAI

from siada.provider import retry
from siada.provider.responses.responses_model import ResponsesModel
from siada.services.model_wrapper import ModelWrapper

DISCONNECT = "peer closed connection without sending complete message body (incomplete chunked read)"


def _starts():
    return [
        {"type": "response.created"},
        {"type": "response.in_progress"},
        {"type": "response.output_item.added", "item": {
            "type": "reasoning", "summary": [],
        }},
        {"type": "response.reasoning_summary_part.added", "part": {
            "type": "summary_text", "text": "",
        }},
        {"type": "response.output_item.added", "item": {
            "type": "message", "role": "assistant", "status": "in_progress", "content": [],
        }},
        {"type": "response.content_part.added", "part": {
            "type": "output_text", "text": "", "annotations": [],
        }},
    ]


@pytest.fixture
def delays(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    monkeypatch.setattr(retry.random, "uniform", lambda *_: 0.5)
    return sleep


@pytest.mark.asyncio
@pytest.mark.parametrize("objects", [False, True])
@pytest.mark.parametrize("recover", [False, True])
async def test_disconnect_after_empty_start_retries_without_leaking_ids(objects, recover, delays):
    calls = []
    closed = []

    def convert(value):
        if objects and isinstance(value, dict):
            return SimpleNamespace(**{key: convert(item) for key, item in value.items()})
        return value

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        try:
            for event in _starts():
                yield convert({**event, "attempt": attempt})
            if not recover or attempt < 2:
                raise httpx.RemoteProtocolError(DISCONNECT)
            yield convert({"type": "response.output_text.delta", "delta": "ok", "attempt": attempt})
            yield convert({"type": "response.completed", "attempt": attempt})
        finally:
            closed.append(attempt)

    async def sleep(delay):
        assert closed == calls

    delays.side_effect = sleep
    events = []
    if recover:
        events = [event async for event in retry.retry_model_stream(stream)]
        assert len(events) == len(_starts()) + 2
        assert all(retry._field(event, "attempt") == 2 for event in events)
    else:
        with pytest.raises(httpx.RemoteProtocolError, match="incomplete chunked read"):
            async for event in retry.retry_model_stream(stream):
                events.append(event)
        assert events == []
    assert calls == closed == [0, 1, 2]
    assert [call.args[0] for call in delays.await_args_list] == [1.5, 2.5]


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"type": "response.output_text.delta", "delta": "partial"},
    {"type": "response.output_item.added", "item": {
        "type": "function_call", "name": "execute", "arguments": "", "call_id": "call-test",
    }},
    {"type": "response.output_item.added", "item": {
        "type": "message", "role": "assistant", "status": "in_progress",
        "content": [{"type": "output_text", "text": "already present"}],
    }},
    {"type": "response.content_part.added", "part": {
        "type": "output_text", "text": "present", "annotations": [],
    }},
    {"type": "response.custom_event"},
])
async def test_disconnect_after_content_or_tool_is_not_replayed(event, delays):
    calls = []

    async def stream():
        calls.append(1)
        yield _starts()[0]
        yield event
        raise httpx.RemoteProtocolError(DISCONNECT)

    events = []
    with pytest.raises(httpx.RemoteProtocolError):
        async for value in retry.retry_model_stream(stream):
            events.append(value)
    assert events == [_starts()[0], event]
    assert calls == [1]
    delays.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"type": "response.reasoning_summary_text.delta", "delta": "thinking"},
    {"type": "response.output_item.added", "item": {
        "type": "reasoning", "summary": [], "encrypted_content": "opaque-state",
    }},
])
async def test_disconnect_after_thinking_retries_with_fresh_lifecycle(event, delays):
    calls = []
    closed = []

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        try:
            yield {"type": "response.created", "attempt": attempt}
            yield event
            if attempt == 0:
                raise httpx.RemoteProtocolError(DISCONNECT)
            yield {"type": "response.completed"}
        finally:
            closed.append(attempt)

    events = [value async for value in retry.retry_model_stream(stream)]
    assert [value["attempt"] for value in events if value["type"] == "response.created"] == [0, 1]
    assert events.count(event) == 2
    assert events[-1]["type"] == "response.completed"
    assert calls == closed == [0, 1]
    delays.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_pending_headers_are_bounded_and_cancellation_during_backoff_aborts(delays):
    calls = []

    async def excessive_headers():
        calls.append(1)
        for _ in range(retry._MAX_PENDING_EVENTS + 1):
            yield _starts()[0]
        raise httpx.RemoteProtocolError(DISCONNECT)

    events = []
    with pytest.raises(httpx.RemoteProtocolError):
        async for event in retry.retry_model_stream(excessive_headers):
            events.append(event)
    assert len(events) == (retry._MAX_PENDING_EVENTS + 1) * 3
    assert calls == [1, 1, 1]
    assert delays.await_count == 2
    delays.reset_mock()

    closed = []

    async def broken():
        try:
            yield _starts()[0]
            raise httpx.RemoteProtocolError(DISCONNECT)
        finally:
            closed.append(True)

    delays.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        [event async for event in retry.retry_model_stream(broken)]
    assert closed == [True]
    delays.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_responses_sdk_and_runner_recover_from_chunked_disconnect(delays):
    requests = []
    closed = []
    response = {
        "id": "resp-final", "created_at": 1, "model": "gpt-5", "object": "response",
        "status": "in_progress", "output": [], "error": None,
    }
    message = {
        "id": "msg-final", "type": "message", "role": "assistant",
        "status": "in_progress", "content": [],
    }

    def sse(event):
        return f"data: {json.dumps(event)}\n\n".encode()

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse({"type": "response.created", "sequence_number": 0, "response": {
                **response, "id": "resp-discarded",
            }})
            yield sse({"type": "response.output_item.added", "sequence_number": 1,
                       "output_index": 0, "item": {**message, "id": "msg-discarded"}})
            yield sse({"type": "response.content_part.added", "sequence_number": 2,
                       "item_id": "msg-discarded", "output_index": 0, "content_index": 0,
                       "part": {"type": "output_text", "text": "", "annotations": []}})
            raise httpx.RemoteProtocolError(DISCONNECT)

        async def aclose(self):
            closed.append(True)

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=BrokenBody())
        assert closed
        events = [
            {"type": "response.created", "response": response},
            {"type": "response.output_item.added", "output_index": 0, "item": message},
            {"type": "response.content_part.added", "item_id": message["id"],
             "output_index": 0, "content_index": 0,
             "part": {"type": "output_text", "text": "", "annotations": []}},
            {"type": "response.output_text.delta", "item_id": message["id"],
             "output_index": 0, "content_index": 0, "delta": "ok"},
            {"type": "response.completed", "response": {
                **response, "status": "completed", "output": [{
                    **message, "status": "completed",
                    "content": [{"type": "output_text", "text": "ok", "annotations": []}],
                }],
            }},
        ]
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=b"".join(sse({**event, "sequence_number": index})
                                               for index, event in enumerate(events)))

    async with AsyncOpenAI(
        api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ) as client:
        async def create_stream(**kwargs):
            return await client.responses.create(**kwargs, stream=True), kwargs

        model = ModelWrapper(ResponsesModel(model="gpt-5", transport=SimpleNamespace(
            convert_model_name=lambda name: name, create_stream=create_stream,
        )))
        result = Runner.run_streamed(
            Agent(name="DisconnectRetryTest", model=model), input="hello",
            run_config=RunConfig(tracing_disabled=True),
        )
        events = [event.data async for event in result.stream_events()
                  if event.type == "raw_response_event"]
        assert result.final_output == "ok"
    assert len(requests) == 2
    assert json.loads(requests[0].content) == json.loads(requests[1].content)
    assert [event.delta for event in events if event.type == "response.output_text.delta"] == ["ok"]
    assert sum(event.type == "response.created" for event in events) == 1
    assert "discarded" not in repr(events)
    # Runner also yields to the event loop with sleep(0).
    assert [call.args[0] for call in delays.await_args_list if call.args[0] > 0] == [1.5]