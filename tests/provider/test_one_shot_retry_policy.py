"""SDK helpers preserve durable learning retry budgets and task isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI, InternalServerError

from siada.provider import one_shot, retry
from siada.provider.default import chat_completions, responses_transport
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.provider_factory import provider_runtime


class FailingModel:
    model = "gpt-4o"

    def __init__(self):
        self.attempts = {}

    async def get_response(self, **kwargs):
        label = kwargs["input"]
        self.attempts[label] = self.attempts.get(label, 0) + 1
        assert "num_retries" not in (kwargs["model_settings"].extra_args or {})
        await asyncio.sleep(0)
        raise TimeoutError("synthetic attempt failed")

    async def stream_response(self, **kwargs):
        await self.get_response(**kwargs)
        yield  # pragma: no cover


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("limit", "attempts"), [(None, 3), (0, 1), (1, 2)])
async def test_helper_retry_budget_is_consumed_before_sdk_settings(monkeypatch, stream, limit, attempts):
    model = FailingModel()
    monkeypatch.setattr(one_shot, "get_provider", lambda _: SimpleNamespace(get_model=lambda _: model))
    monkeypatch.setattr(retry, "_backoff", AsyncMock())
    with pytest.raises(TimeoutError):
        await one_shot.one_shot_completion("request", model=model.model, stream=stream, num_retries=limit)
    assert model.attempts == {"request": attempts}
    assert retry._retry_limit() == 2


@pytest.mark.asyncio
async def test_concurrent_helper_retry_scopes_do_not_change_sibling_budget(monkeypatch):
    model = FailingModel()
    monkeypatch.setattr(one_shot, "get_provider", lambda _: SimpleNamespace(get_model=lambda _: model))
    monkeypatch.setattr(retry, "_backoff", AsyncMock())
    results = await asyncio.gather(
        one_shot.one_shot_completion("learning", model=model.model, num_retries=0),
        one_shot.one_shot_completion("normal", model=model.model),
        return_exceptions=True,
    )
    assert all(isinstance(result, TimeoutError) for result in results)
    assert model.attempts == {"learning": 1, "normal": 3}
    assert retry._retry_limit() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-4o", "gpt-5.4"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("limit", "attempts"), [(0, 1), (None, 3)])
async def test_native_http_clients_have_no_nested_retries(monkeypatch, model_name, stream, limit, attempts):
    requests = []
    clients = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "synthetic failure", "type": "server_error"}})

    def create_client(**kwargs):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
        clients.append(client)
        return AsyncOpenAI(**kwargs, http_client=client)

    monkeypatch.setenv("BASE_URL", "https://retry.example/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.setattr(chat_completions, "AsyncOpenAI", create_client)
    monkeypatch.setattr(responses_transport, "AsyncOpenAI", create_client)
    monkeypatch.setattr(retry, "_backoff", AsyncMock())
    async with provider_runtime():
        with pytest.raises(InternalServerError):
            await one_shot.one_shot_completion(
                "request", model=model_name, provider="default", stream=stream, num_retries=limit,
            )
    assert len(requests) == attempts
    assert all(client.is_closed for client in clients)


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["claude-sonnet-4", "gemini-2.5-pro"])
@pytest.mark.parametrize("stream", [False, True])
async def test_retained_vendor_adapters_disable_nested_learning_retries(monkeypatch, model_name, stream):
    import litellm

    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        assert kwargs["num_retries"] == 0
        raise TimeoutError("synthetic vendor failure")

    provider = DefaultProvider()
    monkeypatch.setenv("BASE_URL", "https://vendor.example/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.setattr(one_shot, "get_provider", lambda _: provider)
    monkeypatch.setattr(litellm, "acompletion", completion)
    try:
        with pytest.raises(TimeoutError):
            await one_shot.one_shot_completion(
                "request", model=model_name, provider="default", stream=stream, num_retries=0,
            )
    finally:
        await provider.aclose()
    assert len(requests) == 1
    assert retry._retry_limit() == 2