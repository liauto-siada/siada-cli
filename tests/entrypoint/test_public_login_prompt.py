"""Public-build sign-in flow tests (siada.entrypoint.login.login_prompt).

The open-source build authenticates with the user's own provider API key, so
the module must offer exactly one sign-in method while keeping the established
frontend contract:

* ``ui/showLoginSelector`` — always with ``liidDisabled`` (and ``cancelable``
  in the ``/configure`` re-run), so the frontend renders the API key wizard.
* ``__LOGIN_CHOICE__:3:<json>`` with ``provider_id`` / ``api_key`` /
  ``base_url`` / ``model`` — the payload the frontend already sends. A payload
  missing ``base_url``/``api_key`` (or carrying a field of the wrong JSON type)
  is rejected with a ``ui/loginError``; it never raises and never signs in.
* ``ui/loginSuccess`` / ``ui/loginError`` / ``ui/loginDismiss`` unchanged, and
  a conf.yaml write failure fails the sign-in instead of reporting a success
  the next launch could not reproduce (the key is never echoed back).
* ``BASE_URL``/``API_KEY`` in the environment (``--set-env`` or shell
  exports) are a complete sign-in: no TTY prompt, no selector and nothing
  persisted; only a pair missing one half still prompts.

Everything runs against a temporary ``~/.siada-cli`` (never the real user
config) with the provider catalogue mocked, so no network or live model call
happens.
"""

import contextlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

import siada.config.conf_store as conf_store
from siada.entrypoint.login import login_prompt

KEY_PAYLOAD = {
    "provider_id": "kimi",
    "api_key": "sk-test-abcdef",
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.5",
}

# Explicit per-invocation credentials (``--set-env BASE_URL=... --set-env
# API_KEY=...`` or plain shell exports) that must sign in without prompting.
ENV_BASE_URL = "http://127.0.0.1:9/v1"
ENV_API_KEY = "sk-test-no-network"


@contextlib.contextmanager
def _forbid_private_imports():
    """Fail if anything under ``siada.internal`` is imported while active."""

    attempted = []

    class _Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "siada.internal" or fullname.startswith("siada.internal."):
                attempted.append(fullname)
                raise AssertionError(f"unexpected private import: {fullname}")
            return None

    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        yield attempted
    finally:
        sys.meta_path.remove(finder)


class _FakeTransport:
    """Collects the ACP notifications the sign-in flow sends to the frontend."""

    def __init__(self):
        self.is_connected = True
        self.messages = []

    def send_sync(self, message):
        self.messages.append(message)


class _FakeIO:
    def __init__(self, connected=True):
        self.infos = []
        self.errors = []
        self.warnings = []
        self.acp_adapter = MagicMock()
        self.acp_adapter.transport = _FakeTransport() if connected else None

    def print_info(self, message):
        self.infos.append(message)

    def print_error(self, message):
        self.errors.append(message)

    def print_warning(self, message):
        self.warnings.append(message)

    def methods(self):
        return [message.method for message in self.acp_adapter.transport.messages]

    def params(self, method):
        for message in self.acp_adapter.transport.messages:
            if message.method == method:
                return message.params
        return None


class _RecordingModel:
    """Stands in for the running model in ``siadahub._apply_login()`` tests."""

    def __init__(self, model_name="args-selected-model", provider="openrouter"):
        self.provider = provider
        self.model_name = model_name
        self.configured = []

    def configure_model_settings(self, model_name):
        self.configured.append(model_name)
        self.model_name = model_name


@pytest.fixture(autouse=True)
def temp_user_home(tmp_path, monkeypatch):
    """Point ``~/.siada-cli`` at a temp dir and mock the provider catalogue."""
    monkeypatch.setattr(conf_store, "SIADA_HOME", Path(tmp_path))
    monkeypatch.setattr("siada.config.model_config.SIADA_HOME", Path(tmp_path))
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    monkeypatch.setattr(
        "siada.provider.models_dev.get_providers_for_ui",
        lambda: [
            {
                "id": "kimi",
                "name": "Kimi (Moonshot AI)",
                "baseUrl": "https://api.moonshot.cn/v1",
                "apiKeyHint": "sk-...",
                "models": [{"id": "kimi-k2.5", "name": "Kimi K2.5", "context": 262}],
            }
        ],
    )
    return Path(tmp_path)


def _write_conf(home: Path, data: dict) -> None:
    (home / "conf.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _read_llm_config(home: Path) -> dict:
    return conf_store.get_conf_section("llm_config")


def _new_prompt_choice(monkeypatch, raw):
    """Make the ACP stdin reader return one ``__LOGIN_CHOICE__`` message."""
    monkeypatch.setattr(login_prompt, "_read_acp_stdin_message", lambda: raw)


def _key_choice(payload) -> str:
    return "__LOGIN_CHOICE__:3:" + json.dumps(payload)


def _fail_if_called(*args, **kwargs):
    """Assertion helper for paths that must never prompt or reach the network."""
    raise AssertionError("no prompt/selector is allowed for these credentials")


def _set_env_credentials(monkeypatch, base_url=ENV_BASE_URL, api_key=ENV_API_KEY):
    """Export a (possibly partial) credential pair, like ``--set-env`` does."""
    if base_url is not None:
        monkeypatch.setenv("BASE_URL", base_url)
    if api_key is not None:
        monkeypatch.setenv("API_KEY", api_key)


# --------------------------------------------------------------------------- #
# First-run sign-in (ACP mode)
# --------------------------------------------------------------------------- #
def test_first_run_shows_api_key_only_selector(monkeypatch, temp_user_home):
    """The first sign-in offers the API key wizard and nothing else."""
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    with _forbid_private_imports() as attempted:
        user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert attempted == []
    selector = io.params("ui/showLoginSelector")
    assert selector is not None
    assert selector["liidDisabled"] is True
    assert not selector.get("cancelable"), "first-run sign-in cannot be cancelled"
    assert selector["providers"][0]["id"] == "kimi"
    assert io.methods()[0] == "ui/showLoginSelector"
    assert io.params("ui/loginError") is not None


def test_first_run_api_key_choice_configures_provider(monkeypatch, temp_user_home):
    """``__LOGIN_CHOICE__:3`` persists the provider config and reports success."""
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, _key_choice(KEY_PAYLOAD))

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user == "api-key-user:kimi"
    assert io.params("ui/loginSuccess") == {
        "userId": "api-key-user:kimi",
        "displayName": "API Key (kimi)",
    }
    methods = io.methods()
    assert methods.index("ui/showLoginSelector") < methods.index("ui/loginSuccess")
    stored = _read_llm_config(temp_user_home)
    assert stored["provider"] == "default"
    assert stored["provider_id"] == "kimi"
    assert stored["api_key"] == KEY_PAYLOAD["api_key"]
    assert stored["base_url"] == KEY_PAYLOAD["base_url"]
    assert stored["model"] == KEY_PAYLOAD["model"]
    assert os.environ["BASE_URL"] == KEY_PAYLOAD["base_url"]
    assert os.environ["API_KEY"] == KEY_PAYLOAD["api_key"]
    assert login_prompt.get_applied_api_key_config() == KEY_PAYLOAD


def test_first_run_empty_api_key_is_rejected(monkeypatch, temp_user_home):
    io = _FakeIO()
    _new_prompt_choice(
        monkeypatch, _key_choice({"provider_id": "kimi", "api_key": "   "})
    )

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/loginError") == {"error": "API key cannot be empty."}
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None


def test_first_run_malformed_choice_payload_is_reported(monkeypatch, temp_user_home):
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:3:not-json")

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/loginError") == {"error": "Invalid API key configuration."}
    assert _read_llm_config(temp_user_home) == {}


def test_first_run_api_key_choice_requires_a_base_url(monkeypatch, temp_user_home):
    """A payload without an endpoint is not a sign-in."""
    io = _FakeIO()
    _new_prompt_choice(
        monkeypatch,
        _key_choice({"provider_id": "kimi", "api_key": "sk-test-abcdef"}),
    )

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/loginError") == {"error": "Base URL cannot be empty."}
    assert "ui/loginSuccess" not in io.methods()
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None
    assert os.environ.get("BASE_URL") is None
    assert os.environ.get("API_KEY") is None


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_id": "kimi", "api_key": {"value": "sk-x"}, "base_url": "https://x/v1"},
        {"provider_id": ["kimi"], "api_key": "sk-x", "base_url": "https://x/v1"},
        {"provider_id": "kimi", "api_key": "sk-x", "base_url": 123},
        {"provider_id": "kimi", "api_key": "sk-x", "base_url": "https://x/v1", "model": 7},
    ],
    ids=["api-key-object", "provider-id-array", "base-url-number", "model-number"],
)
def test_first_run_wrong_payload_field_types_are_reported(
    monkeypatch, temp_user_home, payload
):
    """Wrong JSON types surface as a loginError — no AttributeError, no success."""
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, _key_choice(payload))

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/loginError") == {"error": "Invalid API key configuration."}
    assert "ui/loginSuccess" not in io.methods()
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None
    assert os.environ.get("BASE_URL") is None
    assert os.environ.get("API_KEY") is None


def test_reconfigure_wrong_payload_field_type_is_reported(monkeypatch, temp_user_home):
    """The /configure re-run must report the bad type instead of raising."""
    io = _FakeIO()
    _new_prompt_choice(
        monkeypatch,
        _key_choice({"provider_id": "kimi", "api_key": 42, "base_url": "https://x/v1"}),
    )

    assert login_prompt.reconfigure_acp(io) is None
    assert io.params("ui/loginError") == {"error": "Invalid API key configuration."}
    assert "ui/loginSuccess" not in io.methods()
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None


def test_first_run_failed_conf_write_is_not_a_sign_in(monkeypatch, temp_user_home):
    """A conf.yaml write failure must fail the wizard, never fake a sign-in."""
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, _key_choice(KEY_PAYLOAD))
    monkeypatch.setattr(conf_store, "update_conf", lambda mutator: False)

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert "ui/loginSuccess" not in io.methods()
    error = io.params("ui/loginError")
    assert error is not None and "conf.yaml" in error["error"]
    assert KEY_PAYLOAD["api_key"] not in json.dumps(error)
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None
    # Nothing was persisted, so the process credentials stay untouched too.
    assert os.environ.get("BASE_URL") is None
    assert os.environ.get("API_KEY") is None


def test_failed_conf_write_keeps_the_previous_configuration(
    monkeypatch, temp_user_home
):
    """A failed wizard write leaves the pre-existing conf.yaml content intact."""
    _write_conf(
        temp_user_home, {"theme": "dark", "llm_config": {"model": "gpt-4o-mini"}}
    )
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, _key_choice(KEY_PAYLOAD))
    monkeypatch.setattr(conf_store, "update_conf", lambda mutator: False)

    assert login_prompt.ensure_logged_in(io, acp_mode=True) is None

    stored = conf_store.read_conf_dict()
    assert stored["theme"] == "dark"
    assert stored["llm_config"] == {"model": "gpt-4o-mini"}


def test_save_provider_config_reports_write_failure(monkeypatch, temp_user_home):
    monkeypatch.setattr(conf_store, "update_conf", lambda mutator: False)

    assert login_prompt._save_provider_config("kimi", "sk-x", "https://x/v1", "m") is False
    assert _read_llm_config(temp_user_home) == {}


def test_save_provider_config_reports_success(temp_user_home):
    assert login_prompt._save_provider_config("kimi", "sk-x", "https://x/v1", "m") is True
    stored = _read_llm_config(temp_user_home)
    assert stored["provider"] == "default"
    assert stored["provider_id"] == "kimi"
    assert stored["api_key"] == "sk-x"
    assert stored["model"] == "m"


def test_first_run_without_transport_returns_none(monkeypatch, temp_user_home):
    """No UI transport means no way to sign in; callers must not hang."""
    io = _FakeIO(connected=False)
    _new_prompt_choice(monkeypatch, _key_choice(KEY_PAYLOAD))

    assert login_prompt.ensure_logged_in(io, acp_mode=True) is None


def test_stored_api_key_config_skips_the_selector(monkeypatch, temp_user_home):
    """A previously configured provider is used without prompting again."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-openai",
                "model": "gpt-5.2",
            }
        },
    )
    io = _FakeIO()

    def _fail_if_prompted():
        raise AssertionError("stored config must not prompt for a choice")

    monkeypatch.setattr(login_prompt, "_read_acp_stdin_message", _fail_if_prompted)

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user == "api-key-configured"
    assert io.acp_adapter.transport.messages == []
    assert os.environ["API_KEY"] == "sk-openai"
    assert login_prompt.get_applied_api_key_config()["provider_id"] == "openai"


# --------------------------------------------------------------------------- #
# /configure re-run (ACP mode)
# --------------------------------------------------------------------------- #
def test_reconfigure_selector_is_cancelable_and_api_key_only(
    monkeypatch, temp_user_home
):
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:cancel")

    result = login_prompt.reconfigure_acp(io)

    assert result is None
    selector = io.params("ui/showLoginSelector")
    assert selector["cancelable"] is True
    assert selector["liidDisabled"] is True
    assert "ui/loginDismiss" in io.methods()
    assert _read_llm_config(temp_user_home) == {}


def test_reconfigure_cancel_keeps_existing_configuration(monkeypatch, temp_user_home):
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-old",
                "model": "gpt-4o",
            }
        },
    )
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    assert login_prompt.reconfigure_acp(io) is None

    stored = _read_llm_config(temp_user_home)
    assert stored["provider_id"] == "openai"
    assert stored["api_key"] == "sk-old"
    assert login_prompt.get_applied_api_key_config() is None


def test_reconfigure_success_applies_new_api_key(monkeypatch, temp_user_home):
    io = _FakeIO()
    payload = {
        "provider_id": "openai",
        "api_key": "sk-new-key",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.2",
    }
    _new_prompt_choice(monkeypatch, _key_choice(payload))

    result = login_prompt.reconfigure_acp(io)

    assert result == "api-key-user:openai"
    assert io.params("ui/loginSuccess") == {
        "userId": "api-key-user:openai",
        "displayName": "API Key (openai)",
    }
    assert "ui/loginDismiss" not in io.methods()
    stored = _read_llm_config(temp_user_home)
    assert stored["api_key"] == "sk-new-key"
    assert stored["model"] == "gpt-5.2"
    assert login_prompt.get_applied_api_key_config()["api_key"] == "sk-new-key"


def test_reconfigure_without_key_payload_dismisses(monkeypatch, temp_user_home):
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:3")

    assert login_prompt.reconfigure_acp(io) is None
    assert "ui/loginDismiss" in io.methods()
    assert _read_llm_config(temp_user_home) == {}


def test_reconfigure_unsupported_choice_reports_error(monkeypatch, temp_user_home):
    """Hosted sign-in options are not offered; they must not be attempted."""
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:1")

    with _forbid_private_imports() as attempted:
        result = login_prompt.reconfigure_acp(io)

    assert result is None
    assert attempted == []
    assert io.params("ui/loginError") is not None
    assert "ui/loginDeviceUrl" not in io.methods()
    assert _read_llm_config(temp_user_home) == {}


def test_reconfigure_without_transport_is_a_noop(temp_user_home):
    io = _FakeIO(connected=False)

    assert login_prompt.reconfigure_acp(io) is None


# --------------------------------------------------------------------------- #
# TTY mode
# --------------------------------------------------------------------------- #
def test_tty_login_prompts_for_endpoint_and_key(monkeypatch, temp_user_home):
    io = _FakeIO()
    answers = iter(["https://api.openai.com/v1", "gpt-5.2"])
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "sk-tty-key")

    user = login_prompt.ensure_logged_in(io, acp_mode=False)

    assert user == "api-key-user:configured"
    stored = _read_llm_config(temp_user_home)
    assert stored["provider"] == "default"
    assert stored["api_key"] == "sk-tty-key"
    assert stored["base_url"] == "https://api.openai.com/v1"
    assert stored["model"] == "gpt-5.2"
    assert os.environ["API_KEY"] == "sk-tty-key"


def test_tty_login_requires_an_interactive_terminal(monkeypatch, temp_user_home):
    io = _FakeIO()
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert io.infos == []
    assert _read_llm_config(temp_user_home) == {}


def test_tty_login_rejects_empty_api_key(monkeypatch, temp_user_home):
    io = _FakeIO()
    answers = iter(["https://api.openai.com/v1", ""])
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "  ")

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert io.errors == ["API key cannot be empty."]
    assert _read_llm_config(temp_user_home) == {}


def test_tty_login_rejects_empty_base_url(monkeypatch, temp_user_home):
    """A blank endpoint is not usable: reject it before persisting anything."""
    io = _FakeIO()
    answers = iter(["   ", "gpt-5.2"])
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "sk-tty-key")

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert io.errors == ["Base URL cannot be empty."]
    assert _read_llm_config(temp_user_home) == {}
    assert os.environ.get("API_KEY") is None
    assert login_prompt.get_applied_api_key_config() is None


def test_tty_login_failed_conf_write_is_not_a_sign_in(monkeypatch, temp_user_home):
    """The TTY wizard must fail (without echoing the key) when saving fails."""
    io = _FakeIO()
    answers = iter(["https://api.openai.com/v1", "gpt-5.2"])
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "sk-tty-key")
    monkeypatch.setattr(conf_store, "update_conf", lambda mutator: False)

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert io.errors and "conf.yaml" in io.errors[0]
    assert "sk-tty-key" not in io.errors[0]
    assert _read_llm_config(temp_user_home) == {}
    assert login_prompt.get_applied_api_key_config() is None
    assert os.environ.get("BASE_URL") is None
    assert os.environ.get("API_KEY") is None


# --------------------------------------------------------------------------- #
# Explicit environment credentials (--set-env / shell exports / --prompt runs)
# --------------------------------------------------------------------------- #
def test_env_credentials_sign_in_without_any_prompt(monkeypatch, temp_user_home):
    """BASE_URL + API_KEY are a complete sign-in: no TTY, no ACP selector."""
    _set_env_credentials(monkeypatch)
    io = _FakeIO()

    monkeypatch.setattr(login_prompt, "_read_acp_stdin_message", _fail_if_called)
    monkeypatch.setattr("builtins.input", _fail_if_called)
    monkeypatch.setattr("getpass.getpass", _fail_if_called)
    monkeypatch.setattr(login_prompt, "_save_provider_config", _fail_if_called)
    # Skipping the selector also means the provider catalogue is never needed.
    monkeypatch.setattr(
        "siada.provider.models_dev.get_providers_for_ui", _fail_if_called
    )

    with _forbid_private_imports() as attempted:
        user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert attempted == []
    assert user == "api-key-user:configured"
    assert user.startswith("api-key-")
    assert ENV_API_KEY not in user
    assert io.acp_adapter.transport.messages == []  # no ui/showLoginSelector
    assert io.infos == [] and io.errors == []
    assert os.environ["BASE_URL"] == ENV_BASE_URL
    assert os.environ["API_KEY"] == ENV_API_KEY
    # Environment credentials are scoped to this process: nothing persists.
    assert _read_llm_config(temp_user_home) == {}
    applied = login_prompt.get_applied_api_key_config()
    assert applied["provider_id"] == "configured"
    assert applied["base_url"] == ENV_BASE_URL
    assert applied["api_key"] == ENV_API_KEY
    # No model travels with env credentials, so --model / conf.yaml keep theirs.
    assert applied["model"] == ""


def test_env_credentials_sign_in_for_noninteractive_prompt_runs(
    monkeypatch, temp_user_home
):
    """``--prompt`` runs have no TTY: env credentials still sign in, silently."""
    _set_env_credentials(monkeypatch)
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)
    monkeypatch.setattr("builtins.input", _fail_if_called)
    io = _FakeIO()

    user = login_prompt.ensure_logged_in(io, acp_mode=False)

    assert user == "api-key-user:configured"
    assert io.infos == []
    assert _read_llm_config(temp_user_home) == {}


@pytest.mark.parametrize(
    "base_url, api_key",
    [(ENV_BASE_URL, None), (None, ENV_API_KEY)],
    ids=["base-url-only", "api-key-only"],
)
def test_partial_env_credentials_do_not_skip_the_selector(
    monkeypatch, temp_user_home, base_url, api_key
):
    """Half a pair is not a sign-in: the login selector must still run."""
    _set_env_credentials(monkeypatch, base_url=base_url, api_key=api_key)
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/showLoginSelector") is not None
    assert login_prompt.get_applied_api_key_config() is None
    assert _read_llm_config(temp_user_home) == {}


def test_partial_env_credentials_fail_in_noninteractive_tty(
    monkeypatch, temp_user_home
):
    _set_env_credentials(monkeypatch, base_url=None)
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)
    monkeypatch.setattr("builtins.input", _fail_if_called)
    io = _FakeIO()

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert login_prompt.get_applied_api_key_config() is None


def test_env_credentials_override_the_stored_config(monkeypatch, temp_user_home):
    """--set-env wins over conf.yaml; the stored config is left untouched."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-stored",
                "model": "gpt-5.2",
            }
        },
    )
    _set_env_credentials(monkeypatch)
    io = _FakeIO()
    monkeypatch.setattr(login_prompt, "_read_acp_stdin_message", _fail_if_called)

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user == "api-key-user:configured"
    assert io.acp_adapter.transport.messages == []
    stored = _read_llm_config(temp_user_home)
    assert stored["provider_id"] == "openai"
    assert stored["base_url"] == "https://api.openai.com/v1"
    assert stored["api_key"] == "sk-stored"
    assert os.environ["BASE_URL"] == ENV_BASE_URL
    assert os.environ["API_KEY"] == ENV_API_KEY
    applied = login_prompt.get_applied_api_key_config()
    assert applied["base_url"] == ENV_BASE_URL
    # The stored model must not override the one --model / conf.yaml resolved.
    assert applied["model"] == ""


def test_env_endpoint_completes_a_stored_api_key(monkeypatch, temp_user_home):
    """conf.yaml fills the half the environment leaves empty, without a prompt."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "kimi",
                "api_key": "sk-stored",
            }
        },
    )
    _set_env_credentials(monkeypatch, api_key=None)
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)
    io = _FakeIO()

    user = login_prompt.ensure_logged_in(io, acp_mode=False)

    assert user == "api-key-user:configured"
    assert os.environ["BASE_URL"] == ENV_BASE_URL
    assert os.environ["API_KEY"] == "sk-stored"
    assert _read_llm_config(temp_user_home)["api_key"] == "sk-stored"


def test_stored_api_key_without_base_url_does_not_fast_path(
    monkeypatch, temp_user_home
):
    """A stored api_key alone is not a credential: no fake sign-in, prompt runs."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "api_key": "sk-stored",
                "model": "gpt-5.2",
            }
        },
    )
    # get_config() pre-loads a stored api_key into the environment; the missing
    # endpoint still makes the pair partial.
    monkeypatch.setenv("API_KEY", "sk-stored")
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/showLoginSelector") is not None
    assert login_prompt.get_applied_api_key_config() is None


def test_failed_login_does_not_reuse_stale_applied_config(
    monkeypatch, temp_user_home
):
    """A config applied by an earlier sign-in must not outlive a failed login."""
    stale = {
        "provider_id": "openai",
        "base_url": "https://stale.example/v1",
        "api_key": "sk-stale",
        "model": "stale-model",
    }
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", dict(stale))
    monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)
    io = _FakeIO()

    assert login_prompt.ensure_logged_in(io, acp_mode=False) is None
    assert login_prompt.get_applied_api_key_config() is None


def test_env_credentials_are_never_logged(monkeypatch, temp_user_home):
    """Only the synthetic identity may reach the logs, never key nor endpoint."""
    _set_env_credentials(monkeypatch)
    logger_mock = MagicMock()
    monkeypatch.setattr(login_prompt, "logger", logger_mock)

    user = login_prompt.ensure_logged_in(_FakeIO(), acp_mode=False)

    assert user == "api-key-user:configured"
    rendered = repr(logger_mock.mock_calls)
    assert ENV_API_KEY not in rendered
    assert ENV_BASE_URL not in rendered
    assert "api-key-user:configured" in rendered


# --------------------------------------------------------------------------- #
# Stored conf.yaml fields are validated before they authenticate anything
# (release blocker: a raw numeric/list field used to raise AttributeError, or
# reach ``_apply_login`` and blow up there on ``.strip()``).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "llm_config",
    [
        {"provider": "default", "provider_id": "openai", "base_url": 42,
         "api_key": "sk-stored", "model": "gpt-5.2"},
        {"provider": "default", "provider_id": "openai",
         "base_url": ["https://api.openai.com/v1"], "api_key": "sk-stored",
         "model": "gpt-5.2"},
        {"provider": "default", "provider_id": "openai",
         "base_url": "https://api.openai.com/v1", "api_key": 12345,
         "model": "gpt-5.2"},
        {"provider": "default", "provider_id": "openai",
         "base_url": "https://api.openai.com/v1", "api_key": {"key": "sk-stored"},
         "model": "gpt-5.2"},
    ],
    ids=["base-url-number", "base-url-array", "api-key-number", "api-key-object"],
)
def test_wrongly_typed_stored_credentials_do_not_crash_and_prompt(
    monkeypatch, temp_user_home, llm_config
):
    """A bad stored half reads as missing: selector runs, no fake sign-in."""
    _write_conf(temp_user_home, {"llm_config": llm_config})
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/showLoginSelector") is not None
    assert "ui/loginSuccess" not in io.methods()
    assert login_prompt.get_applied_api_key_config() is None


def test_wrongly_typed_stored_config_can_be_reconfigured(monkeypatch, temp_user_home):
    """The corrupt stored section must not block a fresh, valid sign-in."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": ["openai"],
                "base_url": [1],
                "api_key": 42,
                "model": 7,
            }
        },
    )
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, _key_choice(KEY_PAYLOAD))

    assert login_prompt.reconfigure_acp(io) == "api-key-user:kimi"

    stored = _read_llm_config(temp_user_home)
    assert stored["base_url"] == KEY_PAYLOAD["base_url"]
    assert stored["api_key"] == KEY_PAYLOAD["api_key"]
    assert login_prompt.get_applied_api_key_config() == KEY_PAYLOAD


def test_wrongly_typed_stored_model_and_provider_id_do_not_crash(
    monkeypatch, temp_user_home
):
    """Valid credentials plus a numeric model / list provider_id still sign in,
    and the sanitized config survives ``_apply_login`` without ``.strip()``."""
    import siada.entrypoint.siadahub as siadahub
    from siada.models import model_base_config

    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": ["openai"],
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-stored",
                "model": 7,
            }
        },
    )
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    monkeypatch.setattr(siadahub, "get_api_key_provider_models", lambda *a, **k: [])
    io = _FakeIO()

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user == "api-key-configured"
    applied = login_prompt.get_applied_api_key_config()
    assert applied["provider_id"] == "configured"
    assert applied["model"] == ""
    assert os.environ["API_KEY"] == "sk-stored"

    model = _RecordingModel(model_name="kept-model")
    assert siadahub._apply_login(
        io, SimpleNamespace(acp=False), model, controller=None
    ) is None
    assert model.provider == "default"
    assert model.model_name == "kept-model"
    assert model.configured == []


def test_env_pair_signs_in_next_to_corrupt_stored_config(monkeypatch, temp_user_home):
    """A complete environment pair is authoritative even when conf.yaml is junk."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": {"id": "openai"},
                "base_url": 42,
                "api_key": ["sk-stored"],
                "model": 7,
            }
        },
    )
    _set_env_credentials(monkeypatch)
    io = _FakeIO()

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user == "api-key-user:configured"
    applied = login_prompt.get_applied_api_key_config()
    assert applied["base_url"] == ENV_BASE_URL
    assert applied["api_key"] == ENV_API_KEY
    assert applied["model"] == ""
    assert io.acp_adapter.transport.messages == []  # no selector, no prompt
    # Environment credentials stay in-process: the corrupt stored data is intact.
    stored = _read_llm_config(temp_user_home)
    assert stored["base_url"] == 42


def test_env_half_with_corrupt_stored_half_still_prompts(
    monkeypatch, temp_user_home
):
    """A stored field of the wrong type cannot complete the env pair."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": 12345,
            }
        },
    )
    _set_env_credentials(monkeypatch, api_key=None)  # BASE_URL only
    io = _FakeIO()
    _new_prompt_choice(monkeypatch, "__LOGIN_CHOICE__:skip")

    user = login_prompt.ensure_logged_in(io, acp_mode=True)

    assert user is None
    assert io.params("ui/showLoginSelector") is not None
    assert login_prompt.get_applied_api_key_config() is None


def test_stored_credentials_are_never_logged(monkeypatch, temp_user_home):
    """The stored api key / endpoint must not reach the logs either."""
    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-secret-stored",
                "model": "gpt-5.2",
            }
        },
    )
    logger_mock = MagicMock()
    monkeypatch.setattr(login_prompt, "logger", logger_mock)

    user = login_prompt.ensure_logged_in(_FakeIO(), acp_mode=True)

    assert user == "api-key-configured"
    rendered = repr(logger_mock.mock_calls)
    assert "sk-secret-stored" not in rendered
    assert "https://api.openai.com/v1" not in rendered


# --------------------------------------------------------------------------- #
# ACP stdin framing (EOF semantics)
# --------------------------------------------------------------------------- #
class _FakeStdin:
    """``sys.stdin`` stand-in: yields the given lines, then reports EOF."""

    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return ""


class _FakeMonitor:
    """``StdinInterruptMonitor`` stand-in: yields lines, then poll timeouts."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.timeouts = 0

    def readline(self, timeout=None):
        line = self._lines.pop(0) if self._lines else ""
        if not line:
            self.timeouts += 1
        return line

    def read_login_reply_line(self, timeout=None):
        # The login prompt reads configuration replies through the
        # monitor's dedicated login-reply queue (2f21d82e); for this
        # stand-in it behaves like the ordinary polled readline.
        return self.readline(timeout=timeout)


def test_inactive_monitor_stdin_eof_raises(monkeypatch):
    """Without the monitor, an empty read is EOF — never an infinite poll."""
    monkeypatch.setattr(
        "siada.io.stdin_interrupt_monitor.is_monitor_active", lambda: False
    )
    monkeypatch.setattr(sys, "stdin", _FakeStdin([]))

    with pytest.raises(EOFError):
        login_prompt._read_acp_stdin_message()


def test_partial_frame_eof_raises(monkeypatch):
    """EOF after START but before END must not spin inside the frame either."""
    monkeypatch.setattr(
        "siada.io.stdin_interrupt_monitor.is_monitor_active", lambda: False
    )
    monkeypatch.setattr(sys, "stdin", _FakeStdin(["<<<SIADA_MSG_START>>>\n"]))

    with pytest.raises(EOFError):
        login_prompt._read_acp_stdin_message()


def test_monitor_timeout_keeps_polling_until_the_message_arrives(monkeypatch):
    """Monitor poll timeouts are not EOF: keep reading until the frame is in."""
    monitor = _FakeMonitor(
        [
            "",  # outer poll timeout
            "<<<SIADA_MSG_START>>>\n",
            "",  # inner poll timeout mid-frame
            "__LOGIN_CHOICE__:skip\n",
            "<<<SIADA_MSG_END>>>\n",
        ]
    )
    monkeypatch.setattr(
        "siada.io.stdin_interrupt_monitor.is_monitor_active", lambda: True
    )
    monkeypatch.setattr(
        "siada.io.stdin_interrupt_monitor.get_stdin_monitor", lambda: monitor
    )

    assert login_prompt._read_acp_stdin_message() == "__LOGIN_CHOICE__:skip"
    assert monitor.timeouts == 2


def test_acp_login_reports_eof_instead_of_hanging(monkeypatch, temp_user_home):
    """An EOF from the frontend fails the selector with a loginError."""
    monkeypatch.setattr(
        login_prompt, "_read_acp_stdin_message",
        lambda: (_ for _ in ()).throw(EOFError("pipe closed")),
    )
    io = _FakeIO()

    assert login_prompt.ensure_logged_in(io, acp_mode=True) is None
    assert "ui/showLoginSelector" in io.methods()
    assert io.params("ui/loginError") is not None
    assert login_prompt.get_applied_api_key_config() is None


# --------------------------------------------------------------------------- #
# ``_apply_login`` consumes the applied config
# --------------------------------------------------------------------------- #
def test_apply_login_keeps_the_selected_model_with_env_credentials(
    monkeypatch, temp_user_home
):
    """``_apply_login`` switches to provider=default but keeps the model that
    ``--model`` / conf.yaml selected (env credentials carry no model)."""
    import siada.entrypoint.siadahub as siadahub

    _set_env_credentials(monkeypatch)
    calls = []

    def _record(provider_id, selected_model, base_url=""):
        calls.append((provider_id, selected_model, base_url))
        return []

    monkeypatch.setattr(siadahub, "get_api_key_provider_models", _record)
    model = _RecordingModel(model_name="args-selected-model", provider="openrouter")
    io = _FakeIO()

    result = siadahub._apply_login(
        io, SimpleNamespace(acp=False), model, controller=None
    )

    assert result is None
    assert model.provider == "default"
    assert model.model_name == "args-selected-model"
    assert model.configured == []
    assert calls == [("configured", "", ENV_BASE_URL)]


def test_apply_login_explicit_model_wins_over_the_stored_model(
    monkeypatch, temp_user_home
):
    """``--model`` beats the model stored with the API-key config, and a custom
    name keeps a locally built settings entry (no extra provider lookup)."""
    import siada.entrypoint.siadahub as siadahub
    from siada.models import model_base_config

    _write_conf(
        temp_user_home,
        {
            "llm_config": {
                "provider": "default",
                "provider_id": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-stored",
                "model": "stored-model",
            }
        },
    )
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    calls = []

    def _record(provider_id, selected_model, base_url=""):
        calls.append((provider_id, selected_model, base_url))
        return [
            model_base_config.ModelBaseConfig(
                model_name="stored-model",
                context_window=128_000,
                max_tokens=8192,
                parallel_tool_calls=True,
            )
        ]

    monkeypatch.setattr(siadahub, "get_api_key_provider_models", _record)
    model = _RecordingModel(model_name="args-selected-model", provider="openrouter")
    io = _FakeIO()

    result = siadahub._apply_login(
        io, SimpleNamespace(acp=False, model="my-custom-model"), model, controller=None
    )

    assert result is None
    assert model.provider == "default"
    assert model.model_name == "my-custom-model"
    assert model.configured == ["my-custom-model"]
    # One provider lookup only, primed with the model actually selected.
    assert calls == [("openai", "my-custom-model", "https://api.openai.com/v1")]
    settings = model_base_config._user_model_settings
    assert [entry.model_name for entry in settings] == ["stored-model", "my-custom-model"]


# --------------------------------------------------------------------------- #
# /logout helper
# --------------------------------------------------------------------------- #
def test_clear_api_key_config_removes_stored_provider(temp_user_home):
    _write_conf(
        temp_user_home,
        {
            "theme": "dark",
            "llm_config": {"provider": "default", "base_url": "https://x/v1", "api_key": "k"},
        },
    )

    assert login_prompt.clear_api_key_config() is True

    stored = conf_store.read_conf_dict()
    assert stored.get("theme") == "dark"
    assert stored.get("llm_config", {}).get("provider") is None
    assert stored.get("llm_config", {}).get("api_key") is None


def test_clear_api_key_config_is_false_without_stored_provider(temp_user_home):
    assert login_prompt.clear_api_key_config() is False
    _write_conf(temp_user_home, {"llm_config": {"model": "gpt-5.2"}})
    assert login_prompt.clear_api_key_config() is False