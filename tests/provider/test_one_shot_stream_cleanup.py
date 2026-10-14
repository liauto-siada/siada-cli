"""One-shot streaming releases request streams without closing shared providers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents.exceptions import ModelBehaviorError
from openai import APIError
from openai.types.responses import Response

from siada.provider import one_shot
from siada.provider.responses.responses_model import ResponsesModel


class SyntheticResponseStream:
    """Model an OpenAI-style stream exposing close() rather than aclose()."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.started = asyncio.Event()
        self.close = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.started.set()
        if self.outcome == "hang":
            await asyncio.Event().wait()
        if self.outcome == "error":
            raise OSError("synthetic stream disconnect")
        if self.outcome == "empty":
            raise StopAsyncIteration
        response = Response.model_construct(
            id="resp-synthetic", status="completed", output=[], usage=None,
        )
        return SimpleNamespace(type=self.outcome, response=response)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [
    "response.completed", "response.failed", "response.incomplete", "error", "empty", "hang", "cancel",
])
async def test_responses_model_closes_http_stream_on_all_exit_paths(monkeypatch, outcome):
    stream = SyntheticResponseStream("hang" if outcome == "cancel" else outcome)
    transport = SimpleNamespace(create_stream=AsyncMock(return_value=(stream, {})), aclose=AsyncMock())
    model = ResponsesModel(model="gpt-5.4", transport=transport)
    provider = SimpleNamespace(get_model=lambda name: model, aclose=AsyncMock())
    monkeypatch.setattr(one_shot, "get_provider", lambda name: provider)
    monkeypatch.setattr("siada.provider.retry._backoff", AsyncMock())
    task = asyncio.create_task(one_shot.one_shot_completion(
        "synthetic prompt", model="gpt-5.4", timeout=0.01 if outcome == "hang" else None,
    ))
    await stream.started.wait()
    if outcome == "cancel":
        task.cancel()
    if outcome == "response.completed":
        response = await task
        assert response.response_id == "resp-synthetic" and response.output == []
    else:
        expected = {
            "cancel": asyncio.CancelledError, "hang": TimeoutError, "error": OSError,
            "response.failed": APIError,
        }.get(outcome, ModelBehaviorError)
        with pytest.raises(expected):
            await task
    attempts = 3 if outcome == "empty" else 1
    assert stream.close.await_count == attempts
    assert transport.create_stream.await_count == attempts
    transport.aclose.assert_not_awaited()
    provider.aclose.assert_not_awaited()