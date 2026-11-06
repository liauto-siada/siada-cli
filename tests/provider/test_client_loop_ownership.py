"""Reject cross-loop cache access before entering native HTTP connection pools."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.provider.default import chat_completions as default_chat
from siada.provider.default import responses_transport as responses


@pytest.fixture(params=["default-chat", "default-responses"])
def cache(request, monkeypatch):
    clients = []

    def make_client(**kwargs):
        client = MagicMock()
        client.close = AsyncMock()
        clients.append(client)
        return client

    monkeypatch.setenv("BASE_URL", "https://synthetic.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    if request.param == "default-chat":
        monkeypatch.setattr(default_chat, "AsyncOpenAI", make_client)
        factory = default_chat.DefaultChatClientFactory()
        get_client = factory.get_client
    else:
        monkeypatch.setattr(responses, "AsyncOpenAI", make_client)
        factory = responses.DefaultResponsesTransport()
        get_client = factory._get_client
    return factory, get_client, clients


@pytest.mark.parametrize("close_owner_loop", [False, True])
def test_cache_rejects_other_live_or_closed_loop(cache, close_owner_loop):
    factory, get_client, clients = cache
    owner = asyncio.new_event_loop()
    foreign = asyncio.new_event_loop()

    async def access():
        return get_client()

    try:
        first = owner.run_until_complete(access())
        assert owner.run_until_complete(access()) is first
        if close_owner_loop:
            owner.close()
        with pytest.raises(RuntimeError, match="different event loop"):
            foreign.run_until_complete(access())
        with pytest.raises(RuntimeError, match="different event loop"):
            foreign.run_until_complete(factory.aclose())
        assert clients == [first]
        first.close.assert_not_called()
    finally:
        if not owner.is_closed():
            owner.run_until_complete(factory.aclose())
            owner.close()
        else:
            # No real sockets were opened; the mock can be released safely.
            foreign.run_until_complete(clients[0].close())
        foreign.close()


def test_cache_can_be_constructed_synchronously_then_binds_to_execution_loop(cache):
    factory, get_client, clients = cache
    first = get_client()

    async def run():
        assert get_client() is first
        await factory.aclose()
        await factory.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            get_client()

    asyncio.run(run())
    assert len(clients) == 1
    first.close.assert_awaited_once()
