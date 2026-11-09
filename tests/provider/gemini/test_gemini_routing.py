from __future__ import annotations

import pytest
from agents.exceptions import UserError

from siada.provider.default.default_provider import DefaultProvider
from siada.provider.gemini import GeminiModel
from siada.provider.gemini.routing import is_gemini_model, wire_model_name
from siada.provider.token_counting import token_counting_info_from_model

from test_gemini_model import native_response, request_args, sse


@pytest.mark.parametrize("model_name", [
    "gemini-3.5-flash",
    "gemini/gemini-3.5-flash",
    "google/gemini-3.5-flash",
    "models/gemini-3.5-flash",
    "google-gemini",
    "google-gemini-3.5-flash",
    "GOOGLE-Gemini-2.5-pro",
    "vendor-gemini",
    "vendor-gemini-3.5-flash",
    "my-team-gemini-3.5-flash",
    "custom-gemini-model",
    "VENDOR-Gemini-2.5-pro",
])
def test_gemini_routes_recognize_derived_names(model_name):
    assert is_gemini_model(model_name)


@pytest.mark.parametrize("model_name", [
    None, "", "gpt-4o", "claude-sonnet-4.6", "custom-geminist-model",
    "google-geminist", "openrouter/google/gemini-3.5-flash",
    "openrouter/vendor-gemini-3.5-flash",
    "vertex_ai/gemini-3.5-flash",
])
def test_unrelated_and_compatibility_routes_are_unchanged(model_name):
    assert not is_gemini_model(model_name)


@pytest.mark.parametrize("model_name,expected", [
    ("gemini-3.5-flash", "gemini-3.5-flash"),
    ("gemini/gemini-3.5-flash", "gemini-3.5-flash"),
    ("google/gemini-3.5-flash", "gemini-3.5-flash"),
    ("models/gemini-3.5-flash", "gemini-3.5-flash"),
    ("google-gemini", "gemini"),
    ("google-gemini-3.5-flash", "gemini-3.5-flash"),
    ("GOOGLE-Gemini-2.5-pro", "Gemini-2.5-pro"),
    ("vendor-gemini", "gemini"),
    ("vendor-gemini-3.5-flash", "gemini-3.5-flash"),
    ("my-team-gemini-3.5-flash", "gemini-3.5-flash"),
    ("VENDOR-Gemini-2.5-pro", "Gemini-2.5-pro"),
    ("custom-gemini-model", "gemini-model"),
    ("gemini-custom-gemini-pro", "gemini-custom-gemini-pro"),
    ("vendor-gemini-custom-gemini-pro", "gemini-custom-gemini-pro"),
    ("openrouter/vendor-gemini-3.5-flash", "openrouter/vendor-gemini-3.5-flash"),
    ("google-geminist", "google-geminist"),
])
def test_wire_model_normalizes_only_supported_names(model_name, expected):
    assert wire_model_name(model_name) == expected
    assert wire_model_name(expected) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["default"])
@pytest.mark.parametrize("model_name", [
    "google-gemini-3.5-flash", "GOOGLE-Gemini-2.5-pro",
    "vendor-gemini-3.5-flash", "my-team-gemini-3.5-flash",
])
async def test_derived_names_share_native_route_and_counting(monkeypatch, provider_name, model_name):
    monkeypatch.setenv("BASE_URL", "https://gateway.test/v1")
    provider = DefaultProvider()
    try:
        info = provider.get_token_counting_info(model_name)
        first = provider.get_model(model_name)
        second = provider.get_model(model_name)
        assert isinstance(first, GeminiModel)
        assert isinstance(second, GeminiModel)
        assert first is not second and first._transport is second._transport
        assert first.model == wire_model_name(model_name)
        assert info.protocol == "gemini"
        assert info == token_counting_info_from_model(first) == token_counting_info_from_model(second)
    finally:
        await provider.aclose()


@pytest.mark.parametrize("model_name", [
    "gemini-3.5-flash", "google/gemini-3.5-flash", "google-gemini-3.5-flash",
    "vendor-gemini-3.5-flash", "my-team-gemini-3.5-flash",
    "openrouter/vendor-gemini-3.5-flash",
])
def test_openrouter_keeps_compatibility_route(monkeypatch, model_name):
    monkeypatch.setenv("BASE_URL", "https://openrouter.ai/api/v1")
    provider = DefaultProvider()
    route, info = provider._resolve_model_route(model_name, "https://openrouter.ai/api/v1")
    assert route == "litellm"
    assert info.protocol == "chat"
    assert info.model_name.startswith("openrouter/")
    assert provider.get_token_counting_info(model_name) == info
    assert provider._gemini_transport is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("model_name", ["google-gemini-3.5-flash", "my-team-gemini-3.5-flash"])
async def test_derived_name_sends_native_request_to_configured_endpoint(endpoint, monkeypatch, stream, model_name):
    monkeypatch.setenv("GEMINI_BASE_URL", endpoint.url + "/v1beta")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key")
    monkeypatch.setenv("BASE_URL", "https://chat.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-chat-key")
    monkeypatch.setenv("MODEL_NAME", model_name)
    response = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(response) if stream else response)]
    provider = DefaultProvider()
    try:
        model = provider.get_model(None)
        assert isinstance(model, GeminiModel)
        if stream:
            events = [event async for event in model.stream_response(**request_args())]
            assert events[-1].type == "response.completed"
        else:
            result = await model.get_response(**request_args())
            assert result.output
        assert provider.get_token_counting_info(None) == token_counting_info_from_model(model)
        assert len(endpoint.requests) == 1
        path, body, headers = endpoint.requests[0]
        method = "streamGenerateContent?alt=sse" if stream else "generateContent"
        assert path == f"/v1beta/models/gemini-3.5-flash:{method}"
        assert body["contents"][0]["parts"] == [{"text": "hello"}]
        assert "messages" not in body
        assert headers["x-goog-api-key"] == "synthetic-gemini-key"
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["vendor-gemini-3.5-flash", "my-team-gemini-3.5-flash"])
async def test_openrouter_wins_over_native_gemini_configuration(monkeypatch, model_name):
    from unittest.mock import AsyncMock

    import litellm
    import siada.entrypoint
    from litellm.types.utils import Choices, Message, ModelResponse

    monkeypatch.setenv("BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("API_KEY", "synthetic-openrouter-key")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://gemini.test/v1beta")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-key")
    monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
    completion = AsyncMock(return_value=ModelResponse(
        id="synthetic-response",
        choices=[Choices(message=Message(role="assistant", content="done"), finish_reason="stop")],
    ))
    monkeypatch.setattr(litellm, "acompletion", completion)
    provider = DefaultProvider()
    try:
        model = provider.get_model(model_name)
        assert not isinstance(model, GeminiModel)
        await model.get_response(**request_args())
        assert completion.await_count == 1
        kwargs = completion.await_args.kwargs
        assert kwargs["model"] == f"openrouter/{model_name}"
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
        assert kwargs["api_key"] == "synthetic-openrouter-key"
        assert provider.get_token_counting_info(model_name) == token_counting_info_from_model(model)
        assert provider._gemini_transport is None
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_openrouter_priority_uses_request_local_endpoint(monkeypatch):
    from agents.extensions.models.litellm_model import LitellmModel

    import siada.entrypoint

    monkeypatch.setenv("BASE_URL", "https://gateway.test/v1beta")
    monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
    provider = DefaultProvider()
    model_name = "vendor-gemini-3.5-flash"
    try:
        assert isinstance(provider.get_model(model_name), GeminiModel)
        with provider.request_scope(base_url="https://openrouter.ai/api/v1", api_key="synthetic-key"):
            model = provider.get_model(model_name)
            assert isinstance(model, LitellmModel)
            assert model.model == f"openrouter/{model_name}"
            assert provider.get_token_counting_info(model_name) == token_counting_info_from_model(model)
        assert isinstance(provider.get_model(model_name), GeminiModel)
        assert provider.get_token_counting_info(model_name).protocol == "gemini"
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_derived_name_preserves_chat_endpoint_validation(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://chat.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = DefaultProvider()
    try:
        model = provider.get_model("google-gemini-3.5-flash")
        assert isinstance(model, GeminiModel)
        with pytest.raises(UserError, match="Native Gemini requires a Gemini endpoint"):
            await model.get_response(**request_args())
        assert not model._transport._clients
    finally:
        await provider.aclose()