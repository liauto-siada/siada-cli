"""Public startup preserves explicit credentials and reports safe failures."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from siada.config import conf_store, config_loader
from siada.entrypoint import launch_ui_with_acp
from siada.entrypoint.env_assignments import parse_env_assignments
from siada.entrypoint.login import login_prompt


@pytest.mark.parametrize("field", ["model", "provider", "api_key", "base_url", "provider_id"])
@pytest.mark.parametrize("value", [42, ["private-test-value"], {"key": "private-test-value"}])
def test_invalid_llm_fields_are_ignored_without_logging_values(monkeypatch, field, value):
    warning = MagicMock()
    monkeypatch.setattr(config_loader.logger, "warning", warning)
    config = config_loader.LLMConfig.from_dict({field: value})
    assert getattr(config, field) is None
    warning.assert_called_once_with("Ignoring llm_config.%s: expected a string", field)


def test_yaml_alias_error_does_not_expose_credentials(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("api_key: *private-test-value\n")
    errors = []
    assert conf_store.read_conf_dict(path, on_error=errors.append) == {}
    assert "line 1, column" in errors[0]
    assert "private-test-value" not in errors[0]
    assert path.read_text() == "api_key: *private-test-value\n"


def test_environment_credentials_skip_login_without_reading_user_state(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("API_KEY", "synthetic-env-key")
    monkeypatch.setattr(login_prompt, "_check_stored_api_key_config", lambda: pytest.fail("read stored credentials"))
    assert login_prompt.ensure_logged_in(MagicMock(), acp_mode=True) == "api-key-environment"


def test_stored_login_preserves_each_explicit_environment_field(monkeypatch):
    monkeypatch.setattr(conf_store, "get_conf_section", lambda name: {
        "provider": "default", "base_url": "https://stored.invalid/v1",
        "api_key": "synthetic-stored-key",
    })
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    monkeypatch.setenv("BASE_URL", "https://explicit.invalid/v1")
    monkeypatch.delenv("API_KEY", raising=False)
    assert login_prompt._check_stored_api_key_config() == "api-key-user:configured"
    assert os.environ["BASE_URL"] == "https://explicit.invalid/v1"
    assert os.environ["API_KEY"] == "synthetic-stored-key"


def test_failed_provider_save_does_not_apply_credentials_or_report_success(monkeypatch):
    monkeypatch.setattr(login_prompt, "_save_provider_config", lambda *args: False)
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    notify = MagicMock()
    monkeypatch.setattr(login_prompt, "_send_acp_notification", notify)
    monkeypatch.setenv("API_KEY", "original")
    result = login_prompt._handle_provider_api_key_config({
        "provider_id": "custom", "api_key": "new-synthetic-key",
        "base_url": "https://example.invalid/v1",
    }, MagicMock())
    assert result is None
    assert os.environ["API_KEY"] == "original"
    assert login_prompt.get_applied_api_key_config() is None
    assert notify.call_args.args[1] == "ui/loginError"


def test_invalid_assignment_is_atomic_and_does_not_expose_value():
    args = SimpleNamespace(set_env=["VALID=synthetic", "private-test-value"])
    with pytest.raises(ValueError) as error:
        parse_env_assignments(args)
    assert "private-test-value" not in str(error.value)


def test_node_check_uses_path_without_installing(monkeypatch):
    from siada.foundation import node_runtime

    monkeypatch.setattr(node_runtime, "find_node", lambda *args: "/synthetic/node")
    monkeypatch.setattr(launch_ui_with_acp.subprocess, "run", lambda *args, **kwargs: pytest.fail("ran installer"))
    assert launch_ui_with_acp._ensure_nodejs() is True


@pytest.mark.parametrize("section, value", [
    ("llm_config", "invalid-synthetic-section"),
    ("proactive", {"trigger_interval": "invalid-synthetic-section"}),
])
def test_invalid_section_does_not_discard_later_settings(tmp_path, monkeypatch, section, value):
    import yaml

    path = tmp_path / "conf.yaml"
    data = {"auto_update": {"enabled": False}, "enable_notification": False}
    data[section] = value
    path.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(config_loader, "_ensure_config_up_to_date", lambda *args: None)
    monkeypatch.setattr(config_loader.MCPConfigLoader, "load_config", lambda: None)
    monkeypatch.setattr(config_loader, "load_user_model_config", lambda: None)
    config = config_loader.load_conf(path)
    assert config.auto_update_config.enabled is False
    assert config.enable_notification is False


def test_first_setup_does_not_restart_other_daemons(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launch_ui_with_acp, "_expected_node_path", lambda: tmp_path / "node")
    monkeypatch.setattr(launch_ui_with_acp, "_ensure_nodejs", lambda: True)
    monkeypatch.setattr(launch_ui_with_acp, "_check_ui_bundle", lambda: None)
    monkeypatch.setattr(
        launch_ui_with_acp, "_kill_proactive_processes", lambda: pytest.fail("restarted other daemons"),
        raising=False,
    )
    launch_ui_with_acp._run_first_time_setup_if_needed()
    assert (tmp_path / ".siada-cli/.setup_version").is_file()
