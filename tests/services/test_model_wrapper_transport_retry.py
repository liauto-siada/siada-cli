"""Offline regression coverage for transport failures across model adapters."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from agents import Agent, ModelSettings, RunConfig, Runner
from agents.models.interface import ModelTracing
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI
from litellm.exceptions import MidStreamFallbackError, Timeout

from siada.provider import retry
from siada.provider.default.chat_completions import DefaultOpenAIChatCompletionsModel
from siada.services.model_wrapper import ModelWrapper
from siada.provider.responses.responses_model import ResponsesModel


_GATEWAY_AUTH_MESSAGE = (
    "Gateway cannot authenticate upstream services. Please contact Microsoft for help."
)


def _args():
    return dict(
        system_instructions=None, input=[{"role": "user", "content": "hello"}],
        model_settings=ModelSettings(), tools=[], output_schema=None, handoffs=[],
        tracing=ModelTracing.DISABLED, previous_response_id=None,
        conversation_id=None, prompt=None,
    )


def _errors():
    request = httpx.Request("POST", "https://model.test/v1")
    return [
        TimeoutError("timeout"),
        APITimeoutError(request=request),
        APIConnectionError(request=request),
        httpx.ReadTimeout("read timeout"),
        httpx.RemoteProtocolError("incomplete body"),
        Timeout(message="timeout", model="test", llm_provider="openai"),
        MidStreamFallbackError(message="broken stream", model="test", llm_provider="openai"),
        APIError("Unknown stream error", request=request, body={"message": "Unknown stream error"}),
        APIError("busy", request=request, body={"code": "server_is_overloaded"}),
        APIError(
            _GATEWAY_AUTH_MESSAGE, request=request,
            body={"message": _GATEWAY_AUTH_MESSAGE, "code": "authentication_error"},
        ),
    ]


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    monkeypatch.setattr(retry.random, "uniform", lambda *_: 0)
    return sleep


@pytest.mark.asyncio
@pytest.mark.parametrize("error", _errors())
@pytest.mark.parametrize("phase", ["create", "first_read", "lifecycle"])
async def test_stream_retry_catches_creation_and_iteration(error, phase, no_delay):
    calls = []
    closed = []
    admission = AsyncMock()
    processor = Mock(side_effect=lambda items: items)
    final = SimpleNamespace(type="response.completed")

    def create(**kwargs):
        attempt = len(calls)
        calls.append(kwargs)
        if attempt == 0 and phase == "create":
            raise error

        async def stream():
            try:
                if phase == "lifecycle":
                    yield SimpleNamespace(type="response.created", attempt=attempt)
                if attempt == 0:
                    raise error
                yield final
            finally:
                closed.append(attempt)
        return stream()

    wrapper = ModelWrapper(
        SimpleNamespace(stream_response=create), processor, before_request=admission,
    )
    events = [event async for event in wrapper.stream_response(**_args())]
    assert events[-1] is final
    assert all(getattr(event, "attempt", 1) == 1 for event in events)
    assert len(calls) == 2
    assert calls[0]["input"] is calls[1]["input"]
    assert closed == ([1] if phase == "create" else [0, 1])
    admission.assert_awaited_once()
    processor.assert_called_once()
    no_delay.assert_awaited_once_with(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", [
    "response.output_text.delta",
    "response.function_call_arguments.delta", "response.output_item.added",
    "response.completed",
])
@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("interrupted"),
    APIError("Unknown stream error", request=httpx.Request("POST", "https://model.test"), body=None),
    APIError(
        _GATEWAY_AUTH_MESSAGE, request=httpx.Request("POST", "https://model.test"),
        body={"message": _GATEWAY_AUTH_MESSAGE, "code": "authentication_error"},
    ),
])
async def test_does_not_replay_exposed_output_or_tools(event_type, error, no_delay):
    calls = Mock()

    async def stream():
        calls()
        yield SimpleNamespace(type=event_type)
        raise error

    events = []
    with pytest.raises(type(error)):
        async for event in retry.retry_model_stream(stream):
            events.append(event)
    assert [event.type for event in events] == [event_type]
    calls.assert_called_once()
    no_delay.assert_not_awaited()


@pytest.mark.parametrize("event,expected", [
    # Lifecycle and empty scaffolding placeholders stay replay-safe.
    ({"type": "response.created"}, True),
    ({"type": "response.in_progress"}, True),
    ({"type": "response.output_item.added", "item": {
        "type": "message", "role": "assistant", "status": "in_progress", "content": [],
    }}, True),
    ({"type": "response.output_item.added", "item": {
        "type": "reasoning", "summary": [],
    }}, True),
    ({"type": "response.content_part.added", "part": {
        "type": "output_text", "text": "", "annotations": [],
    }}, True),
    ({"type": "response.reasoning_summary_part.added", "part": {
        "type": "summary_text", "text": "",
    }}, True),
    # Reasoning keeps streaming in real time and never commits the attempt.
    ({"type": "response.reasoning_summary_text.delta", "delta": "thinking"}, True),
    ({"type": "response.reasoning_summary_text.done", "text": "thinking"}, True),
    ({"type": "response.reasoning_summary_part.added", "part": {
        "type": "summary_text", "text": "inline summary",
    }}, True),
    ({"type": "response.reasoning_summary_part.done", "part": {
        "type": "summary_text", "text": "inline summary",
    }}, True),
    ({"type": "response.reasoning_text.delta", "delta": "raw thought"}, True),
    ({"type": "response.reasoning_text.done", "text": "raw thought"}, True),
    ({"type": "response.output_item.added", "item": {
        "type": "reasoning", "summary": [], "encrypted_content": "opaque-state",
    }}, True),
    ({"type": "response.output_item.done", "item": {
        "type": "reasoning", "summary": [{"type": "summary_text", "text": "done thinking"}],
    }}, True),
    ({"type": "response.content_part.added", "part": {
        "type": "reasoning_text", "text": "",
    }}, True),
    ({"type": "response.content_part.done", "part": {
        "type": "reasoning_text", "text": "raw thought",
    }}, True),
    (SimpleNamespace(type="response.reasoning_summary_text.delta", delta="thinking"), True),
    # Answer text, tool output, unknown payloads, and terminal events commit.
    ({"type": "response.output_text.delta", "delta": "answer"}, False),
    ({"type": "response.output_item.added", "item": {
        "type": "function_call", "call_id": "call-test", "name": "synthetic_tool",
        "arguments": "", "status": "in_progress",
    }}, False),
    ({"type": "response.function_call_arguments.delta", "delta": "{}"}, False),
    ({"type": "response.output_item.added", "item": {
        "type": "message", "role": "assistant", "status": "in_progress",
        "content": [{"type": "output_text", "text": "already present"}],
    }}, False),
    ({"type": "response.output_item.done", "item": {
        "type": "message", "role": "assistant", "status": "completed", "content": [],
    }}, False),
    ({"type": "response.content_part.added", "part": {
        "type": "output_text", "text": "answer", "annotations": [],
    }}, False),
    ({"type": "response.content_part.done", "part": {
        "type": "output_text", "text": "answer", "annotations": [],
    }}, False),
    ({"type": "response.output_item.added"}, False),
    ({"type": "response.custom_event"}, False),
    ({"type": "response.completed"}, False),
    ({"type": "response.incomplete"}, False),
    ({"type": "response.failed"}, False),
])
def test_replay_safe_stream_event_whitelist(event, expected):
    assert retry.is_replay_safe_stream_event(event) is expected


def _thinking(item_id="rs-test", summary="Let me think"):
    """A realistic Responses API reasoning lifecycle with live thinking deltas."""
    return [
        {"type": "response.created"},
        {"type": "response.in_progress"},
        {"type": "response.output_item.added", "output_index": 0,
         "item": {"id": item_id, "type": "reasoning", "summary": []}},
        {"type": "response.reasoning_summary_part.added", "item_id": item_id,
         "output_index": 0, "summary_index": 0,
         "part": {"type": "summary_text", "text": ""}},
        {"type": "response.reasoning_summary_text.delta", "item_id": item_id,
         "output_index": 0, "summary_index": 0, "delta": summary},
        {"type": "response.reasoning_summary_text.done", "item_id": item_id,
         "output_index": 0, "summary_index": 0, "text": summary},
        {"type": "response.reasoning_summary_part.done", "item_id": item_id,
         "output_index": 0, "summary_index": 0,
         "part": {"type": "summary_text", "text": summary}},
        {"type": "response.content_part.added", "item_id": item_id,
         "output_index": 0, "content_index": 0,
         "part": {"type": "reasoning_text", "text": ""}},
        {"type": "response.reasoning_text.delta", "item_id": item_id,
         "output_index": 0, "content_index": 0, "delta": summary},
        {"type": "response.reasoning_text.done", "item_id": item_id,
         "output_index": 0, "content_index": 0, "text": summary},
        {"type": "response.content_part.done", "item_id": item_id,
         "output_index": 0, "content_index": 0,
         "part": {"type": "reasoning_text", "text": summary}},
        {"type": "response.output_item.done", "output_index": 0,
         "item": {"id": item_id, "type": "reasoning",
                  "summary": [{"type": "summary_text", "text": summary}]}},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    MidStreamFallbackError(message="broken stream", model="test", llm_provider="openai"),
    httpx.RemoteProtocolError("incomplete SSE body"),
    TimeoutError("read timed out"),
])
async def test_transport_failure_after_thinking_lifecycle_is_retried(error, no_delay):
    calls = []

    def attempt_events(attempt):
        thinking = _thinking(item_id=f"rs-{attempt}")
        if attempt:
            return thinking + [
                {"type": "response.output_item.added", "output_index": 1,
                 "item": {"id": "msg-test", "type": "message", "role": "assistant",
                          "status": "in_progress", "content": []}},
                {"type": "response.output_text.delta", "item_id": "msg-test",
                 "output_index": 1, "content_index": 0, "delta": "recovered"},
                {"type": "response.completed"},
            ]
        return thinking

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        for event in attempt_events(attempt):
            yield event
        if not attempt:
            raise error

    events = [event async for event in retry.retry_model_stream(stream)]
    assert len(calls) == 2
    no_delay.assert_awaited_once_with(1)
    # The failed attempt's thinking stays in the raw stream and the retry
    # streams its own fresh lifecycle; only the final attempt answers.
    assert [event["delta"] for event in events
            if event["type"] == "response.reasoning_summary_text.delta"] == ["Let me think"] * 2
    assert [event["delta"] for event in events
            if event["type"] == "response.reasoning_text.delta"] == ["Let me think"] * 2
    assert [event["delta"] for event in events
            if event["type"] == "response.output_text.delta"] == ["recovered"]
    assert [event["item"]["id"] for event in events
            if event["type"] == "response.output_item.added"] == ["rs-0", "rs-1", "msg-test"]
    assert sum(event["type"] == "response.created" for event in events) == 2
    assert events[-1]["type"] == "response.completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["deltas", "placeholders"])
async def test_more_than_pending_limit_thinking_events_still_retry(shape, no_delay):
    count = retry._MAX_PENDING_EVENTS + 36
    calls = []

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        yield {"type": "response.created"}
        for index in range(count):
            if shape == "deltas":
                yield {"type": "response.reasoning_summary_text.delta",
                       "item_id": f"rs-{attempt}", "delta": f"thought {index}"}
            else:
                yield {"type": "response.reasoning_summary_part.added",
                       "item_id": f"rs-{attempt}",
                       "part": {"type": "summary_text", "text": ""}}
        if not attempt:
            raise MidStreamFallbackError(message="broken stream", model="test", llm_provider="openai")
        yield {"type": "response.completed"}

    events = [event async for event in retry.retry_model_stream(stream)]
    thinking_type = ("response.reasoning_summary_text.delta" if shape == "deltas"
                     else "response.reasoning_summary_part.added")
    assert len(calls) == 2
    no_delay.assert_awaited_once_with(1)
    # The pending buffer only bounds empty scaffolding; long thinking never
    # commits the attempt, so every thinking event of both attempts is kept.
    assert sum(event["type"] == thinking_type for event in events) == 2 * count
    assert sum(event["type"] == "response.created" for event in events) == 2
    assert events[-1]["type"] == "response.completed"


@pytest.mark.asyncio
async def test_stream_eof_after_thinking_only_is_retryable(no_delay):
    calls = []

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        for event in _thinking(item_id=f"rs-{attempt}"):
            yield event
        if attempt:
            yield {"type": "response.output_text.delta", "delta": "recovered"}
            yield {"type": "response.completed"}
        # The first attempt ends without a terminal response event.

    events = [event async for event in retry.retry_model_stream(stream, model_name="test")]
    assert len(calls) == 2
    no_delay.assert_awaited_once_with(1)
    assert [event["delta"] for event in events
            if event["type"] == "response.reasoning_summary_text.delta"] == ["Let me think"] * 2
    assert [event["delta"] for event in events
            if event["type"] == "response.output_text.delta"] == ["recovered"]
    assert events[-1]["type"] == "response.completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["transport", "eof"])
async def test_thinking_retry_exhaustion_raises_last_error(failure, no_delay):
    calls = []

    async def stream():
        attempt = len(calls)
        calls.append(attempt)
        yield {"type": "response.created"}
        yield {"type": "response.reasoning_summary_text.delta", "delta": f"thought {attempt}"}
        if failure == "transport":
            raise MidStreamFallbackError(message="broken stream", model="test", llm_provider="openai")
        # eof: end the stream without a terminal response event.

    events = []
    with pytest.raises(
        MidStreamFallbackError if failure == "transport" else retry.MissingFinalResponseError
    ) as caught:
        async for event in retry.retry_model_stream(stream):
            events.append(event)
    if failure == "eof":
        assert caught.value.output_exposed is False
        assert caught.value.last_event == "response.reasoning_summary_text.delta"
    assert len(calls) == 3
    # Thinking of every failed attempt was already exposed in real time.
    assert [event["delta"] for event in events
            if event["type"] == "response.reasoning_summary_text.delta"] == [
                "thought 0", "thought 1", "thought 2",
            ]
    assert [call.args[0] for call in no_delay.await_args_list] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("bad JSON"), asyncio.CancelledError()])
async def test_parser_bugs_and_cancellation_mid_thinking_are_not_retried(error, no_delay):
    calls = Mock()

    async def stream():
        calls()
        yield {"type": "response.created"}
        yield {"type": "response.reasoning_summary_text.delta", "delta": "partial thought"}
        raise error

    events = []
    with pytest.raises(type(error)):
        async for event in retry.retry_model_stream(stream):
            events.append(event)
    assert [event["type"] for event in events] == [
        "response.created", "response.reasoning_summary_text.delta",
    ]
    calls.assert_called_once()
    no_delay.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("committing", [
    {"type": "response.output_text.delta", "item_id": "msg-test",
     "output_index": 1, "content_index": 0, "delta": "answer"},
    {"type": "response.output_item.added", "output_index": 1, "item": {
        "id": "fc-test", "type": "function_call", "call_id": "call-test",
        "name": "synthetic_tool", "arguments": "", "status": "in_progress",
    }},
    {"type": "response.function_call_arguments.delta", "item_id": "fc-test",
     "output_index": 1, "delta": "{}"},
    {"type": "response.content_part.added", "item_id": "msg-test",
     "output_index": 1, "content_index": 0,
     "part": {"type": "output_text", "text": "answer", "annotations": []}},
])
async def test_body_or_tool_after_thinking_commits_the_attempt(committing, no_delay):
    calls = Mock()

    async def stream():
        calls()
        for event in _thinking():
            yield event
        yield committing
        raise MidStreamFallbackError(message="broken stream", model="test", llm_provider="openai")

    events = []
    with pytest.raises(MidStreamFallbackError):
        async for event in retry.retry_model_stream(stream):
            events.append(event)
    assert events[: len(_thinking())] == _thinking()
    assert events[-1] == committing
    assert len(events) == len(_thinking()) + 1
    calls.assert_called_once()
    no_delay.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_exhaustion_preserves_last_error_and_closes_before_backoff(streaming, no_delay):
    errors = [TimeoutError(str(index)) for index in range(3)]
    closed = []
    calls = 0

    async def call(**kwargs):
        nonlocal calls
        error = errors[calls]
        calls += 1
        raise error

    async def stream():
        nonlocal calls
        attempt = calls
        calls += 1
        try:
            raise errors[attempt]
            yield
        finally:
            closed.append(attempt)

    async def sleep(delay):
        if streaming:
            assert closed == list(range(calls))
    no_delay.side_effect = sleep
    with pytest.raises(TimeoutError) as caught:
        if streaming:
            [event async for event in retry.retry_model_stream(stream)]
        else:
            await retry.retry_model_call(call)
    assert caught.value is errors[-1]
    assert calls == 3
    assert [args.args[0] for args in no_delay.await_args_list] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("bad JSON"), asyncio.CancelledError()])
async def test_parser_bugs_and_cancellation_are_not_retried(error, no_delay):
    closed = Mock()

    async def stream():
        try:
            raise error
            yield
        finally:
            closed()
    with pytest.raises(type(error)):
        [event async for event in retry.retry_model_stream(stream)]
    closed.assert_called_once()
    no_delay.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_admission_timeout_aborts_without_model_calls(streaming, no_delay):
    call = Mock()
    admission = AsyncMock(side_effect=TimeoutError("storage unavailable"))
    wrapper = ModelWrapper(
        SimpleNamespace(get_response=call, stream_response=call),
        before_request=admission,
    )
    with pytest.raises(TimeoutError):
        if streaming:
            [event async for event in wrapper.stream_response(**_args())]
        else:
            await wrapper.get_response(**_args())
    call.assert_not_called()
    admission.assert_awaited_once()
    no_delay.assert_not_awaited()


@pytest.mark.asyncio
async def test_nonstream_retry_does_not_repeat_admission(no_delay):
    call = AsyncMock(side_effect=[APITimeoutError(request=httpx.Request("POST", "https://model.test")), "ok"])
    admission = AsyncMock()
    wrapper = ModelWrapper(SimpleNamespace(get_response=call), before_request=admission)
    assert await wrapper.get_response(**_args()) == "ok"
    assert call.await_count == 2
    admission.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_nested_admission_wrappers_share_one_retry_budget(streaming, no_delay):
    calls = Mock()
    admissions = [AsyncMock(), AsyncMock()]
    processors = [Mock(side_effect=lambda items: items), Mock(side_effect=lambda items: items)]

    async def call(**kwargs):
        calls()
        raise TimeoutError("persistent failure")

    async def stream(**kwargs):
        calls()
        raise TimeoutError("persistent failure")
        yield

    wrapper = ModelWrapper(
        ModelWrapper(
            SimpleNamespace(get_response=call, stream_response=stream),
            processors[0], before_request=admissions[0],
        ),
        processors[1], before_request=admissions[1],
    )
    with pytest.raises(TimeoutError):
        if streaming:
            [event async for event in wrapper.stream_response(**_args())]
        else:
            await wrapper.get_response(**_args())
    assert calls.call_count == 3
    assert no_delay.await_count == 2
    for admission in admissions:
        admission.assert_awaited_once()
    for processor in processors:
        processor.assert_called_once()


@pytest.mark.asyncio
async def test_responses_transport_iteration_failure_recreates_model_stream(no_delay):
    closed = []
    calls = 0

    async def stream(attempt):
        try:
            yield SimpleNamespace(type="response.created")
            if attempt == 0:
                raise httpx.RemoteProtocolError("incomplete SSE body")
            yield SimpleNamespace(type="response.completed", response=None)
        finally:
            closed.append(attempt)

    async def create_stream(**kwargs):
        nonlocal calls
        attempt = calls
        calls += 1
        return stream(attempt), kwargs

    transport = SimpleNamespace(
        convert_model_name=lambda model: model, create_stream=create_stream,
    )
    model = ResponsesModel(model="gpt-5", transport=transport)
    events = [event async for event in ModelWrapper(model).stream_response(**_args())]
    assert [event.type for event in events] == ["response.created", "response.completed"]
    assert calls == 2
    assert closed == [0, 1]


@pytest.mark.asyncio
async def test_caller_closing_stream_closes_active_attempt(no_delay):
    closed = Mock()
    calls = Mock()

    async def stream():
        calls()
        try:
            yield SimpleNamespace(type="response.output_text.delta")
            yield SimpleNamespace(type="response.completed")
        finally:
            closed()

    model = ModelWrapper(SimpleNamespace(stream_response=lambda **kwargs: stream()))
    result = model.stream_response(**_args())
    await anext(result)
    await result.aclose()
    closed.assert_called_once()
    calls.assert_called_once()
    no_delay.assert_not_awaited()


class _BrokenBody(httpx.AsyncByteStream):
    def __init__(self, prefix=b""):
        self.closed = False
        self.prefix = prefix

    async def __aiter__(self):
        if self.prefix:
            yield self.prefix
            # Let the Runner deliver queued text before a subsequent socket
            # read times out, matching a real midstream read boundary.
            ready = asyncio.get_running_loop().create_future()
            timer = asyncio.get_running_loop().call_later(0.01, ready.set_result, None)
            try:
                await ready
            finally:
                timer.cancel()
        raise httpx.ReadTimeout("SSE read timeout")
        yield b""

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_real_chat_sdk_body_timeout_after_response_created(no_delay):
    bodies = []
    requests = []
    chunk = {
        "id": "chatcmpl-test", "object": "chat.completion.chunk",
        "created": 1, "model": "test",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    }

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            body = _BrokenBody()
            bodies.append(body)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode(),
        )

    async with AsyncOpenAI(
        api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ) as client:
        factory = SimpleNamespace(get_client=lambda: client)
        model = DefaultOpenAIChatCompletionsModel(
            "test", factory, should_replay_reasoning_content=lambda *_: False,
        )
        events = [event async for event in ModelWrapper(model).stream_response(**_args())]
    assert len(requests) == 2
    assert bodies[0].closed
    assert sum(event.type == "response.created" for event in events) == 1
    assert [event.delta for event in events if event.type == "response.output_text.delta"] == ["ok"]
    assert events[-1].type == "response.completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["recover", "exhaust", "after_text"])
async def test_real_runner_handles_sdk_read_timeout_without_replaying_output(
    scenario, no_delay,
):
    bodies = []
    requests = []
    chunk = {
        "id": "chatcmpl-runner", "object": "chat.completion.chunk",
        "created": 1, "model": "test",
        "choices": [{
            "index": 0, "delta": {"role": "assistant", "content": "ok"},
            "finish_reason": None,
        }],
    }
    text_sse = f"data: {json.dumps(chunk)}\n\n".encode()
    complete_sse = text_sse + b"data: [DONE]\n\n"

    def handler(request):
        requests.append(request)
        if scenario == "recover" and len(requests) > 1:
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                content=complete_sse,
            )
        body = _BrokenBody(text_sse if scenario == "after_text" else b"")
        bodies.append(body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=body,
        )

    events = []
    async with AsyncOpenAI(
        api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ) as client:
        model = DefaultOpenAIChatCompletionsModel(
            "test", SimpleNamespace(get_client=lambda: client),
            should_replay_reasoning_content=lambda *_: False,
        )
        result = Runner.run_streamed(
            Agent(name="RetryTest", model=ModelWrapper(model)),
            input="hello", run_config=RunConfig(tracing_disabled=True),
        )

        async def consume():
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    events.append(event.data)

        if scenario == "recover":
            await consume()
            assert result.final_output == "ok"
        else:
            with pytest.raises(httpx.ReadTimeout):
                await consume()

    assert len(requests) == {"recover": 2, "exhaust": 3, "after_text": 1}[scenario]
    assert all(body.closed for body in bodies)
    deltas = [event.delta for event in events if event.type == "response.output_text.delta"]
    assert deltas == ([] if scenario == "exhaust" else ["ok"])
    assert sum(event.type == "response.created" for event in events) == (
        0 if scenario == "exhaust" else 1
    )


@pytest.mark.parametrize("body,expected", [
    ({"message": "Unknown stream error"}, True),
    ({"type": "server_error"}, True),
    ({"error": {"code": "rate_limit_exceeded"}}, True),
    ({"code": "insufficient_quota", "type": "server_error"}, False),
    ({"code": "invalid_request_error", "message": "Unknown stream error"}, False),
    ({"type": "invalid_request_error", "message": "Unknown stream error"}, False),
    ({"message": "invalid input"}, False),
])
def test_api_error_classification(body, expected):
    error = APIError(
        body.get("message", "failure"),
        request=httpx.Request("POST", "https://model.test"), body=body,
    )
    assert retry.is_retryable_model_error(error) is expected


@pytest.mark.parametrize("status,expected", [
    (400, False), (401, False), (403, True), (404, False),
    (408, True), (409, True), (429, True), (500, True), (503, True),
])
def test_api_status_error_classification(status, expected):
    error = APIStatusError(
        "failure",
        response=httpx.Response(status, request=httpx.Request("POST", "https://model.test")),
        body=None,
    )
    assert retry.is_retryable_model_error(error) is expected


@pytest.mark.parametrize("body", [
    None,
    _GATEWAY_AUTH_MESSAGE,
    {"message": _GATEWAY_AUTH_MESSAGE, "code": "authentication_error"},
    {"error": {"message": _GATEWAY_AUTH_MESSAGE, "type": "authentication_error"}},
    {"message": f"  {_GATEWAY_AUTH_MESSAGE.upper()}  ", "code": "Unauthorized"},
])
@pytest.mark.parametrize("status", [None, 400, 401])
def test_gateway_upstream_auth_error_is_retryable(body, status):
    request = httpx.Request("POST", "https://model.test")
    if status is None:
        error = APIError(_GATEWAY_AUTH_MESSAGE, request=request, body=body)
    else:
        error = APIStatusError(
            _GATEWAY_AUTH_MESSAGE,
            response=httpx.Response(status, request=request), body=body,
        )
    assert retry.is_retryable_model_error(error)


@pytest.mark.parametrize("message", [
    "Invalid API key.",
    "Gateway cannot authenticate client credentials.",
    "Request rejected: Gateway cannot authenticate upstream services.",
])
def test_other_authentication_errors_are_not_retryable(message):
    error = APIError(
        message, request=httpx.Request("POST", "https://model.test"),
        body={"message": message, "code": "authentication_error"},
    )
    assert not retry.is_retryable_model_error(error)
    assert not retry.is_retryable_model_error(ValueError(_GATEWAY_AUTH_MESSAGE))


@pytest.mark.asyncio
@pytest.mark.parametrize("recover", [True, False])
async def test_nonstream_gateway_auth_retry_budget(recover, no_delay):
    error = APIError(
        _GATEWAY_AUTH_MESSAGE, request=httpx.Request("POST", "https://model.test"),
        body={"message": _GATEWAY_AUTH_MESSAGE, "code": "authentication_error"},
    )
    call = AsyncMock(side_effect=[error, "ok"] if recover else error)
    admission = AsyncMock()
    wrapper = ModelWrapper(SimpleNamespace(get_response=call), before_request=admission)
    if recover:
        assert await wrapper.get_response(**_args()) == "ok"
    else:
        with pytest.raises(APIError) as caught:
            await wrapper.get_response(**_args())
        assert caught.value is error
    assert call.await_count == (2 if recover else 3)
    assert no_delay.await_count == (1 if recover else 2)
    admission.assert_awaited_once()


def test_diagnostics_do_not_dump_unstructured_body_or_authentication():
    request = httpx.Request(
        "POST", "https://model.test",
        headers={"authorization": "Bearer synthetic-secret", "siada-trace-id": "trace-test"},
    )
    error = APIError(
        "error body contains synthetic-secret", request=request,
        body={"debug": {"api_key": "synthetic-secret"}, "code": "server_error"},
    )
    details = retry.api_error_details(error)
    assert details["trace_id"] == "trace-test"
    assert details["code"] == "server_error"
    assert "synthetic-secret" not in repr(details)
    assert retry.api_error_details(APIError(
        "failure", request=request, body={"message": "x" * 1000},
    ))["message"] == "x" * 512


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected_calls", [
    ("server_error", 2), ("invalid_request_error", 1),
])
async def test_nonstream_api_retry_preserves_admission(code, expected_calls, no_delay):
    error = APIError(
        "failure", request=httpx.Request("POST", "https://model.test"),
        body={"code": code},
    )
    call = AsyncMock(side_effect=[error, "ok"])
    admission = AsyncMock()
    wrapper = ModelWrapper(SimpleNamespace(get_response=call), before_request=admission)
    if expected_calls == 2:
        assert await wrapper.get_response(**_args()) == "ok"
    else:
        with pytest.raises(APIError) as caught:
            await wrapper.get_response(**_args())
        assert caught.value is error
    assert call.await_count == expected_calls
    assert no_delay.await_count == expected_calls - 1
    admission.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", [
    "recover", "exhaust", "after_text", "invalid", "failed_event", "error_event",
    "eof_recover", "eof_exhaust", "eof_after_text", "eof_after_tool", "empty_eof",
])
@pytest.mark.parametrize("gateway_auth", [False, True])
async def test_real_responses_sdk_stream_errors(
    scenario, gateway_auth, no_delay, caplog, monkeypatch,
):
    requests = []
    bodies = []
    app_logger = logging.getLogger("siada.app")
    monkeypatch.setattr(app_logger, "handlers", [*app_logger.handlers, caplog.handler])

    class Body(httpx.AsyncByteStream):
        closed = False

        def __init__(self, prefix, suffix):
            self.prefix, self.suffix = prefix, suffix

        async def __aiter__(self):
            yield self.prefix
            # Model a later socket read so queued output reaches the consumer.
            ready = asyncio.get_running_loop().create_future()
            timer = asyncio.get_running_loop().call_later(0.01, ready.set_result, None)
            try:
                await ready
            finally:
                timer.cancel()
            yield self.suffix

        async def aclose(self):
            self.closed = True
    response = {
        "id": "resp-test", "created_at": 1, "model": "gpt-5",
        "object": "response", "status": "completed", "output": [],
        "error": None, "incomplete_details": None, "instructions": None,
        "metadata": {}, "parallel_tool_calls": True, "temperature": 1,
        "tool_choice": "auto", "tools": [], "top_p": 1,
    }

    def sse(data):
        return f"data: {json.dumps(data)}\n\n".encode()

    error_body = {
        "message": "Unknown stream error", "code": "server_error",
        "type": "server_error", "debug": {"api_key": "synthetic-secret"},
    }
    if scenario == "invalid":
        error_body["code"] = "invalid_request_error"
    if gateway_auth and scenario != "invalid":
        error_body.update(
            message=_GATEWAY_AUTH_MESSAGE, code="authentication_error",
            type="authentication_error",
        )
    recovering = scenario in {"recover", "failed_event", "error_event", "eof_recover"}

    def handler(request):
        requests.append(request)
        if bodies:
            assert bodies[-1].closed
        created = sse({
            "type": "response.created", "sequence_number": 0,
            "response": {**response, "status": "in_progress"},
        })
        if recovering and len(requests) > 1:
            content = created + sse({
                "type": "response.completed", "sequence_number": 1, "response": response,
            })
        else:
            content = created
            if scenario in {"after_text", "eof_after_text"}:
                content += sse({
                    "type": "response.output_text.delta", "sequence_number": 1,
                    "item_id": "msg-test", "output_index": 0, "content_index": 0,
                    "delta": "once",
                })
            if scenario == "eof_after_tool":
                content += sse({
                    "type": "response.output_item.added", "sequence_number": 1,
                    "output_index": 0,
                    "item": {
                        "id": "fc-test", "type": "function_call",
                        "call_id": "call-test", "name": "synthetic_tool",
                        "arguments": "", "status": "in_progress",
                    },
                })
            if scenario == "failed_event":
                suffix = sse({
                    "type": "response.failed", "sequence_number": 1,
                    "response": {**response, "status": "failed", "error": error_body},
                })
            elif scenario == "error_event":
                suffix = sse({
                    "type": "error", "sequence_number": 1,
                    "message": error_body["message"], "code": None, "param": None,
                })
            elif scenario.startswith("eof_") or scenario == "empty_eof":
                suffix = b"data: [DONE]\n\n"
                if scenario == "empty_eof":
                    content = b""
            else:
                suffix = sse({"error": error_body})
        if recovering and len(requests) > 1:
            suffix = b""
        body = Body(content, suffix)
        bodies.append(body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream", "x-request-id": "req-test"},
            stream=body,
        )

    events = []
    with caplog.at_level("ERROR", logger="siada.app"):
        async with AsyncOpenAI(
            api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as client:
            async def create_stream(**kwargs):
                stream = await client.responses.create(**kwargs, stream=True)
                return stream, kwargs

            model = ModelWrapper(ResponsesModel(
                model="gpt-5", transport=SimpleNamespace(
                    convert_model_name=lambda name: name, create_stream=create_stream,
                ),
            ))
            result = Runner.run_streamed(
                Agent(name="ResponsesRetryTest", model=model),
                input="hello", run_config=RunConfig(tracing_disabled=True),
            )

            async def consume():
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        events.append(event.data)

            if recovering:
                await consume()
            else:
                expected_error = (
                    retry.MissingFinalResponseError
                    if scenario.startswith("eof_") or scenario == "empty_eof"
                    else APIError
                )
                with pytest.raises(expected_error):
                    await consume()

    assert len(requests) == {
        "recover": 2, "exhaust": 3, "after_text": 1, "invalid": 1,
        "failed_event": 2, "error_event": 2,
        "eof_recover": 2, "eof_exhaust": 3, "eof_after_text": 1,
        "eof_after_tool": 1, "empty_eof": 3,
    }[scenario]
    assert all(body.closed for body in bodies)
    assert [event.delta for event in events if event.type == "response.output_text.delta"] == (
        ["once"] if scenario in {"after_text", "eof_after_text"} else []
    )
    assert sum(event.type == "response.created" for event in events) == (
        0 if scenario in {"exhaust", "invalid", "eof_exhaust", "empty_eof"} else 1
    )
    diagnostic = "\n".join(
        record.getMessage() for record in caplog.records
        if "OpenAI Responses API streaming error:" in record.getMessage()
    )
    assert (
        "without a final response" if scenario.startswith("eof_") or scenario == "empty_eof"
        else error_body["message"]
    ) in diagnostic
    assert "'request_id': 'req-test'" in diagnostic
    assert f"response_id={'None' if scenario == 'empty_eof' else 'resp-test'}" in diagnostic
    assert f"output_exposed={scenario in {'after_text', 'eof_after_text', 'eof_after_tool'}}" in diagnostic
    assert "synthetic-secret" not in diagnostic
    assert "api_key" not in diagnostic


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["server_error", "eof"])
async def test_real_responses_sdk_runner_recovers_after_reasoning_without_mixing_ids(
    failure, no_delay, caplog, monkeypatch,
):
    requests = []
    bodies = []
    app_logger = logging.getLogger("siada.app")
    monkeypatch.setattr(app_logger, "handlers", [*app_logger.handlers, caplog.handler])

    def sse(data):
        return f"data: {json.dumps(data)}\n\n".encode()

    response = {
        "id": "resp-final", "created_at": 1, "model": "gpt-5", "object": "response",
        "status": "in_progress", "output": [], "error": None,
    }
    final_reasoning = {
        "id": "rs-final", "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "second attempt thinking"}],
    }
    final_message = {
        "id": "msg-final", "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": "recovered answer", "annotations": []}],
    }

    def reasoning_start(item_id, response_id, delta):
        return [
            {"type": "response.created", "sequence_number": 0,
             "response": {**response, "id": response_id}},
            {"type": "response.output_item.added", "sequence_number": 1,
             "output_index": 0, "item": {"id": item_id, "type": "reasoning", "summary": []}},
            {"type": "response.reasoning_summary_part.added", "sequence_number": 2,
             "item_id": item_id, "output_index": 0, "summary_index": 0,
             "part": {"type": "summary_text", "text": ""}},
            {"type": "response.reasoning_summary_text.delta", "sequence_number": 3,
             "item_id": item_id, "output_index": 0, "summary_index": 0, "delta": delta},
        ]

    success = reasoning_start("rs-final", "resp-final", "second attempt thinking") + [
        {"type": "response.reasoning_summary_text.done", "sequence_number": 4,
         "item_id": "rs-final", "output_index": 0, "summary_index": 0,
         "text": "second attempt thinking"},
        {"type": "response.reasoning_summary_part.done", "sequence_number": 5,
         "item_id": "rs-final", "output_index": 0, "summary_index": 0,
         "part": {"type": "summary_text", "text": "second attempt thinking"}},
        {"type": "response.output_item.done", "sequence_number": 6, "output_index": 0,
         "item": final_reasoning},
        {"type": "response.output_item.added", "sequence_number": 7, "output_index": 1,
         "item": {"id": "msg-final", "type": "message", "role": "assistant",
                  "status": "in_progress", "content": []}},
        {"type": "response.content_part.added", "sequence_number": 8, "item_id": "msg-final",
         "output_index": 1, "content_index": 0,
         "part": {"type": "output_text", "text": "", "annotations": []}},
        {"type": "response.output_text.delta", "sequence_number": 9, "item_id": "msg-final",
         "output_index": 1, "content_index": 0, "delta": "recovered answer"},
        {"type": "response.output_item.done", "sequence_number": 10, "output_index": 1,
         "item": final_message},
        {"type": "response.completed", "sequence_number": 11, "response": {
            **response, "status": "completed", "output": [final_reasoning, final_message],
        }},
    ]

    class Body(httpx.AsyncByteStream):
        closed = False

        def __init__(self, events, failure):
            self.events, self.failure = events, failure

        async def __aiter__(self):
            for event in self.events:
                yield sse(event)
            if self.failure is None:
                return
            # Model a later socket read so streamed thinking reaches the
            # consumer before the failure, matching a real midstream boundary.
            ready = asyncio.get_running_loop().create_future()
            timer = asyncio.get_running_loop().call_later(0.01, ready.set_result, None)
            try:
                await ready
            finally:
                timer.cancel()
            if self.failure == "eof":
                # End the stream without a terminal response event.
                yield b"data: [DONE]\n\n"
            else:
                yield sse({"error": {
                    "message": "Unknown stream error", "code": "server_error",
                    "type": "server_error", "debug": {"api_key": "synthetic-secret"},
                }})

        async def aclose(self):
            self.closed = True

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            body = Body(
                reasoning_start("rs-failed", "resp-failed", "first attempt thinking"),
                failure,
            )
            request_id = "req-failed"
        else:
            body = Body(success, None)
            request_id = "req-final"
        bodies.append(body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream", "x-request-id": request_id},
            stream=body,
        )

    events = []
    with caplog.at_level("ERROR", logger="siada.app"):
        async with AsyncOpenAI(
            api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as client:
            async def create_stream(**kwargs):
                stream = await client.responses.create(**kwargs, stream=True)
                return stream, kwargs

            model = ModelWrapper(ResponsesModel(
                model="gpt-5", transport=SimpleNamespace(
                    convert_model_name=lambda name: name, create_stream=create_stream,
                ),
            ))
            result = Runner.run_streamed(
                Agent(name="ResponsesThinkingRetryTest", model=model),
                input="hello", run_config=RunConfig(tracing_disabled=True),
            )
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    events.append(event.data)

    assert len(requests) == 2
    assert all(body.closed for body in bodies)
    # Only the final attempt's completed response reaches the runner output;
    # response and item IDs of the failed attempt never mix in.
    assert result.final_output == "recovered answer"
    assert result.raw_responses[-1].response_id == "resp-final"
    new_item_ids = [getattr(item.raw_item, "id", None) for item in result.new_items]
    assert "rs-final" in new_item_ids and "msg-final" in new_item_ids
    assert "rs-failed" not in new_item_ids
    # The failed attempt's thinking stays in the raw events and the retry
    # streams its own thinking; answer text comes from the final attempt only.
    assert [event.delta for event in events
            if event.type == "response.reasoning_summary_text.delta"] == [
        "first attempt thinking", "second attempt thinking",
    ]
    assert [event.delta for event in events
            if event.type == "response.output_text.delta"] == ["recovered answer"]
    assert sorted(
        event.response.id for event in events if event.type == "response.created"
    ) == ["resp-failed", "resp-final"]
    assert [event.response.id for event in events
            if event.type == "response.completed"] == ["resp-final"]
    # The model adapter used the shared helper: reasoning-only output stays
    # unexposed, so both failures stay retryable.
    diagnostic = "\n".join(
        record.getMessage() for record in caplog.records
        if "OpenAI Responses API streaming error:" in record.getMessage()
    )
    assert "response_id=resp-failed" in diagnostic
    assert "output_exposed=False" in diagnostic
    assert "'request_id': 'req-failed'" in diagnostic
    assert "synthetic-secret" not in diagnostic
    assert "api_key" not in diagnostic