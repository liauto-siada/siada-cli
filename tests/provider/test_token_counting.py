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
    ("gemini-2.5-pro", "https://gateway.test/v1", TokenCountingInfo("gemini-2.5-pro", "gemini", "siada_gemini", replay_domain="default:gemini_api")),
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


@pytest.mark.parametrize("protocol", ["chat", "responses", "gemini", None])
def test_native_estimation_requires_explicit_gemini_protocol(monkeypatch, protocol):
    from siada.agent_hub.context_filter import utils
    from siada.provider.gemini import counting

    chat_counter = Mock(return_value=100)
    native_counter = Mock(return_value=200)
    monkeypatch.setattr(utils, "_calculate_tokens", chat_counter)
    monkeypatch.setattr(counting, "estimate_input_tokens", native_counter)
    info = TokenCountingInfo("opaque-wire-alias", protocol) if protocol else None
    items = [{"role": "user", "content": "synthetic"}]
    tokens = utils.calculate_tokens("google/gemini-3.5-flash", items, counting_info=info)
    if protocol == "gemini":
        assert tokens == 220
        native_counter.assert_called_once_with(items, None)
        chat_counter.assert_not_called()
    else:
        assert tokens == 110
        chat_counter.assert_called_once_with(info.model_name if info else "google/gemini-3.5-flash", items, tools=None)
        native_counter.assert_not_called()


def test_counting_retains_configured_name_when_model_has_no_name(monkeypatch):
    from siada.agent_hub.context_filter import utils
    from siada.provider.token_counting import context_token_counting_info

    info = TokenCountingInfo(None)
    context = SimpleNamespace(
        model_run_config=SimpleNamespace(model_name="gpt-4o", provider="unused"),
        runtime_session=SimpleNamespace(token_counting_info=info),
    )
    counter = Mock(return_value=100)
    monkeypatch.setattr(utils, "_calculate_tokens", counter)
    items = [{"role": "user", "content": "synthetic"}]
    assert utils.calculate_tokens("gpt-4o", items, counting_info=info) == 110
    counter.assert_called_once_with("gpt-4o", items, tools=None)
    assert context_token_counting_info(context) == TokenCountingInfo("gpt-4o")
    assert context.runtime_session.token_counting_info is info


def test_config_without_a_concrete_model_name_uses_unknown_counting_domain():
    from siada.provider.token_counting import token_counting_info_from_config

    assert token_counting_info_from_config(Mock()) == TokenCountingInfo(None)


def test_gemini_estimate_input_tokens_uses_litellm_token_counter(monkeypatch):
    import litellm
    from siada.provider.gemini.counting import estimate_input_tokens
    from siada.provider.gemini.replay import encode_replay

    text = "你好世界！Hello Gemini token counting."
    expected_text_tokens = litellm.token_counter(model="gemini", text=text)
    assert estimate_input_tokens(text) == expected_text_tokens
    assert estimate_input_tokens(text) < len(text.encode("utf-8"))

    replay_item = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
        "provider_data": {
            "gemini": encode_replay({
                "parts": [{
                    "content_index": 0,
                    "part_index": 0,
                    "part": {"text": text, "thought_signature": "x" * 2048},
                }],
            }),
        },
    }
    assert estimate_input_tokens([replay_item]) == expected_text_tokens + 4

    monkeypatch.setattr(litellm, "token_counter", Mock(side_effect=RuntimeError("unavailable")))
    assert estimate_input_tokens(text) == max(1, len(text) // 4)
