"""Public provider counting descriptions require neither models nor clients."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.provider.default.default_provider import DefaultProvider
from siada.provider.token_counting import TokenCountingInfo, token_counting_info_from_model
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper


@pytest.mark.parametrize("name,endpoint,expected", [
    ("gpt-4o", "https://gateway.test/v1", TokenCountingInfo("gpt-4o")),
    ("openai/gpt-4o", "https://gateway.test/v1", TokenCountingInfo("gpt-4o")),
    ("deepseek-v3.1", "https://gateway.test/v1", TokenCountingInfo("deepseek-chat-v3.1")),
    ("kimi-k2.5", "https://gateway.test/v1", TokenCountingInfo("kimi-k2.5")),
    ("gpt-5.4", "https://gateway.test/v1", TokenCountingInfo("gpt-5.4", "responses", "siada_responses")),
    ("claude-sonnet-4.6", "https://gateway.test/v1", TokenCountingInfo("anthropic/claude-sonnet-4.6")),
    ("gemini-2.5-pro", "https://gateway.test/v1", TokenCountingInfo("gemini/gemini-2.5-pro")),
    ("codex-mini-latest", "https://gateway.test/v1", TokenCountingInfo("openai/responses/codex-mini-latest")),
    ("gpt-4o", "https://openrouter.ai/api/v1", TokenCountingInfo("openai/gpt-4o")),
    ("openrouter/openai/gpt-4o", "https://openrouter.ai/api/v1", TokenCountingInfo("openai/gpt-4o")),
    ("claude-sonnet-4.6", "https://openrouter.ai/api/v1", TokenCountingInfo("openrouter/anthropic/claude-sonnet-4.6")),
])
def test_default_counting_information_uses_existing_routes_without_creation(monkeypatch, name, endpoint, expected):
    monkeypatch.setenv("BASE_URL", endpoint)
    monkeypatch.delenv("API_KEY", raising=False)
    provider = DefaultProvider()
    create = Mock(side_effect=AssertionError("Counting must not create a client"))
    monkeypatch.setattr(provider._chat_client_factory, "get_client", create)
    assert provider.get_token_counting_info(name) == expected
    assert provider.get_token_counting_info(name) == expected
    assert provider.base_url is None and provider.api_key is None
    create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["gpt-4o", "gpt-5.4", "claude-sonnet-4.6", "gemini-2.5-pro", "codex-mini-latest"])
async def test_default_counting_description_matches_fresh_actual_models(monkeypatch, name):
    import siada.entrypoint

    monkeypatch.setenv("BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
    provider = DefaultProvider()
    try:
        info = provider.get_token_counting_info(name)
        first = provider.get_model(name)
        second = provider.get_model(name)
        assert first is not second
        assert info == token_counting_info_from_model(first) == token_counting_info_from_model(second)
        if name == "gpt-4o":
            assert first._client is second._client
        elif name == "gpt-5.4":
            assert first._transport is second._transport
    finally:
        await provider.aclose()


def test_default_route_uses_request_local_endpoint_and_environment_model(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o")
    provider = DefaultProvider()
    assert provider.get_token_counting_info(None) == TokenCountingInfo("gpt-4o")
    with provider.request_scope(base_url="https://openrouter.ai/api/v1", api_key="synthetic-key"):
        assert provider.get_token_counting_info(None) == TokenCountingInfo("openai/gpt-4o")
    assert provider.get_token_counting_info(None) == TokenCountingInfo("gpt-4o")


def test_counting_information_is_frozen_and_does_not_retain_model():
    model = SimpleNamespace(model="glm-test")
    info = token_counting_info_from_model(ModelWrapper(model, input_processor=process_input))
    model.model = "changed-model"
    assert info == TokenCountingInfo("glm-test")
    with pytest.raises(FrozenInstanceError):
        info.model_name = "changed-model"
    assert all(value is not model for value in vars(info).values())


def test_provider_wrappers_forward_counting_information_without_model_resolution():
    base = SimpleNamespace(get_model=Mock(), get_token_counting_info=Mock(return_value=TokenCountingInfo("glm-test")))
    wrapped = ModelProviderWrapper(ModelProviderWrapper(base, process_input))
    assert wrapped.get_token_counting_info("synthetic-alias") == TokenCountingInfo("glm-test")
    base.get_token_counting_info.assert_called_once_with("synthetic-alias")
    base.get_model.assert_not_called()
    opaque = ModelProviderWrapper(base, lambda value: value)
    assert opaque.get_token_counting_info("synthetic-alias").unavailable_reason == "opaque_processor"
