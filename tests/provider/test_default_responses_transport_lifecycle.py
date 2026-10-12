from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.provider.default import responses_transport as responses_module
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.default.responses_transport import DefaultResponsesTransport
from siada.provider.responses.transport import ResponsesTransport


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


@pytest.mark.asyncio
async def test_default_transport_aclose_cancellation_keeps_clients_owned(
    monkeypatch: pytest.MonkeyPatch,
):
    """A cancelled ``aclose`` keeps the clients whose close it did not confirm.

    ``asyncio.CancelledError`` is a ``BaseException``, so it is not an ordinary
    close failure: it propagates unchanged (the caller's cancellation is never
    swallowed) and the remaining clients stay owned by the transport, so a later
    ``aclose`` still closes them instead of returning early on ``_closed`` and
    leaking them. ``_closed`` itself keeps refusing new work.
    """
    clients = [_mock_client(), _mock_client()]
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
    assert len(created) == 2

    started: list[int] = []
    closed: list[int] = []
    gate = asyncio.Event()

    def gated_close(index: int):
        async def close() -> None:
            started.append(index)
            if index == 0:
                await gate.wait()
            closed.append(index)

        return close

    for index, client in enumerate(clients):
        client.close = gated_close(index)

    task = asyncio.ensure_future(transport.aclose())
    for _ in range(100):
        if started:
            break
        await asyncio.sleep(0)
    assert started == [0]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert closed == []
    assert transport._closed is True
    assert transport._retired_clients == clients
    with pytest.raises(RuntimeError, match="is closed"):
        transport._get_client()

    gate.set()
    await transport.aclose()

    assert closed == [0, 1]
    assert transport._retired_clients == []
    assert transport._client is None

    # Nothing left to close: the retry is not a repeat of the same closes.
    await transport.aclose()
    assert closed == [0, 1]