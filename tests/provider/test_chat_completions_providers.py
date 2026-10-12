"""Contract tests for the default-provider OpenAI Chat Completions adapter.

Covers the public ``default`` provider only: wire-model mapping/validation,
``DefaultChatClientFactory`` lifecycle (including the explicit-credential
deviation), and ``DefaultOpenAIChatCompletionsModel`` request/stream
behaviour (official SDK conversion, Kimi tool-call ordering, GLM reasoning
replay, ``ModelSettings.extra_headers``, stream cleanup).

Every request is mocked at the ``httpx`` transport boundary, so the suite runs
fully offline.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from agents import ModelSettings
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI

from siada.provider.default.chat_completions import (
    DefaultChatClientFactory,
    DefaultOpenAIChatCompletionsModel,
    get_default_chat_wire_model,
)


def _completion_response(model: str = "test-model") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 1,
            "total_tokens": 4,
        },
    }


def _mock_openai_factory(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[AsyncOpenAI]:
    clients: list[AsyncOpenAI] = []

    def create_client(**kwargs: Any) -> AsyncOpenAI:
        client = AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(module, "AsyncOpenAI", create_client)
    return clients


async def _get_response(model: Any, model_settings: ModelSettings | None = None):
    return await model.get_response(
        system_instructions="system instructions",
        input=[{"role": "user", "content": "hello"}],
        model_settings=model_settings or ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=ModelTracing.DISABLED,
    )


@pytest.mark.parametrize(
    ("model_name", "base_url", "expected"),
    [
        ("gpt-4o", "https://gateway.test/v1", "gpt-4o"),
        ("openai/gpt-4o", "https://gateway.test/v1", "gpt-4o"),
        ("deepseek/deepseek-chat", "https://gateway.test/v1", "deepseek-chat"),
        ("kimi-k2.5", "https://gateway.test/v1", "kimi-k2.5"),
        (
            "openrouter/anthropic/claude-sonnet-4",
            "https://openrouter.ai/api/v1",
            "anthropic/claude-sonnet-4",
        ),
    ],
)
def test_default_wire_model_mapping(model_name: str, base_url: str, expected: str):
    assert get_default_chat_wire_model(model_name, base_url) == expected


@pytest.mark.parametrize("model_name", ["anthropic/claude-3-opus", "gemini/gemini-2.5-pro"])
def test_default_chat_wire_model_rejects_native_protocols(model_name: str):
    with pytest.raises(ValueError, match="native protocol"):
        get_default_chat_wire_model(model_name, "https://gateway.test/v1")


def test_default_chat_wire_model_rejects_litellm_only_provider():
    with pytest.raises(ValueError, match="native protocol"):
        get_default_chat_wire_model("vertex_ai/gemini-2.5-pro", "https://gateway.test/v1")


def test_default_chat_wire_model_requires_endpoint_for_vendor_specific_model():
    with pytest.raises(ValueError, match="BASE_URL is required"):
        get_default_chat_wire_model("deepseek-v4-pro", None)


def test_default_chat_client_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    from siada.provider.default.chat_completions import DefaultChatClientFactory

    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(ValueError, match="API_KEY is required"):
        DefaultChatClientFactory().get_client()


@pytest.mark.asyncio
async def test_default_client_factory_pins_explicit_credentials(
    monkeypatch: pytest.MonkeyPatch,
):
    """Public deviation: explicit credentials stay off the process environment.

    ``DefaultChatClientFactory(base_url=..., api_key=...)`` is how a per-model
    ``fast_llm_config`` override keeps its endpoint and key on the client it
    builds, so rotating the environment must not rebuild or repoint it.
    """
    from siada.provider.default import chat_completions as chat_module

    created: list[MagicMock] = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock()
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    factory = DefaultChatClientFactory(
        base_url="https://pinned.test/v1", api_key="pinned-key"
    )

    client = factory.get_client()
    assert client is factory.get_client()
    assert len(created) == 1
    assert created[0].config["base_url"] == "https://pinned.test/v1"
    assert created[0].config["api_key"] == "pinned-key"

    monkeypatch.setenv("API_KEY", "env-key-rotated")
    assert factory.get_client() is client
    assert len(created) == 1

    await factory.aclose()
    client.close.assert_awaited_once()


def test_default_chat_model_exposes_read_only_client_credentials(
    monkeypatch: pytest.MonkeyPatch,
):
    """Public deviation: the model exposes its client's endpoint/key read-only.

    The values are read off the ``AsyncOpenAI`` client the factory built, so a
    caller can inspect the effective credentials without process-global state.
    """
    from siada.provider.default import chat_completions as chat_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_response(), request=request)

    clients = _mock_openai_factory(monkeypatch, chat_module, handler)
    factory = DefaultChatClientFactory(
        base_url="https://pinned.test/v1", api_key="pinned-key"
    )
    model = DefaultOpenAIChatCompletionsModel(
        model="gpt-4o",
        client_factory=factory,
        should_replay_reasoning_content=lambda _context: False,
    )

    assert clients
    assert model.api_key == "pinned-key"
    assert (model.base_url or "").rstrip("/") == "https://pinned.test/v1"
    with pytest.raises(AttributeError):
        model.api_key = "other-key"
    with pytest.raises(AttributeError):
        model.base_url = "https://other.test/v1"


@pytest.mark.asyncio
async def test_default_provider_sends_sdk_chat_request_and_reuses_client(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_response(), request=request)

    clients = _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-default-key")

    provider = DefaultProvider()
    model = provider.get_model("gpt-4o")
    second_model = provider.get_model("deepseek-v4-pro")
    assert model.model == "gpt-4o"
    assert second_model.model == "deepseek-v4-pro"
    assert len(clients) == 1

    model_settings = ModelSettings(
        max_tokens=256,
        extra_body={"reasoning_effort": "high", "enable_thinking": True},
    )
    response = await _get_response(model, model_settings)

    assert response.output
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-default-key"
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o"
    assert body["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "hello"},
    ]
    assert body["max_tokens"] == 256
    assert body["reasoning_effort"] == "high"
    assert body["enable_thinking"] is True
    # ADAPTED (sanitized): the source asserted that a private gateway header
    # was absent; this build names no gateway, so assert positively that the
    # wire carries exactly one credential header — the standard Bearer one.
    credential_headers = {
        name: value
        for name, value in request.headers.items()
        if "auth" in name.lower() or "token" in name.lower()
    }
    assert credential_headers == {"authorization": "Bearer test-default-key"}

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_chat_model_sends_model_settings_extra_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    """Caller-supplied ``ModelSettings.extra_headers`` reach the wire as-is."""
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")

    provider = DefaultProvider()
    model = provider.get_model("gpt-4o")
    settings = ModelSettings(
        extra_headers={"x-synthetic-caller": "synthetic-test"},
        extra_body={"reasoning_effort": "high"},
    )

    response = await _get_response(model, settings)

    assert response.output
    assert requests[0].headers["x-synthetic-caller"] == "synthetic-test"
    assert json.loads(requests[0].content)["reasoning_effort"] == "high"

    await provider.aclose()


@pytest.mark.asyncio
async def test_official_chat_model_preserves_tool_call_ids_and_usage(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-tool-call",
                "object": "chat.completion",
                "created": 2,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-preserved",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"src/app.py"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                    "prompt_tokens_details": {"cached_tokens": 5},
                },
            },
            request=request,
        )

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()
    model = provider.get_model("gpt-4o")

    response = await _get_response(model)

    tool_call = next(
        item
        for item in response.output
        if getattr(item, "type", None) == "function_call"
    )
    assert tool_call.call_id == "call-preserved"
    assert tool_call.name == "read_file"
    assert json.loads(tool_call.arguments) == {"path": "src/app.py"}
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 16
    assert response.usage.input_tokens_details.cached_tokens == 5

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_kimi_model_pairs_tool_results_before_sdk_conversion(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()
    model = provider.get_model("kimi-k2.5")
    input_items = [
        {"type": "function_call", "call_id": "call-a", "name": "tool_a", "arguments": "{}"},
        {
            "type": "message",
            "id": "message-1",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "working"}],
        },
        {"type": "function_call", "call_id": "call-b", "name": "tool_b", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call-a", "output": "result-a"},
        {"type": "function_call_output", "call_id": "call-b", "output": "result-b"},
        {"role": "user", "content": "continue"},
    ]

    await model.get_response(
        system_instructions=None,
        input=input_items,
        model_settings=ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=ModelTracing.DISABLED,
    )

    messages = captured[0]["messages"]
    roles = [message["role"] for message in messages]
    assert roles == ["assistant", "tool", "assistant", "tool", "user"]
    assert messages[1]["tool_call_id"] == "call-a"
    assert messages[1]["content"] == "result-a"
    assert messages[3]["tool_call_id"] == "call-b"
    assert messages[3]["content"] == "result-b"
    assert input_items[3]["type"] == "function_call_output"

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_deepseek_keeps_sdk_tool_messages_unmerged(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()
    model = provider.get_model("deepseek-v4-pro")
    items = [
        {"type": "function_call", "call_id": "call-a", "name": "tool_a", "arguments": "{}"},
        {
            "type": "message",
            "id": "message-1",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "progress"}],
        },
        {"type": "function_call", "call_id": "call-b", "name": "tool_b", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call-a", "output": "result-a"},
        {"type": "function_call_output", "call_id": "call-b", "output": "result-b"},
        {"role": "user", "content": "continue"},
    ]

    await model.get_response(
        system_instructions=None,
        input=items,
        model_settings=ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=ModelTracing.DISABLED,
    )

    messages = captured[0]["messages"]
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert [message["role"] for message in messages] == ["assistant", "tool", "tool", "user"]
    assert [
        call["id"] for call in assistant_messages[0]["tool_calls"]
    ] == ["call-a", "call-b"]

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_chat_model_replays_only_matching_provider_reasoning(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()
    model = provider.get_model("glm-5.2")

    def history(origin_model: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "reasoning-1",
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "private reasoning"}],
                "provider_data": {"model": origin_model},
            },
            {
                "id": "message-1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "answer"}],
                "status": "completed",
            },
            {"role": "user", "content": "follow up"},
        ]

    for items in (history("glm-5.2"), history("deepseek-v4-pro")):
        await model.get_response(
            system_instructions=None,
            input=items,
            model_settings=ModelSettings(),
            tools=[],
            output_schema=None,
            handoffs=[],
            tracing=ModelTracing.DISABLED,
        )

    matching_assistant = next(message for message in captured[0]["messages"] if message["role"] == "assistant")
    mismatching_assistant = next(message for message in captured[1]["messages"] if message["role"] == "assistant")
    assert matching_assistant["reasoning_content"] == "private reasoning"
    assert "reasoning_content" not in mismatching_assistant

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_client_factory_rebuilds_on_credentials_change_and_closes_clients(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module

    created = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock()
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("API_KEY", "key-one")
    monkeypatch.setenv("BASE_URL", "https://one.test/v1")
    factory = DefaultChatClientFactory()

    first = factory.get_client()
    assert factory.get_client() is first
    monkeypatch.setenv("API_KEY", "key-two")
    second = factory.get_client()
    assert second is not first
    assert len(created) == 2

    await factory.aclose()
    first.close.assert_awaited_once()
    second.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_factory_closes_provider_owned_clients(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider import provider_factory

    provider = MagicMock()
    provider.aclose = AsyncMock()
    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": provider})

    await provider_factory.aclose_providers()

    provider.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_chat_model_closes_the_sdk_stream_after_consumption(
    monkeypatch: pytest.MonkeyPatch,
):
    """``RefreshingOpenAIClientMixin`` closes the SDK stream it wraps.

    Replaces the source streaming test, which exercised a non-public provider
    path: the shared mixin must close the async generator even when the caller
    drains it to the end.
    """
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")

    events = [MagicMock(type="response.output_text.delta"), MagicMock(type="response.completed")]

    class FakeSDKStream:
        def __init__(self) -> None:
            self.closed = False

        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            for event in events:
                yield event

        async def aclose(self) -> None:
            self.closed = True

    stream = FakeSDKStream()
    monkeypatch.setattr(
        OpenAIChatCompletionsModel,
        "stream_response",
        lambda self, *args, **kwargs: stream,
    )

    provider = DefaultProvider()
    model = provider.get_model("gpt-4o")
    received = [
        event
        async for event in model.stream_response(
            system_instructions="system instructions",
            input=[{"role": "user", "content": "hello"}],
            model_settings=ModelSettings(),
            tools=[],
            output_schema=None,
            handoffs=[],
            tracing=ModelTracing.DISABLED,
        )
    ]

    assert received == events
    assert stream.closed is True

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_client_factory_close_attempts_every_client_and_aggregates_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failing close must not strand the factory's other clients.

    The factory detaches its clients before closing, so a close that raises
    would otherwise leak every remaining client (and a retry would find
    nothing left to close). A single failure is re-raised unchanged; several
    are aggregated.
    """
    from siada.provider.default import chat_completions as chat_module

    created = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock()
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("API_KEY", "key-one")
    monkeypatch.setenv("BASE_URL", "https://one.test/v1")
    factory = DefaultChatClientFactory()

    factory.get_client()  # retired: replaced below
    monkeypatch.setenv("API_KEY", "key-two")
    factory.get_client()  # current client
    monkeypatch.setenv("API_KEY", "key-three")
    factory.get_client()  # current client
    assert len(created) == 3

    created[0].close = AsyncMock(side_effect=OSError("first close failed"))
    created[1].close = AsyncMock(side_effect=OSError("second close failed"))

    with pytest.raises(ExceptionGroup) as excinfo:
        await factory.aclose()

    assert len(excinfo.value.exceptions) == 2
    for client in created:
        client.close.assert_awaited_once()

    # The factory is empty afterwards: a second close is a no-op, not a repeat.
    await factory.aclose()
    for client in created:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_client_factory_reports_a_single_close_failure_as_is(
    monkeypatch: pytest.MonkeyPatch,
):
    from siada.provider.default import chat_completions as chat_module

    created = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock(side_effect=OSError("close failed"))
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("API_KEY", "key-one")
    factory = DefaultChatClientFactory()

    factory.get_client()

    with pytest.raises(OSError, match="close failed"):
        await factory.aclose()

    created[0].close.assert_awaited_once()


@pytest.mark.parametrize(
    ("env_model_name", "expected_litellm_model"),
    [
        ("claude-sonnet-4.6", "anthropic/claude-sonnet-4.6"),
        ("gemini-2.5-pro", "gemini/gemini-2.5-pro"),
        ("openai/responses/codex-mini-latest", "openai/responses/codex-mini-latest"),
    ],
)
def test_default_provider_get_model_none_resolves_model_name_env_on_retained_routes(
    monkeypatch: pytest.MonkeyPatch,
    env_model_name: str,
    expected_litellm_model: str,
):
    """``get_model(None)`` keeps its documented ``MODEL_NAME`` fallback.

    The SDK calls ``ModelProvider.get_model(agent.model)`` with ``None`` when an
    agent carries no model of its own, so every route — including the retained
    Claude / Gemini / Responses-bridge LiteLLM path — must resolve the
    environment name instead of handing the unresolved argument to name parsing.
    """
    import siada.entrypoint

    from siada.provider.default.default_provider import DefaultProvider

    monkeypatch.setenv("MODEL_NAME", env_model_name)
    monkeypatch.setenv("BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)

    model = DefaultProvider().get_model(None)

    assert model.model == expected_litellm_model


@pytest.mark.asyncio
async def test_default_provider_get_model_none_without_model_name_env_builds_chat_model(
    monkeypatch: pytest.MonkeyPatch,
):
    """With no ``MODEL_NAME`` there is nothing to resolve — and nothing to crash."""
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_response(), request=request)

    _mock_openai_factory(monkeypatch, chat_module, handler)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.setenv("BASE_URL", "https://default.test/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    provider = DefaultProvider()

    model = provider.get_model(None)

    assert isinstance(model, DefaultOpenAIChatCompletionsModel)
    # Environment path: the shared factory, never a pinned override factory.
    assert model._client_factory is provider._chat_client_factory
    assert provider._pinned_chat_client_factories == {}

    await provider.aclose()


@pytest.mark.asyncio
async def test_default_provider_reuses_one_pinned_factory_per_override_credentials(
    monkeypatch: pytest.MonkeyPatch,
):
    """Repeated identical overrides share one pinned factory — and one client.

    A ``fast_llm_config`` override is resolved once per task, so building a
    fresh pinned factory (and a fresh ``AsyncOpenAI`` with its own connection
    pool) on every call would grow the provider's holdings with the run count,
    until ``aclose()``. The credentials are frozen on the factory, so two calls
    with the same pair can safely share it; a different pair still gets its own.
    """
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    created: list[MagicMock] = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock()
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("API_KEY", "env-key")
    provider = DefaultProvider()
    assert provider._pinned_chat_client_factories == {}

    models = [
        provider.get_model_with_credentials(
            "gpt-4o", base_url="https://fast.test/v1", api_key="fast-key"
        )
        for _ in range(20)
    ]

    assert len(provider._pinned_chat_client_factories) == 1
    assert len(created) == 1
    assert all(model._client_factory is models[0]._client_factory for model in models)
    assert created[0].config["base_url"] == "https://fast.test/v1"
    assert created[0].config["api_key"] == "fast-key"

    other = provider.get_model_with_credentials(
        "gpt-4o", base_url="https://fast.test/v1", api_key="other-key"
    )
    assert len(provider._pinned_chat_client_factories) == 2
    assert len(created) == 2
    assert other._client_factory is not models[0]._client_factory
    assert created[1].config["api_key"] == "other-key"

    # The environment path keeps using the shared factory and pins nothing.
    env_model = provider.get_model("gpt-4o")
    assert env_model._client_factory is provider._chat_client_factory
    assert len(provider._pinned_chat_client_factories) == 2
    assert len(created) == 3

    await provider.aclose()

    assert provider._pinned_chat_client_factories == {}
    for client in created:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_provider_aclose_closes_pinned_factories_and_aggregates_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    """``aclose`` reaches the pinned factories and reports every failure.

    The pinned factories own the override clients, so they are closed with the
    shared ones even while the shared close fails, the Responses transport is
    still closed after the chat failure, and the cache ends up empty.
    """
    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.default_provider import DefaultProvider

    created: list[MagicMock] = []

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.close = AsyncMock()
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("API_KEY", "env-key")
    provider = DefaultProvider()
    provider.get_model_with_credentials(
        "gpt-4o", base_url="https://fast.test/v1", api_key="fast-key"
    )
    provider._chat_client_factory.aclose = AsyncMock(
        side_effect=OSError("chat close failed")
    )
    provider._responses_transport.aclose = AsyncMock(
        side_effect=ValueError("responses close failed")
    )

    with pytest.raises(ExceptionGroup) as excinfo:
        await provider.aclose()

    assert {type(error) for error in excinfo.value.exceptions} == {OSError, ValueError}
    provider._chat_client_factory.aclose.assert_awaited_once()
    provider._responses_transport.aclose.assert_awaited_once()
    assert provider._pinned_chat_client_factories == {}
    for client in created:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_client_factory_aclose_cancellation_keeps_clients_owned(
    monkeypatch: pytest.MonkeyPatch,
):
    """A cancelled ``aclose`` must not drop the clients it has not closed.

    ``asyncio.CancelledError`` is a ``BaseException``, so it is not an ordinary
    close failure: it propagates unchanged (the caller's cancellation is never
    swallowed) and the clients whose close was not confirmed — the interrupted
    one included — stay owned by the factory, so a later ``aclose`` still
    closes them instead of them being detached beyond reach.
    """
    from siada.provider.default import chat_completions as chat_module

    created: list[MagicMock] = []
    started: list[int] = []
    closed: list[int] = []
    gate = asyncio.Event()

    def create_client(**kwargs: Any) -> MagicMock:
        client = MagicMock()
        client.config = kwargs
        created.append(client)
        return client

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", "https://one.test/v1")
    monkeypatch.setenv("API_KEY", "key-one")
    factory = DefaultChatClientFactory()

    factory.get_client()
    monkeypatch.setenv("API_KEY", "key-two")
    factory.get_client()
    monkeypatch.setenv("API_KEY", "key-three")
    factory.get_client()
    assert len(created) == 3

    def gated_close(index: int):
        async def close() -> None:
            started.append(index)
            if index == 0:
                await gate.wait()
            closed.append(index)

        return close

    for index, client in enumerate(created):
        client.close = gated_close(index)

    task = asyncio.ensure_future(factory.aclose())
    for _ in range(100):
        if started:
            break
        await asyncio.sleep(0)
    assert started == [0]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert closed == []
    assert factory._retired_clients == created

    gate.set()
    await factory.aclose()

    assert closed == [0, 1, 2]
    assert factory._retired_clients == []
    assert factory._client is None

    # Nothing left to close: the retry is not a repeat of the same closes.
    await factory.aclose()
    assert closed == [0, 1, 2]