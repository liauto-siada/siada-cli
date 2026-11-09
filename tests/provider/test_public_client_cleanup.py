"""Interrupted cleanup keeps cached HTTP clients reachable for a later retry."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["chat", "responses"])
async def test_cancelled_cleanup_retries_only_unfinished_clients(monkeypatch, kind):
    from siada.provider.default import chat_completions, responses_transport

    first = SimpleNamespace(close=AsyncMock(side_effect=[asyncio.CancelledError(), None]))
    second = SimpleNamespace(close=AsyncMock())
    clients = iter([first, second])
    module = chat_completions if kind == "chat" else responses_transport
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: next(clients))
    factory = (chat_completions.DefaultChatClientFactory() if kind == "chat"
               else responses_transport.DefaultResponsesTransport())
    get_client = factory.get_client if kind == "chat" else factory._get_client
    monkeypatch.setenv("BASE_URL", "https://cleanup.example/v1")
    monkeypatch.setenv("API_KEY", "synthetic-first-key")
    assert get_client() is first
    monkeypatch.setenv("API_KEY", "synthetic-second-key")
    assert get_client() is second
    with pytest.raises(asyncio.CancelledError):
        await factory.aclose()
    second.close.assert_not_awaited()
    await factory.aclose()
    assert first.close.await_count == 2
    second.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="closed"):
        get_client()