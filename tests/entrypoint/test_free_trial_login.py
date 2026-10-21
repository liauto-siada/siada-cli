"""Anonymous trial login persistence and transport boundaries."""

import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2 as httpx
import pytest

from siada.config import conf_store
from siada.entrypoint.login import login_prompt
from siada.provider.default.chat_completions import (
    DefaultChatClientFactory,
    get_default_chat_wire_model,
)
from siada.provider.free_trial import (
    FREE_TRIAL_BASE_URL,
    FREE_TRIAL_MODEL_IDS,
    FREE_TRIAL_MODELS,
    FREE_TRIAL_PROVIDER_ID,
)
from siada.provider.models_dev import get_provider_model_configs
from siada.provider.request_config import default_credentials_scope


@pytest.fixture
def trial(monkeypatch, tmp_path):
    monkeypatch.setattr(conf_store, "SIADA_HOME", tmp_path)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    notifications = []
    monkeypatch.setattr(
        login_prompt, "_send_acp_notification",
        lambda io, method, params: notifications.append((method, params)),
    )
    return notifications


@pytest.mark.parametrize("reconfigure", [False, True])
def test_trial_choice_persists_and_restarts_without_key(trial, monkeypatch, reconfigure):
    monkeypatch.setenv("BASE_URL", "https://previous.example/v1")
    monkeypatch.setenv("API_KEY", "synthetic-previous-key")
    model = FREE_TRIAL_MODELS[0][0]
    monkeypatch.setattr(
        login_prompt, "_read_acp_stdin_message",
        lambda: '__LOGIN_CHOICE__:4:' + json.dumps({"model": model}),
    )
    monkeypatch.setattr("siada.provider.models_dev.get_providers_for_ui", lambda: [])
    io = SimpleNamespace(acp_adapter=SimpleNamespace(transport=SimpleNamespace(is_connected=True)))
    entry = login_prompt.reconfigure_acp if reconfigure else login_prompt._ensure_logged_in_acp
    assert entry(io) == f"api-key-user:{FREE_TRIAL_PROVIDER_ID}"
    assert trial[0][0] == "ui/showLoginSelector"
    assert {m["id"] for m in trial[0][1]["freeTrialModels"]} == FREE_TRIAL_MODEL_IDS
    assert trial[-1][0] == "ui/loginSuccess"
    assert os.environ["API_KEY"] == ""
    assert conf_store.get_conf_section("llm_config")["api_key"] == ""
    monkeypatch.delenv("BASE_URL")
    monkeypatch.delenv("API_KEY")
    assert login_prompt.ensure_logged_in(io, acp_mode=True) == f"api-key-user:{FREE_TRIAL_PROVIDER_ID}"
    assert login_prompt.get_applied_api_key_config()["model"] == model


@pytest.mark.parametrize("payload", [
    "", "invalid-json", "[]", '{"model": null}', '{"model": 42}',
    '{"model": "openai/paid-model"}', '{"model": "kili-auto/free"}',
])
def test_invalid_trial_payload_does_not_modify_config_or_credentials(trial, monkeypatch, payload):
    monkeypatch.setenv("API_KEY", "synthetic-previous-key")
    assert login_prompt._handle_free_trial_config(payload, MagicMock()) is None
    assert trial[-1][0] == "ui/loginError"
    assert os.environ["API_KEY"] == "synthetic-previous-key"
    assert conf_store.get_conf_section("llm_config") == {}


def test_trial_save_failure_preserves_previous_credentials(trial, monkeypatch):
    monkeypatch.setenv("API_KEY", "synthetic-previous-key")
    monkeypatch.setattr(login_prompt, "_save_provider_config", lambda *args: False)
    assert login_prompt._handle_free_trial_config(
        json.dumps({"model": FREE_TRIAL_MODELS[0][0]}), MagicMock(),
    ) is None
    assert trial[-1][0] == "ui/loginError"
    assert os.environ["API_KEY"] == "synthetic-previous-key"
    assert login_prompt.get_applied_api_key_config() is None


def test_trial_ignores_client_supplied_endpoint_and_key(trial):
    assert login_prompt._handle_free_trial_config(json.dumps({
        "model": FREE_TRIAL_MODELS[0][0], "api_key": "synthetic-key",
        "base_url": "https://other.example/v1",
    }), MagicMock())
    applied = login_prompt.get_applied_api_key_config()
    assert applied["base_url"] == FREE_TRIAL_BASE_URL
    assert applied["api_key"] == ""


def test_trial_can_switch_back_to_api_key(trial):
    io = MagicMock()
    login_prompt._handle_free_trial_config(json.dumps({"model": FREE_TRIAL_MODELS[0][0]}), io)
    assert login_prompt._handle_provider_api_key_config({
        "provider_id": "custom", "base_url": "https://other.example/v1",
        "api_key": "synthetic-key", "model": "custom-model",
    }, io)
    assert os.environ["API_KEY"] == "synthetic-key"
    assert conf_store.get_conf_section("llm_config")["provider_id"] == "custom"


def test_tty_trial_defaults_and_reports_save_failure(trial, monkeypatch):
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr(login_prompt, "_acp_transport_connected", lambda io: False)
    values = iter(["2", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(values))
    io = MagicMock()
    assert login_prompt._ensure_logged_in_tty(io) == f"api-key-user:{FREE_TRIAL_PROVIDER_ID}"
    io.print_info.assert_any_call(f"Free trial configured: {FREE_TRIAL_MODELS[0][0]}")
    monkeypatch.setattr(login_prompt, "_save_provider_config", lambda *args: False)
    values = iter(["2", "1"])
    assert login_prompt._ensure_logged_in_tty(io) is None
    io.print_error.assert_called_with(login_prompt._save_failed_message())


@pytest.mark.parametrize("field,value", [
    ("base_url", "https://other.example/v1"),
    ("provider_id", "custom"),
    ("model", "unknown"),
])
def test_corrupt_stored_trial_cannot_skip_login(trial, field, value):
    login_prompt._save_provider_config(
        FREE_TRIAL_PROVIDER_ID, "", FREE_TRIAL_BASE_URL, FREE_TRIAL_MODELS[0][0],
    )
    conf_store.update_conf(lambda data: data["llm_config"].update({field: value}))
    assert login_prompt._resolve_session_credentials() is None


def test_free_models_available_without_network(trial, monkeypatch):
    monkeypatch.setattr("siada.provider.models_dev.get_providers_for_ui", lambda: pytest.fail("network catalogue"))
    models = get_provider_model_configs(FREE_TRIAL_PROVIDER_ID, FREE_TRIAL_MODELS[0][0], FREE_TRIAL_BASE_URL)
    assert {model.model_name for model in models} == FREE_TRIAL_MODEL_IDS
    for model in models:
        assert get_default_chat_wire_model(model.model_name, FREE_TRIAL_BASE_URL) == model.model_name


@pytest.mark.asyncio
async def test_anonymous_transport_omits_auth_and_keeps_request_scopes_isolated(trial, monkeypatch):
    from openai import AsyncOpenAI

    captured = []

    async def respond(request):
        captured.append(request)
        return httpx.Response(200, json={
            "id": "synthetic", "object": "chat.completion", "created": 0,
            "model": FREE_TRIAL_MODELS[0][0],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "5"}}],
        })

    def make_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr("siada.provider.default.chat_completions.AsyncOpenAI", make_client)
    from siada.provider.default.chat_completions import AnonymousTrialOpenAI

    def make_anonymous_client(**kwargs):
        return AnonymousTrialOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )

    monkeypatch.setattr("siada.provider.default.chat_completions.AnonymousTrialOpenAI", make_anonymous_client)
    monkeypatch.setenv("BASE_URL", FREE_TRIAL_BASE_URL)
    monkeypatch.setenv("API_KEY", "")
    # Empty credentials must not fall back to the vendor environment key.
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-vendor-key")
    factory = DefaultChatClientFactory()

    async def call():
        return await factory.get_client().chat.completions.create(
            model=FREE_TRIAL_MODELS[0][0], messages=[{"role": "user", "content": "2+3?"}],
        )

    async def authenticated_override():
        with default_credentials_scope(base_url="https://other.example/v1", api_key="synthetic-other-key"):
            return await call()

    try:
        await asyncio.gather(call(), authenticated_override())
        free = next(r for r in captured if r.url.host == "api.kilo.ai")
        paid = next(r for r in captured if r.url.host == "other.example")
        assert "authorization" not in free.headers
        assert paid.headers["authorization"] == "Bearer synthetic-other-key"
        assert json.loads(free.content)["model"] == FREE_TRIAL_MODELS[0][0]
        monkeypatch.setenv("BASE_URL", "https://paid.example/v1")
        monkeypatch.setenv("API_KEY", "synthetic-paid-key")
        await call()
        assert captured[-1].headers["authorization"] == "Bearer synthetic-paid-key"
        monkeypatch.setenv("API_KEY", "")
        with pytest.raises(ValueError, match="API_KEY is required"):
            factory.get_client()
    finally:
        await factory.aclose()