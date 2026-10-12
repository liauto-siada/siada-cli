"""Public-build tests for /configure and /logout (``siada.support.slash_commands``).

Both commands must keep working with the API-key-only sign-in flow: /configure
re-runs the frontend selector (cancel leaves the session untouched, success
switches the session to ``provider=default`` with the new credentials) and
/logout clears the stored provider API key without touching private credential
stores. Everything runs against a temporary ``~/.siada-cli``.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import siada.config.conf_store as conf_store

# Pre-import to break the circular-import chain of slash_commands
# (slash_commands -> checkpoint_tracker -> session.task_message_state), matching
# the other tests in this directory.
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.entrypoint.login import login_prompt
from siada.models.model_run_config import ModelRunConfig
from siada.support.slash_commands import SlashCommands, SwitchEvent

EXISTING_CONFIG = {
    "llm_config": {
        "provider": "default",
        "provider_id": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-existing",
        "model": "gpt-4o",
    }
}


class _FakeTransport:
    def __init__(self):
        self.is_connected = True
        self.messages = []

    def send_sync(self, message):
        self.messages.append(message)


class _FakeIO:
    def __init__(self, connected=True):
        self.infos = []
        self.errors = []
        self.acp_adapter = MagicMock()
        self.acp_adapter.transport = _FakeTransport() if connected else None

    def print_info(self, message):
        self.infos.append(message)

    def print_error(self, message):
        self.errors.append(message)

    def print_warning(self, message):
        pass

    def params(self, method):
        for message in self.acp_adapter.transport.messages:
            if message.method == method:
                return message.params
        return None


@pytest.fixture(autouse=True)
def temp_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(conf_store, "SIADA_HOME", Path(tmp_path))
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    monkeypatch.setattr(
        "siada.provider.models_dev.get_providers_for_ui",
        lambda: [{"id": "kimi", "name": "Kimi", "baseUrl": "https://x/v1", "apiKeyHint": "", "models": []}],
    )
    # Never consult the provider cache or install user model settings globally.
    monkeypatch.setattr("siada.provider.models_dev.get_provider_model_configs", lambda *a, **k: [])
    applied_models = []
    monkeypatch.setattr(
        "siada.models.model_base_config.set_user_model_settings",
        lambda models: applied_models.append(models),
    )
    return Path(tmp_path)


def _write_conf(home: Path, data: dict) -> None:
    (home / "conf.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _session(model_name: str = "claude-sonnet-5"):
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig(model_name)
    return session


def _choose(monkeypatch, raw: str) -> None:
    monkeypatch.setattr(login_prompt, "_read_acp_stdin_message", lambda: raw)


def _key_choice(payload: dict) -> str:
    return "__LOGIN_CHOICE__:3:" + json.dumps(payload)


# --------------------------------------------------------------------------- #
# /configure
# --------------------------------------------------------------------------- #
def test_configure_cancel_keeps_session_and_config(monkeypatch, temp_user_home):
    _write_conf(temp_user_home, EXISTING_CONFIG)
    io = _FakeIO()
    slash = SlashCommands(io=io)
    session = _session()
    original_llm_config = session.siada_config.llm_config
    _choose(monkeypatch, "__LOGIN_CHOICE__:cancel")

    result = slash.cmd_configure(session, "")

    assert result is None
    assert session.siada_config.llm_config is original_llm_config
    assert session.siada_config.llm_config.provider == original_llm_config.provider
    assert io.params("ui/loginDismiss") == {}
    assert login_prompt.get_applied_api_key_config() is None
    assert conf_store.get_conf_section("llm_config")["api_key"] == "sk-existing"


def test_configure_success_switches_session_to_new_provider(
    monkeypatch, temp_user_home
):
    io = _FakeIO()
    slash = SlashCommands(io=io)
    session = _session()
    _choose(
        monkeypatch,
        _key_choice(
            {
                "provider_id": "kimi",
                "api_key": "sk-kimi",
                "base_url": "https://api.moonshot.cn/v1",
                "model": "",
            }
        ),
    )

    result = slash.cmd_configure(session, "")

    assert isinstance(result, SwitchEvent)
    assert result.kwargs["model"] == session.siada_config.llm_config.model_name
    assert session.siada_config.llm_config.provider == "default"
    stored = conf_store.get_conf_section("llm_config")
    assert stored["provider"] == "default"
    assert stored["provider_id"] == "kimi"
    assert stored["api_key"] == "sk-kimi"
    assert io.params("ui/loginSuccess")["userId"] == "api-key-user:kimi"


def test_configure_success_with_model_applies_it(monkeypatch, temp_user_home):
    from siada.models.model_base_config import get_model_settings

    target_model = get_model_settings()[0].model_name
    io = _FakeIO()
    slash = SlashCommands(io=io)
    session = _session()
    _choose(
        monkeypatch,
        _key_choice(
            {
                "provider_id": "openai",
                "api_key": "sk-openai",
                "base_url": "https://api.openai.com/v1",
                "model": target_model,
            }
        ),
    )

    result = slash.cmd_configure(session, "")

    assert isinstance(result, SwitchEvent)
    assert result.kwargs["model"] == target_model
    assert session.siada_config.llm_config.model_name == target_model
    assert session.siada_config.llm_config.provider == "default"
    assert conf_store.get_conf_section("llm_config")["model"] == target_model


def test_configure_merges_without_replacing_models_json(monkeypatch, temp_user_home):
    """A reconfigure keeps the user's custom thinking/price fields this session."""
    from siada.models import model_base_config

    user_entry = model_base_config.ModelBaseConfig(
        model_name="gpt-4o",
        context_window=42_000,
        max_tokens=512,
        default_thinking_tokens=2048,
        default_reasoning_effort="high",
        input_price=1.5,
        output_price=3.0,
        cache_write_price=0.75,
        cache_read_price=0.25,
    )
    existing = [user_entry]
    # Build the session first: ModelRunConfig resolves against the live model
    # settings, and this test replaces them with its own user catalogue.
    session = _session()
    io = _FakeIO()
    slash = SlashCommands(io=io)
    monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
    monkeypatch.setattr(
        "siada.provider.models_dev.get_provider_model_configs",
        lambda *a, **k: [
            model_base_config.ModelBaseConfig(
                model_name="gpt-4o",
                context_window=128_000,
                max_tokens=8192,
                parallel_tool_calls=True,
            ),
            model_base_config.ModelBaseConfig(
                model_name="brand-new-model",
                context_window=128_000,
                max_tokens=8192,
                parallel_tool_calls=True,
            ),
        ],
    )
    _choose(
        monkeypatch,
        _key_choice(
            {
                "provider_id": "openai",
                "api_key": "sk-new",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
            }
        ),
    )

    result = slash.cmd_configure(session, "")

    assert isinstance(result, SwitchEvent)
    assert result.kwargs["model"] == "gpt-4o"
    assert model_base_config._user_model_settings is existing
    assert [entry.model_name for entry in existing] == ["gpt-4o", "brand-new-model"]
    kept = existing[0]
    assert kept.default_thinking_tokens == 2048
    assert kept.default_reasoning_effort == "high"
    assert kept.input_price == 1.5
    assert kept.output_price == 3.0
    assert kept.cache_write_price == 0.75
    assert kept.cache_read_price == 0.25
    assert kept.context_window == 42_000
    assert kept.max_tokens == 512


def test_configure_tolerates_wrongly_typed_applied_payload(
    monkeypatch, temp_user_home
):
    """A non-string applied field must not crash /configure (or fake a model)."""
    io = _FakeIO()
    slash = SlashCommands(io=io)
    session = _session("claude-sonnet-5")
    monkeypatch.setattr(
        login_prompt, "reconfigure_acp", lambda io_: "api-key-user:openai"
    )
    monkeypatch.setattr(
        login_prompt,
        "get_applied_api_key_config",
        lambda: {
            "provider_id": ["openai"],
            "base_url": 7,
            "model": 123,
            "api_key": "sk-x",
        },
    )

    result = slash.cmd_configure(session, "")

    assert isinstance(result, SwitchEvent)
    assert result.kwargs["model"] == "claude-sonnet-5"
    assert session.siada_config.llm_config.provider == "default"


def test_configure_requires_the_acp_ui(temp_user_home):
    io = _FakeIO(connected=False)
    slash = SlashCommands(io=io)
    session = _session()

    assert slash.cmd_configure(session, "") is None
    assert io.errors == ["This command requires the Siada UI."]


# --------------------------------------------------------------------------- #
# /logout
# --------------------------------------------------------------------------- #
def test_logout_removes_stored_api_key_config(temp_user_home):
    _write_conf(temp_user_home, EXISTING_CONFIG)
    io = _FakeIO()
    slash = SlashCommands(io=io)

    with pytest.raises(SystemExit):
        slash.cmd_logout("")

    assert io.infos == ["API key configuration removed."]
    assert conf_store.get_conf_section("llm_config").get("api_key") is None


def test_logout_without_stored_config(temp_user_home):
    io = _FakeIO()
    slash = SlashCommands(io=io)

    with pytest.raises(SystemExit):
        slash.cmd_logout("")

    assert io.infos == ["You were not signed in."]