"""Public-build startup guarantees for the ``siadahub`` entry point.

The open-source CLI signs in with the user's own model provider: a provider API
key stored as ``llm_config`` (``provider: default``) in
``~/.siada-cli/conf.yaml``. These tests pin that boundary on the entry point:

  * nothing on the public startup path may need the private ``siada.internal``
    package — a blocked import must degrade, never surface as a traceback;
  * the headroom proxy integration is gone from the CLI parser and from the
    startup sequence (no flag, no env injection, no network probing);
  * missing or legacy (LiId / domain-account) credentials fail with actionable
    guidance instead of a traceback.

They never touch the real ``~/.siada-cli`` state, never call a model and never
open a socket: every test runs against a temporary SIADA home, and the private
package is blocked by a meta-path finder that records import attempts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

import siada.entrypoint.siadahub as siadahub
from siada.config import conf_store, model_config
from siada.entrypoint.args_parser.args import SiadaArgs, get_parser
from siada.foundation import constants

# Root packages of the closed-source modules the public build must not require.
_PRIVATE_MODULE_ROOTS = ("siada.internal",)

# Flags that used to enable the (private) headroom proxy integration.
_REMOVED_HEADROOM_FLAGS = (
    ("--headroom",),
    ("--no-headroom",),
    ("--headroom-port", "8787"),
    ("--headroom-budget", "5"),
)


class _PrivateImportRecorder:
    """Meta-path finder that records *and* blocks private-module imports.

    Blocking (instead of relying on the package being absent) makes the tests
    independent of what happens to be installed next to the checkout.
    """

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102 - importlib protocol
        if any(
            fullname == root or fullname.startswith(root + ".")
            for root in _PRIVATE_MODULE_ROOTS
        ):
            self.attempts.append(fullname)
            raise ModuleNotFoundError(
                f"No module named {fullname!r} (blocked by test_public_startup)"
            )
        return None


class _RecordingIO:
    """Minimal InputOutput stand-in that keeps every message."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def print_info(self, message) -> None:
        self.infos.append(str(message))

    def print_error(self, message) -> None:
        self.errors.append(str(message))

    def print_warning(self, message) -> None:
        self.warnings.append(str(message))


class _FakeModel:
    """Minimal stand-in for ModelRunConfig that records what login applies."""

    def __init__(self) -> None:
        self.provider = "openrouter"
        self.model_name = "initial-model"
        self.configured: list[str] = []

    def configure_model_settings(self, model_name: str) -> None:
        self.configured.append(model_name)
        self.model_name = model_name


@pytest.fixture
def private_import_recorder(monkeypatch):
    """Block ``siada.internal`` and record every import attempt against it."""
    recorder = _PrivateImportRecorder()
    monkeypatch.setattr(sys, "meta_path", [recorder, *sys.meta_path])
    return recorder


@pytest.fixture
def siada_home(tmp_path, monkeypatch):
    """Redirect every conf/models path to a throwaway SIADA home."""
    home = tmp_path / ".siada-cli"
    home.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(constants, "SIADA_HOME", home)
    monkeypatch.setattr(conf_store, "SIADA_HOME", home)
    monkeypatch.setattr(model_config, "SIADA_HOME", home)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    return home


def _public_parser():
    """Build the real CLI parser exactly as the entry point does."""
    return get_parser(git_root=None, default_config_files=[])


def _args(argv):
    return SiadaArgs(_public_parser().parse_args(argv))


def _write_conf(home: Path, data: dict) -> None:
    (home / "conf.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _api_key_conf(
    model: str = "gpt-4o-mini",
    api_key: str = "sk-test-key",
    base_url: str = "https://api.example.com/v1",
) -> dict:
    return {
        "llm_config": {
            "provider": "default",
            "provider_id": "openai",
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }
    }


class TestPublicParser:
    """The CLI parser must not expose private-integration flags."""

    def test_headroom_flags_are_rejected(self, capsys):
        parser = _public_parser()
        for argv in _REMOVED_HEADROOM_FLAGS:
            with pytest.raises(SystemExit) as excinfo:
                parser.parse_args(list(argv))
            assert excinfo.value.code == 2
        # parser error output goes to stderr; captured so it stays out of the log
        assert "unrecognized arguments" in capsys.readouterr().err

    def test_typed_args_have_no_headroom_attributes(self):
        args = _args([])
        for name in ("headroom", "no_headroom", "headroom_port", "headroom_budget"):
            assert not hasattr(args, name)

    def test_help_has_no_headroom_section(self):
        assert "headroom" not in _public_parser().format_help().lower()

    def test_authentication_options_document_api_keys(self):
        help_text = _public_parser().format_help()
        assert "--logout" in help_text
        # --user-id / --access-token are kept as explainable no-ops
        assert "not supported" in help_text.lower()
        assert "api key" in help_text.lower()


@pytest.mark.parametrize(
    "setting",
    [
        "sk-test-invalid-assignment",
        "=sk-test-invalid-assignment",
        "API_KEY\0=sk-test-invalid-assignment",
    ],
)
def test_backend_env_validation_does_not_partially_apply_or_report_values(
    monkeypatch, setting
):
    monkeypatch.setenv("API_KEY", "sk-test-existing")
    io = _RecordingIO()
    args = SimpleNamespace(set_env=["API_KEY=sk-test-new", setting])

    assert siadahub.set_env(args, io) == 1
    assert os.environ["API_KEY"] == "sk-test-existing"
    assert io.errors == ["Invalid --set-env format. Use ENV_VAR_NAME=value."]
    assert "sk-test-" not in "".join(io.errors + io.infos)


class TestStartupSourceBoundary:
    """The startup module itself must not reach into private integrations."""

    def test_siadahub_source_has_no_private_or_headroom_hooks(self):
        source = Path(siadahub.__file__).read_text(encoding="utf-8")
        assert "siada.internal" not in source
        assert "headroom" not in source


class TestStoredCredentials:
    """Only public API-key metadata counts as a credential."""

    def test_empty_conf_has_no_credentials(self, siada_home):
        assert siadahub._has_stored_credentials() is False

    def test_legacy_liid_keys_are_not_credentials(self, siada_home):
        _write_conf(siada_home, {"user_id": "alice", "access_token": "legacy-token"})
        assert siadahub._has_stored_credentials() is False

    def test_api_key_config_is_a_credential(self, siada_home):
        _write_conf(siada_home, _api_key_conf())
        assert siadahub._has_stored_credentials() is True

    def test_api_key_without_key_is_not_a_credential(self, siada_home):
        conf = _api_key_conf(api_key="")
        _write_conf(siada_home, conf)
        assert siadahub._has_stored_credentials() is False

    def test_api_key_without_base_url_is_not_a_credential(self, siada_home):
        """Half a pair cannot sign in, so it must not take the fast path."""
        conf = _api_key_conf()
        del conf["llm_config"]["base_url"]
        _write_conf(siada_home, conf)
        assert siadahub._has_stored_credentials() is False

    def test_blank_credential_halves_are_not_credentials(self, siada_home):
        _write_conf(siada_home, _api_key_conf(base_url="   ", api_key="  "))
        assert siadahub._has_stored_credentials() is False

    @pytest.mark.parametrize(
        "field, value",
        [
            ("base_url", None),
            ("base_url", 42),
            ("base_url", ["https://api.example.com/v1"]),
            ("api_key", 12345),
            ("api_key", {"key": "sk-test-key"}),
        ],
        ids=["base-url-null", "base-url-number", "base-url-array", "api-key-number", "api-key-object"],
    )
    def test_non_string_credential_fields_are_not_credentials(
        self, siada_home, field, value
    ):
        """Wrong types must read as "no credentials", never as a sign-in."""
        conf = _api_key_conf()
        conf["llm_config"][field] = value
        _write_conf(siada_home, conf)
        assert siadahub._has_stored_credentials() is False


class TestSpecialCommands:
    """One-shot auth commands must stay free of private imports."""

    def test_logout_clears_stored_api_key(self, siada_home, private_import_recorder):
        _write_conf(siada_home, _api_key_conf())
        io = _RecordingIO()

        exit_code = siadahub.handle_special_commands(
            _args(["--logout"]), conf=SimpleNamespace(), io=io
        )

        assert exit_code == 0
        assert private_import_recorder.attempts == []
        remaining = yaml.safe_load((siada_home / "conf.yaml").read_text(encoding="utf-8"))
        assert remaining == {"llm_config": {"model": "gpt-4o-mini"}}
        assert any("Signed out" in message for message in io.infos)

    def test_logout_without_stored_key_is_a_no_op(self, siada_home, private_import_recorder):
        io = _RecordingIO()

        exit_code = siadahub.handle_special_commands(
            _args(["--logout"]), conf=SimpleNamespace(), io=io
        )

        assert exit_code == 0
        assert private_import_recorder.attempts == []
        assert any("No stored provider API key" in message for message in io.infos)

    def test_legacy_credential_flags_fail_with_guidance(
        self, siada_home, private_import_recorder
    ):
        io = _RecordingIO()
        args = _args(["--user-id", "alice", "--access-token", "legacy-token"])

        exit_code = siadahub.handle_special_commands(args, conf=SimpleNamespace(), io=io)

        assert exit_code == 1
        assert private_import_recorder.attempts == []
        assert io.errors and "not supported" in io.errors[0]
        assert any("API key" in message for message in io.errors + io.infos)


class TestApiKeyLogin:
    """The API-key sign-in path applies provider/model config offline."""

    @staticmethod
    def _prepare(siada_home):
        _write_conf(siada_home, _api_key_conf())
        from siada.entrypoint.login import login_prompt

        return login_prompt

    def test_applies_provider_and_provider_models(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        from siada.models import model_base_config

        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        monkeypatch.setattr(model_base_config, "_user_model_settings", None)
        provider_models = [
            model_base_config.ModelBaseConfig(
                model_name="provider-model",
                context_window=128_000,
                max_tokens=8192,
                parallel_tool_calls=True,
            )
        ]
        calls: list[tuple] = []

        def _fake_provider_models(provider_id, selected_model, base_url=""):
            calls.append((provider_id, selected_model, base_url))
            return provider_models

        monkeypatch.setattr(siadahub, "get_api_key_provider_models", _fake_provider_models)
        model = _FakeModel()
        io = _RecordingIO()

        result = siadahub._apply_login(io, _args([]), model, controller=None)

        assert result is None
        assert calls == [("openai", "gpt-4o-mini", "https://api.example.com/v1")]
        assert model.provider == "default"
        assert model.configured == ["gpt-4o-mini"]
        assert model_base_config._user_model_settings is provider_models
        assert private_import_recorder.attempts == []

    def test_merges_into_existing_model_settings(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        from siada.models import model_base_config

        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        existing = [
            model_base_config.ModelBaseConfig(
                model_name="provider-model",
                context_window=32_000,
                max_tokens=4096,
                parallel_tool_calls=False,
            )
        ]
        monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
        monkeypatch.setattr(
            siadahub,
            "get_api_key_provider_models",
            lambda provider_id, selected_model, base_url="": [
                model_base_config.ModelBaseConfig(
                    model_name="provider-model",
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

        result = siadahub._apply_login(
            io=_RecordingIO(), args=_args([]), model=_FakeModel(), controller=None
        )

        assert result is None
        # The user's models.json entry is kept as-is (no replacement) ...
        assert model_base_config._user_model_settings is existing
        assert [entry.model_name for entry in existing] == [
            "provider-model",
            "brand-new-model",
        ]
        assert existing[0].context_window == 32_000
        assert private_import_recorder.attempts == []

    def test_user_only_model_survives_login(self, siada_home, monkeypatch):
        """models.json entries the provider catalogue does not know are kept."""
        from siada.models import model_base_config

        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        user_only = model_base_config.ModelBaseConfig(
            model_name="my-private-deploy",
            context_window=64_000,
            max_tokens=1024,
            default_thinking_tokens=777,
            input_price=9.9,
        )
        existing = [user_only]
        monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
        replace_calls = []
        monkeypatch.setattr(
            model_base_config,
            "set_user_model_settings",
            lambda models: replace_calls.append(models),
        )
        monkeypatch.setattr(
            siadahub,
            "get_api_key_provider_models",
            lambda provider_id, selected_model, base_url="": [
                model_base_config.ModelBaseConfig(
                    model_name="gpt-4o-mini",
                    context_window=128_000,
                    max_tokens=8192,
                    parallel_tool_calls=True,
                )
            ],
        )

        result = siadahub._apply_login(
            _RecordingIO(), _args([]), _FakeModel(), controller=None
        )

        assert result is None
        assert model_base_config._user_model_settings is existing
        assert [entry.model_name for entry in existing] == [
            "gpt-4o-mini",
            "my-private-deploy",
        ]
        assert existing[1].default_thinking_tokens == 777
        assert existing[1].input_price == 9.9
        assert existing[1].context_window == 64_000
        assert replace_calls == []

    def test_missing_credentials_fail_with_guidance(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        from siada.entrypoint.login import login_prompt

        monkeypatch.setattr(login_prompt, "_is_interactive_tty", lambda: False)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        io = _RecordingIO()

        result = siadahub._apply_login(io, _args([]), _FakeModel(), controller=None)

        assert result == 1
        assert private_import_recorder.attempts == []
        assert io.errors and "provider API key" in io.errors[0]
        assert any("API key" in message for message in io.infos)

    def test_explicit_model_wins_and_keeps_user_settings_authoritative(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        """``--model`` beats the stored model; a custom name gets a local entry
        and the user's models.json fields are never replaced."""
        from siada.models import model_base_config

        login_prompt = self._prepare(siada_home)  # stored model: gpt-4o-mini
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        existing = [
            model_base_config.ModelBaseConfig(
                model_name="provider-model",
                context_window=32_000,
                max_tokens=4096,
                parallel_tool_calls=False,
                default_thinking_tokens=1234,
            )
        ]
        monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
        calls: list[tuple] = []

        def _fake_provider_models(provider_id, selected_model, base_url=""):
            calls.append((provider_id, selected_model, base_url))
            return [
                model_base_config.ModelBaseConfig(
                    model_name="gpt-4o-mini",
                    context_window=128_000,
                    max_tokens=8192,
                    parallel_tool_calls=True,
                )
            ]

        monkeypatch.setattr(siadahub, "get_api_key_provider_models", _fake_provider_models)
        model = _FakeModel()

        result = siadahub._apply_login(
            _RecordingIO(), _args(["--model", "my-custom-model"]), model, controller=None
        )

        assert result is None
        # A single provider lookup, primed with the model actually selected.
        assert calls == [("openai", "my-custom-model", "https://api.example.com/v1")]
        assert model.provider == "default"
        assert model.configured == ["my-custom-model"]
        assert model.model_name == "my-custom-model"
        assert [entry.model_name for entry in existing] == [
            "gpt-4o-mini",
            "my-custom-model",
            "provider-model",
        ]
        # models.json stays authoritative: the user's fields are untouched.
        assert existing[2].context_window == 32_000
        assert existing[2].max_tokens == 4096
        assert existing[2].default_thinking_tokens == 1234
        assert model_base_config._user_model_settings is existing
        assert private_import_recorder.attempts == []

    def test_provider_lookup_failure_is_not_reported_as_success(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)

        def _explode(provider_id, selected_model, base_url=""):
            raise RuntimeError("provider catalogue unavailable")

        monkeypatch.setattr(siadahub, "get_api_key_provider_models", _explode)
        model = _FakeModel()
        io = _RecordingIO()

        result = siadahub._apply_login(io, _args([]), model, controller=None)

        assert result == 1
        assert model.provider == "default"
        assert io.errors and "Could not apply" in io.errors[0]
        assert io.infos
        assert private_import_recorder.attempts == []

    def test_model_configuration_failure_is_not_reported_as_success(
        self, siada_home, monkeypatch
    ):
        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
        monkeypatch.setattr(
            siadahub, "get_api_key_provider_models", lambda *a, **k: []
        )

        def _explode(model_name):
            raise ValueError("model settings unavailable")

        model = _FakeModel()
        monkeypatch.setattr(model, "configure_model_settings", _explode)
        io = _RecordingIO()

        result = siadahub._apply_login(io, _args([]), model, controller=None)

        assert result == 1
        assert io.errors and "Could not apply" in io.errors[0]

    def test_api_key_identity_without_applied_config_fails(
        self, siada_home, monkeypatch
    ):
        """An api-key identity with nothing to apply must not be a success."""
        login_prompt = self._prepare(siada_home)
        monkeypatch.setattr(login_prompt, "get_applied_api_key_config", lambda: None)
        model = _FakeModel()
        io = _RecordingIO()

        result = siadahub._apply_login(io, _args([]), model, controller=None)

        assert result == 1
        assert model.provider == "openrouter"  # untouched, session never starts
        assert io.errors and "provider configuration" in io.errors[0]
        assert io.infos


class TestLoginInitTimeout:
    """A login worker that never finishes must fail the first prompt.

    The ACP fast path defers the credential check to a background thread; a
    worker still stuck after the join timeout means the session was never
    authenticated, so ``_ensure_login_ready()`` must fail instead of signalling
    success.
    """

    class _StuckThread:
        """Stands in for a login worker blocked (e.g. on the login selector)."""

        def __init__(self) -> None:
            self.join_timeouts: list = []

        def is_alive(self) -> bool:
            return True

        def join(self, timeout=None) -> None:
            self.join_timeouts.append(timeout)  # bounded wait, still stuck

    def test_unfinished_login_fails_instead_of_signalling_success(self, monkeypatch):
        stuck = self._StuckThread()
        monkeypatch.setattr(siadahub, "_login_init_thread", stuck)
        monkeypatch.setattr(siadahub, "_login_init_result", None)

        assert siadahub._ensure_login_ready() == 1
        assert stuck.join_timeouts == [30]
        # The reference is kept so a later caller can still observe the worker.
        assert siadahub._login_init_thread is stuck

    def test_finished_login_still_reports_its_exit_code(self, monkeypatch):
        class _DoneThread:
            def is_alive(self) -> bool:
                return False

            def join(self, timeout=None) -> None:
                raise AssertionError("a finished thread must not be joined")

        monkeypatch.setattr(siadahub, "_login_init_thread", _DoneThread())
        monkeypatch.setattr(siadahub, "_login_init_result", 1)

        assert siadahub._ensure_login_ready() == 1
        assert siadahub._login_init_thread is None
        assert siadahub._login_init_result is None

    def test_no_login_thread_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(siadahub, "_login_init_thread", None)

        assert siadahub._ensure_login_ready() is None


class TestLoginInitWorkerFailClosed:
    """An exception inside the login worker must never read as success.

    ``_login_init_result`` uses None as "not done" and 0 as "signed in"; a
    worker that dies without publishing a result used to leave None behind,
    which the joiner interpreted as a successful sign-in.
    """

    def _run_worker(self, monkeypatch, outcome):
        monkeypatch.setattr(siadahub, "_login_init_thread", None)
        monkeypatch.setattr(siadahub, "_login_init_result", None)
        io = _RecordingIO()

        def _apply_login(*args, **kwargs):
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(siadahub, "_apply_login", _apply_login)
        siadahub._start_login_init_async(
            io, SimpleNamespace(acp=True), "model", "controller"
        )
        assert siadahub._login_init_thread is not None
        siadahub._login_init_thread.join(timeout=5)
        return io

    def test_unexpected_error_fails_closed(self, monkeypatch):
        io = self._run_worker(monkeypatch, RuntimeError("credential backend down"))

        assert siadahub._login_init_result == 1
        assert siadahub._ensure_login_ready() == 1
        assert io.errors and "login" in io.errors[0].lower()

    def test_system_exit_fails_closed(self, monkeypatch):
        """A prompt that gave up (SystemExit) is a failure, not a success."""
        self._run_worker(monkeypatch, SystemExit(1))

        assert siadahub._login_init_result == 1
        assert siadahub._ensure_login_ready() == 1

    def test_successful_login_reports_success(self, monkeypatch):
        io = self._run_worker(monkeypatch, None)

        assert siadahub._login_init_result == 0
        assert siadahub._ensure_login_ready() is None
        assert io.errors == []

    def test_failed_apply_login_result_is_kept(self, monkeypatch):
        self._run_worker(monkeypatch, 1)

        assert siadahub._login_init_result == 1
        assert siadahub._ensure_login_ready() == 1


class TestAcpModeUnification:
    """``--acp`` and ``SIADA_ACP_MODE`` must select the same behaviour.

    The hosted UI spawns the backend with ``SIADA_ACP_MODE=1`` and no CLI flag,
    so login/runtime decisions cannot read ``args.acp`` alone.
    """

    def test_flag_and_env_are_unified(self, monkeypatch):
        monkeypatch.delenv("SIADA_ACP_MODE", raising=False)
        assert siadahub.acp_enabled(SimpleNamespace(acp=True)) is True
        assert siadahub.acp_enabled(SimpleNamespace(acp=False)) is False
        assert siadahub.acp_enabled(None) is False

        for value in ("1", "true", "yes", "TRUE", "Yes"):
            monkeypatch.setenv("SIADA_ACP_MODE", value)
            assert siadahub.acp_enabled(SimpleNamespace(acp=False)) is True
            assert siadahub.acp_enabled(None) is True

        monkeypatch.setenv("SIADA_ACP_MODE", "0")
        assert siadahub.acp_enabled(SimpleNamespace(acp=True)) is True
        assert siadahub.acp_enabled(SimpleNamespace(acp=False)) is False

    def test_login_decision_uses_env_acp_mode(self, monkeypatch, siada_home):
        """Env-only ACP mode must show the UI selector, not the TTY prompt."""
        from siada.entrypoint.login import login_prompt

        captured = {}

        def _fake_ensure_logged_in(io, acp_mode=False):
            captured["acp_mode"] = acp_mode
            return None

        monkeypatch.setattr(
            login_prompt, "ensure_logged_in", _fake_ensure_logged_in
        )
        monkeypatch.setenv("SIADA_ACP_MODE", "1")

        result = siadahub._apply_login(
            _RecordingIO(), _args([]), _FakeModel(), controller=None
        )

        assert result == 1  # no credentials -> fail, but through the ACP path
        assert captured == {"acp_mode": True}

        monkeypatch.delenv("SIADA_ACP_MODE", raising=False)
        siadahub._apply_login(
            _RecordingIO(), _args([]), _FakeModel(), controller=None
        )
        assert captured == {"acp_mode": False}

    def test_env_only_acp_mode_runs_the_acp_controller(self, monkeypatch, siada_home):
        """Runtime dispatch must not reject the UI-spawned backend as legacy."""
        monkeypatch.setenv("SIADA_ACP_MODE", "1")
        args = _args([])
        io = _RecordingIO()
        created = {}

        class _FakeController:
            def __init__(self, config, slash_commands, session):
                created["config"] = config
                self.ui = SimpleNamespace(close=lambda: None)

            def show_announcements(self):
                pass

            def run(self):
                return 0

        monkeypatch.setattr(siadahub, "Controller", _FakeController)
        monkeypatch.setattr(siadahub, "_apply_login", lambda *a, **k: None)
        monkeypatch.setattr(siadahub, "_try_restore_session", lambda *a, **k: None)
        monkeypatch.setattr(siadahub, "_ensure_login_ready", lambda: None)
        monkeypatch.setattr(siadahub, "_ensure_agents_ready", lambda: None)
        running_config = SimpleNamespace(acp_mode=siadahub.acp_enabled(args))
        commands = SimpleNamespace()
        session = SimpleNamespace()

        assert running_config.acp_mode is True
        assert siadahub._run_interactive(
            args, session, running_config, commands, io, _FakeModel()
        ) == 0
        assert created["config"] is running_config
        assert io.errors == []

    def test_missing_acp_mode_still_rejects_legacy_ui(self, monkeypatch, siada_home):
        monkeypatch.delenv("SIADA_ACP_MODE", raising=False)
        args = _args([])
        io = _RecordingIO()

        result = siadahub._run_interactive(
            args,
            session=SimpleNamespace(),
            running_config=SimpleNamespace(acp_mode=False),
            commands=SimpleNamespace(),
            io=io,
            model=_FakeModel(),
        )

        assert result == 1
        assert io.errors and "no longer supported" in io.errors[0]


class TestStartupWiring:
    """``main()`` must build and run without private modules or headroom."""

    def test_main_reaches_run_phase_without_private_integrations(
        self, siada_home, monkeypatch, private_import_recorder
    ):
        for variable in ("SIADA_HEADROOM_ENABLED", "SIADA_USE_HEADROOM", "SIADA_LLM_BASE_URL"):
            monkeypatch.delenv(variable, raising=False)

        io = _RecordingIO()
        parser = _public_parser()
        args = SiadaArgs(parser.parse_args([]))
        # conf carries an enabled headroom section on purpose: such legacy keys
        # must stay inert instead of activating the (private) proxy.
        conf = SimpleNamespace(
            mcp_config=None,
            headroom_config=SimpleNamespace(enabled=True, host="127.0.0.1", port=8787),
        )
        ran: list = []

        monkeypatch.setattr(siadahub, "logger", MagicMock())
        monkeypatch.setattr(siadahub, "_preload_c_extensions_on_main_thread", lambda: None)
        monkeypatch.setattr(siadahub, "_start_litellm_init_async", lambda: None)
        monkeypatch.setattr(siadahub, "_start_agents_init_async", lambda: None)
        monkeypatch.setattr(siadahub, "_handle_pre_init_commands", lambda: None)
        monkeypatch.setattr(siadahub, "_prepare_startup", lambda: None)
        monkeypatch.setattr(
            siadahub,
            "_load_conf_and_args",
            lambda: (conf, args, None, None, parser, False),
        )
        monkeypatch.setattr(siadahub, "get_io", lambda _args: (io, None))
        monkeypatch.setattr(
            siadahub, "ensure_daemon_running", lambda _conf, verbose=False: None
        )
        monkeypatch.setattr(siadahub, "_check_resume_workspace_early", lambda *a, **k: None)
        monkeypatch.setattr(
            siadahub,
            "_setup_and_build_session",
            lambda *a, **k: (None, "session", "running-config", "commands", "model"),
        )
        monkeypatch.setattr(
            siadahub,
            "_run_noninteractive",
            lambda run_args, session, running_config, run_io, model: ran.append(run_args) or 0,
        )

        assert siadahub.main() == 0
        assert ran == [args]
        assert private_import_recorder.attempts == []
        assert "SIADA_HEADROOM_ENABLED" not in os.environ
        assert "SIADA_USE_HEADROOM" not in os.environ
        assert "SIADA_LLM_BASE_URL" not in os.environ