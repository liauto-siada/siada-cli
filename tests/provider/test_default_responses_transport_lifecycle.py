from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.provider.default import responses_transport as responses_module
from siada.provider.default import chat_completions as chat_module
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.default.responses_transport import DefaultResponsesTransport
from siada.provider.responses.transport import ResponsesTransport
from siada.provider.gemini.transport import GeminiTransport


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.responses.create = AsyncMock(return_value=MagicMock())
    client.close = AsyncMock()
    return client


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.4", "gpt-5.4"),
        ("openai/responses/gpt-5.4", "gpt-5.4"),
        ("responses/gpt-5.4", "gpt-5.4"),
    ],
)
def test_default_responses_transport_converts_only_bridge_prefixes(
    model: str,
    expected: str,
):
    assert DefaultResponsesTransport().convert_model_name(model) == expected


def test_default_responses_transport_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("API_KEY", raising=False)
    transport = DefaultResponsesTransport()

    with pytest.raises(ValueError, match="API_KEY is required"):
        transport._get_client()


@pytest.mark.asyncio
async def test_default_transport_lazily_reuses_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _mock_client()
    created: list[dict[str, Any]] = []

    def create_client(**kwargs: Any) -> MagicMock:
        created.append(kwargs)
        return client

    monkeypatch.setattr(responses_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://responses.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")

    transport = DefaultResponsesTransport()
    assert created == []

    first, _ = await transport.create(model="gpt-5.4", input="first")
    second, _ = await transport.create(model="gpt-5.4", input="second")

    assert first is not None
    assert second is not None
    assert created == [{"api_key": "test-key", "base_url": "https://responses.test/v1"}]
    assert client.responses.create.await_count == 2

    await transport.aclose()
    await transport.aclose()

    client.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="is closed"):
        transport._get_client()


@pytest.mark.asyncio
async def test_default_transport_retires_clients_until_shutdown(
    monkeypatch: pytest.MonkeyPatch,
):
    clients = [_mock_client(), _mock_client(), _mock_client()]
    created: list[dict[str, Any]] = []

    def create_client(**kwargs: Any) -> MagicMock:
        created.append(kwargs)
        return clients[len(created) - 1]

    monkeypatch.setattr(responses_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://one.test/v1")
    monkeypatch.setenv("API_KEY", "key-one")

    transport = DefaultResponsesTransport()
    await transport.create(model="gpt-5.4", input="one")

    monkeypatch.setenv("BASE_URL", "https://two.test/v1")
    monkeypatch.setenv("API_KEY", "key-two")
    await transport.create(model="gpt-5.4", input="two")

    monkeypatch.setenv("BASE_URL", "https://three.test/v1")
    monkeypatch.setenv("API_KEY", "key-three")
    await transport.create(model="gpt-5.4", input="three")

    assert len(created) == 3
    for client in clients:
        client.close.assert_not_awaited()

    await transport.aclose()

    for client in clients:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_transport_closes_remaining_clients_after_close_error(
    monkeypatch: pytest.MonkeyPatch,
):
    first, second = _mock_client(), _mock_client()
    first.close.side_effect = OSError("close failed")
    clients = iter((first, second))
    monkeypatch.setattr(responses_module, "AsyncOpenAI", lambda **_: next(clients))
    monkeypatch.setenv("API_KEY", "key-one")
    monkeypatch.setenv("BASE_URL", "https://one.test/v1")

    transport = DefaultResponsesTransport()
    await transport.create(model="gpt-5.4", input="one")
    monkeypatch.setenv("API_KEY", "key-two")
    await transport.create(model="gpt-5.4", input="two")

    with pytest.raises(OSError, match="close failed"):
        await transport.aclose()

    first.close.assert_awaited_once()
    second.close.assert_awaited_once()


def test_default_provider_reuses_responses_transport_across_model_resolution(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("BASE_URL", "https://responses.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()

    first_model = provider.get_model("gpt-5.4")
    second_model = provider.get_model("gpt-5.4")

    assert first_model is not second_model
    assert first_model._transport is provider._responses_transport
    assert second_model._transport is provider._responses_transport


@pytest.mark.asyncio
async def test_default_provider_closes_both_chat_and_responses_resources():
    provider = DefaultProvider()
    provider._chat_client_factory.aclose = AsyncMock()
    provider._responses_transport.aclose = AsyncMock()

    await provider.aclose()

    provider._chat_client_factory.aclose.assert_awaited_once()
    provider._responses_transport.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_provider_closes_responses_even_if_chat_close_fails():
    provider = DefaultProvider()
    provider._chat_client_factory.aclose = AsyncMock(side_effect=OSError("chat close failed"))
    provider._responses_transport.aclose = AsyncMock()

    with pytest.raises(OSError, match="chat close failed"):
        await provider.aclose()

    provider._chat_client_factory.aclose.assert_awaited_once()
    provider._responses_transport.aclose.assert_awaited_once()


@pytest.mark.parametrize("active_endpoint", ["chat", "responses", "both"])
def test_unused_gemini_does_not_block_owner_loop_shutdown_retry(monkeypatch, active_endpoint):
    clients = []

    def create_client(**kwargs):
        client = _mock_client()
        clients.append(client)
        return client

    monkeypatch.setenv("BASE_URL", "https://synthetic.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setattr(responses_module, "AsyncOpenAI", create_client)
    provider = DefaultProvider()
    provider.get_model("gemini-3.5-flash")
    owner = asyncio.new_event_loop()
    foreign = asyncio.new_event_loop()

    async def acquire():
        if active_endpoint in {"chat", "both"}:
            provider.get_model("gpt-4o")
        if active_endpoint in {"responses", "both"}:
            provider._responses_transport._get_client()

    try:
        owner.run_until_complete(acquire())
        with pytest.raises((RuntimeError, ExceptionGroup)):
            foreign.run_until_complete(provider.aclose())
        for client in clients:
            client.close.assert_not_awaited()
        owner.run_until_complete(provider.aclose())
        owner.run_until_complete(provider.aclose())
        for client in clients:
            client.close.assert_awaited_once()
    finally:
        owner.close()
        foreign.close()


def test_unused_gemini_transport_can_close_without_claiming_a_loop():
    transport = GeminiTransport()
    asyncio.run(transport.aclose())
    asyncio.run(transport.aclose())


@pytest.mark.asyncio
async def test_responses_transport_default_aclose_is_noop():
    class StatelessTransport(ResponsesTransport):
        def convert_model_name(self, model: str) -> str:
            return model

        async def create(self, **params):
            raise NotImplementedError

        async def create_stream(self, **params):
            raise NotImplementedError

    await StatelessTransport().aclose()


@pytest.mark.asyncio
async def test_provider_factory_closes_remaining_providers_after_close_error(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider import provider_factory

    failing_provider = MagicMock()
    failing_provider.aclose = AsyncMock(side_effect=OSError("provider close failed"))
    next_provider = MagicMock()
    next_provider.aclose = AsyncMock()
    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    monkeypatch.setattr(
        provider_factory,
        "provider_map",
        {"first": failing_provider, "second": next_provider},
    )

    with pytest.raises(OSError, match="provider close failed"):
        await provider_factory.aclose_providers()

    failing_provider.aclose.assert_awaited_once()
    next_provider.aclose.assert_awaited_once()


def test_default_transport_client_creation_is_thread_safe(
    monkeypatch: pytest.MonkeyPatch,
):
    clients = [_mock_client()]
    created = 0

    def create_client(**_: Any) -> MagicMock:
        nonlocal created
        created += 1
        return clients[0]

    monkeypatch.setattr(responses_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://responses.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    transport = DefaultResponsesTransport()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: transport._get_client(), range(32)))

    assert created == 1
    assert all(client is clients[0] for client in results)
