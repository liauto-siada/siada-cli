"""Offline EOF validation at the shared model boundary."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from agents import Agent, ModelSettings, RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI

from siada.provider import retry
from siada.provider.responses.responses_model import ResponsesModel
from siada.services.model_wrapper import ModelWrapper


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    backoff = AsyncMock()
    monkeypatch.setattr(retry, "_backoff", backoff)
    return backoff


def _args():
    return dict(
        system_instructions=None, input=[{"role": "user", "content": "hello"}],
        model_settings=ModelSettings(), tools=[], output_schema=None, handoffs=[],
        tracing=ModelTracing.DISABLED, previous_response_id=None,
        conversation_id=None, prompt=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("recover", [True, False])
@pytest.mark.parametrize("empty", [True, False])
async def test_eof_retries_with_one_admission_and_closes_before_backoff(
    recover, empty, no_backoff,
):
    calls = []
    closed = []
    admission = AsyncMock()
    processor = Mock(side_effect=lambda items: items)

    async def stream(**kwargs):
        attempt = len(calls)
        calls.append(kwargs)
        try:
            if not empty:
                yield SimpleNamespace(
                    type="response.created", response=SimpleNamespace(id=f"resp-{attempt}"),
                )
            if recover and attempt == 1:
                yield SimpleNamespace(type="response.completed")
        finally:
            closed.append(attempt)

    async def backoff(*_):
        assert closed == list(range(len(calls)))

    no_backoff.side_effect = backoff
    wrapper = ModelWrapper(
        SimpleNamespace(model="synthetic-model", stream_response=stream),
        processor, before_request=admission,
    )
    # Nested wrappers must retain a single retry budget.
    wrapper = ModelWrapper(wrapper)
    events = []
    if recover:
        events = [event async for event in wrapper.stream_response(**_args())]
        assert events[-1].type == "response.completed"
        if not empty:
            assert events[0].response.id == "resp-1"
    else:
        with pytest.raises(retry.MissingFinalResponseError) as caught:
            async for event in wrapper.stream_response(**_args()):
                events.append(event)
        assert events == []
        assert caught.value.model == "synthetic-model"
        assert caught.value.response_id == (None if empty else "resp-2")
        assert caught.value.last_event == (None if empty else "response.created")
        assert caught.value.output_exposed is False
    assert len(calls) == (2 if recover else 3)
    assert closed == list(range(len(calls)))
    assert all(call["input"] is calls[0]["input"] for call in calls)
    assert no_backoff.await_count == len(calls) - 1
    admission.assert_awaited_once()
    processor.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", [
    "response.output_text.delta",
    "response.output_item.added", "response.function_call_arguments.delta",
    "response.output_item.done",
])
async def test_eof_after_output_preserves_event_without_replaying(event_type, no_backoff):
    calls = Mock()

    async def stream():
        calls()
        yield {"type": "response.created", "response": {"id": "resp-test"}}
        yield {"type": event_type}

    events = []
    with pytest.raises(retry.MissingFinalResponseError) as caught:
        async for event in retry.retry_model_stream(stream, model_name="synthetic"):
            events.append(event)
    assert [event["type"] for event in events] == ["response.created", event_type]
    assert caught.value.response_id == "resp-test"
    assert caught.value.last_event == event_type
    assert caught.value.output_exposed is True
    assert retry.is_retryable_model_error(caught.value) is False
    calls.assert_called_once()
    no_backoff.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [
    "response.completed", "response.incomplete", "response.failed",
])
async def test_explicit_terminal_events_are_preserved(terminal, no_backoff):
    async def stream():
        yield SimpleNamespace(type=terminal)

    assert [event.type async for event in retry.retry_model_stream(stream)] == [terminal]
    no_backoff.assert_not_awaited()


def test_generic_model_behavior_errors_are_not_retried():
    assert not retry.is_retryable_model_error(
        ModelBehaviorError("Model did not produce a final response!"),
    )


@pytest.mark.asyncio
async def test_eof_diagnostic_records_metadata_without_text(monkeypatch):
    log_error = Mock()
    monkeypatch.setattr(retry.logger, "error", log_error)

    async def stream():
        yield SimpleNamespace(
            type="response.created", response=SimpleNamespace(id="resp-test"),
        )
        yield SimpleNamespace(type="response.output_text.delta", delta="synthetic-private-text")

    with pytest.raises(retry.MissingFinalResponseError):
        [event async for event in retry.retry_model_stream(stream, model_name="synthetic")]
    log_error.assert_called_once()
    template, *values = log_error.call_args.args
    message = template % tuple(values)
    assert "model=synthetic" in message
    assert "response_id=resp-test" in message
    assert "last_event=response.output_text.delta" in message
    assert "output_exposed=True" in message
    assert "synthetic-private-text" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["recover", "exhaust", "after_text", "after_tool", "empty"])
async def test_real_responses_runner_handles_eof(scenario, caplog, monkeypatch):
    requests = []
    bodies = []
    app_logger = logging.getLogger("siada.app")
    monkeypatch.setattr(app_logger, "handlers", [*app_logger.handlers, caplog.handler])
    response = {
        "id": "resp-eof", "created_at": 1, "model": "gpt-5", "object": "response",
        "status": "completed", "output": [], "error": None, "incomplete_details": None,
        "instructions": None, "metadata": {}, "parallel_tool_calls": True,
        "temperature": 1, "tool_choice": "auto", "tools": [], "top_p": 1,
    }

    def sse(event):
        return f"data: {json.dumps(event)}\n\n".encode()

    class Body(httpx.AsyncByteStream):
        closed = False

        def __init__(self, prefix):
            self.prefix = prefix

        async def __aiter__(self):
            yield self.prefix
            # Allow the Runner to deliver exposed events before the later EOF.
            await asyncio.sleep(0.01)
            yield b"data: [DONE]\n\n"

        async def aclose(self):
            self.closed = True

    def handler(request):
        requests.append(request)
        if bodies:
            assert bodies[-1].closed
        content = b"" if scenario == "empty" else sse({
            "type": "response.created", "sequence_number": 0,
            "response": {**response, "status": "in_progress"},
        })
        if scenario == "recover" and len(requests) > 1:
            content += sse({
                "type": "response.completed", "sequence_number": 1, "response": response,
            })
        elif scenario == "after_text":
            content += sse({
                "type": "response.output_text.delta", "sequence_number": 1,
                "item_id": "msg-eof", "output_index": 0, "content_index": 0, "delta": "once",
            })
        elif scenario == "after_tool":
            content += sse({
                "type": "response.output_item.added", "sequence_number": 1, "output_index": 0,
                "item": {
                    "id": "fc-eof", "type": "function_call", "call_id": "call-eof",
                    "name": "synthetic_tool", "arguments": "", "status": "in_progress",
                },
            })
        body = Body(content)
        bodies.append(body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=body,
        )

    events = []
    with caplog.at_level("ERROR", logger="siada.app"):
        async with AsyncOpenAI(
            api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as client:
            async def create_stream(**kwargs):
                return await client.responses.create(**kwargs, stream=True), kwargs

            model = ModelWrapper(ResponsesModel(
                model="gpt-5", transport=SimpleNamespace(
                    convert_model_name=lambda name: name, create_stream=create_stream,
                ),
            ))
            result = Runner.run_streamed(
                Agent(name="MissingFinalTest", model=model), input="hello",
                run_config=RunConfig(tracing_disabled=True),
            )

            async def consume():
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        events.append(event.data)

            if scenario == "recover":
                await consume()
            else:
                with pytest.raises(retry.MissingFinalResponseError):
                    await consume()
    assert len(requests) == {"recover": 2, "exhaust": 3, "after_text": 1, "after_tool": 1, "empty": 3}[scenario]
    assert all(body.closed for body in bodies)
    assert [event.delta for event in events if event.type == "response.output_text.delta"] == (
        ["once"] if scenario == "after_text" else []
    )
    assert sum(event.type == "response.created" for event in events) == (
        0 if scenario in {"exhaust", "empty"} else 1
    )
    diagnostic = "\n".join(record.getMessage() for record in caplog.records)
    assert "model=gpt-5" in diagnostic
    assert f"response_id={'None' if scenario == 'empty' else 'resp-eof'}" in diagnostic
    assert f"output_exposed={scenario in {'after_text', 'after_tool'}}" in diagnostic