"""Offline SDK coverage for bounded HTTP 403 retries at the model boundary."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from agents import Agent, RunConfig, Runner
from openai import AsyncOpenAI, PermissionDeniedError

from siada.provider import retry
from siada.provider.responses.responses_model import ResponsesModel
from siada.services.model_wrapper import ModelWrapper


@pytest.fixture
def delays(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(retry, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(retry.random, "uniform", lambda *_: 0)
    return sleep


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("statuses", [
    [403, 200], [503, 403, 200], [403, 403, 403],
], ids=["recover", "503_then_403", "exhaust"])
async def test_real_sdk_and_runner_retry_403_with_shared_budget(streaming, statuses, delays):
    requests = []
    admission = AsyncMock()
    response = {
        "id": "resp-auth-test", "created_at": 1, "model": "gpt-5",
        "object": "response", "status": "completed", "output": [],
        "error": None, "incomplete_details": None, "instructions": None,
        "metadata": {}, "parallel_tool_calls": True, "temperature": 1,
        "tool_choice": "auto", "tools": [], "top_p": 1,
    }

    def handler(request):
        status = statuses[len(requests)]
        requests.append(request)
        if status != 200:
            return httpx.Response(status, json={
                "error": "Authentication failed" if status == 403 else "Unavailable",
                "code": status, "message": "Synthetic model failure",
            })
        if not streaming:
            return httpx.Response(200, json=response)
        events = [
            {"type": "response.created", "sequence_number": 0,
             "response": {**response, "status": "in_progress"}},
            {"type": "response.completed", "sequence_number": 1, "response": response},
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            content="".join(f"data: {json.dumps(event)}\n\n" for event in events).encode(),
        )

    async with AsyncOpenAI(
        api_key="synthetic", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ) as client:
        async def create(**kwargs):
            return await client.responses.create(**kwargs), kwargs

        async def create_stream(**kwargs):
            return await client.responses.create(**kwargs, stream=True), kwargs

        model = ModelWrapper(
            ResponsesModel(model="gpt-5", transport=SimpleNamespace(
                convert_model_name=lambda name: name,
                create=create, create_stream=create_stream,
            )),
            before_request=admission,
        )
        agent = Agent(name="AuthRetryTest", model=model)

        async def run():
            config = RunConfig(tracing_disabled=True)
            if not streaming:
                return await Runner.run(agent, input="hello", run_config=config)
            result = Runner.run_streamed(agent, input="hello", run_config=config)
            async for _ in result.stream_events():
                pass
            return result

        if statuses[-1] == 200:
            result = await run()
            assert result.final_output == ""
        else:
            with pytest.raises(PermissionDeniedError) as caught:
                await run()
            assert caught.value.status_code == 403

    assert len(requests) == len(statuses)
    assert all(request.content == requests[0].content for request in requests)
    assert [call.args[0] for call in delays.await_args_list] == list(range(1, len(statuses)))
    admission.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"type": "response.output_text.delta", "delta": "once"},
    {"type": "response.output_item.added", "item": {
        "type": "function_call", "name": "execute", "call_id": "call-test",
        "arguments": "",
    }},
], ids=["answer", "tool"])
async def test_403_after_answer_or_tool_does_not_replay(event, delays):
    calls = []
    closed = []
    error = PermissionDeniedError(
        "Authentication failed",
        response=httpx.Response(403, request=httpx.Request("POST", "https://model.test")),
        body={"error": "Authentication failed", "code": 403},
    )

    async def stream():
        calls.append(True)
        try:
            yield event
            raise error
        finally:
            closed.append(True)

    events = []
    with pytest.raises(PermissionDeniedError) as caught:
        async for value in retry.retry_model_stream(stream):
            events.append(value)
    assert caught.value is error
    assert events == [event]
    assert calls == closed == [True]
    delays.assert_not_awaited()