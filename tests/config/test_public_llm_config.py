"""Public provider configuration tolerates invalid fields and preserves env."""

import os

import pytest
import yaml

from siada.config import config_loader
from siada.config import conf_store
from siada.io.io import InputOutput


@pytest.mark.parametrize(
    "field",
    [
        "model", "provider", "base_url", "api_key",
        "reasoning_effort", "vision_model", "vision_provider",
    ],
)
@pytest.mark.parametrize("value", [42, ["test"], {"value": "test"}, True])
def test_non_string_provider_fields_are_ignored(field, value, caplog, monkeypatch):
    monkeypatch.setattr(
        config_loader.logger, "handlers", [*config_loader.logger.handlers, caplog.handler]
    )
    config = config_loader.LLMConfig.from_dict({field: value})

    assert getattr(config, field) is None
    assert "expected a string" in caplog.text
    assert str(value) not in "\n".join(record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "env_base, env_key, expected_base, expected_key",
    [
        ("http://127.0.0.1:9/v1", "sk-test-env", "http://127.0.0.1:9/v1", "sk-test-env"),
        ("http://127.0.0.1:9/v1", None, "http://127.0.0.1:9/v1", "sk-test-stored"),
        (None, "sk-test-env", "https://api.example.com/v1", "sk-test-env"),
        (" ", "", "https://api.example.com/v1", "sk-test-stored"),
        (None, None, "https://api.example.com/v1", "sk-test-stored"),
    ],
)
def test_loading_stored_credentials_preserves_each_explicit_env_field(
    tmp_path, monkeypatch, env_base, env_key, expected_base, expected_key
):
    path = tmp_path / "conf.yaml"
    path.write_text(
        yaml.safe_dump({
            "llm_config": {
                "provider": "default",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test-stored",
            },
        }),
        encoding="utf-8",
    )
    for name, value in (("BASE_URL", env_base), ("API_KEY", env_key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(config_loader, "_ensure_config_up_to_date", lambda path: None)
    monkeypatch.setattr(config_loader.MCPConfigLoader, "load_config", lambda: None)
    monkeypatch.setattr(config_loader, "load_user_model_config", lambda: None)
    original = path.read_bytes()

    config = config_loader.load_conf(path)

    assert config.llm_config.api_key == "sk-test-stored"
    assert os.environ["BASE_URL"] == expected_base
    assert os.environ["API_KEY"] == expected_key
    assert path.read_bytes() == original


def test_invalid_credentials_do_not_stop_other_config_sections(tmp_path, monkeypatch):
    path = tmp_path / "conf.yaml"
    path.write_text(
        yaml.safe_dump({
            "llm_config": {"provider": "default", "base_url": 42, "api_key": ["test"]},
            "proactive": {"enabled": False},
        }),
        encoding="utf-8",
    )
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(config_loader, "_ensure_config_up_to_date", lambda path: None)
    monkeypatch.setattr(config_loader.MCPConfigLoader, "load_config", lambda: None)
    monkeypatch.setattr(config_loader, "load_user_model_config", lambda: None)

    config = config_loader.load_conf(path)

    assert config.llm_config.base_url is None
    assert config.llm_config.api_key is None
    assert config.proactive_config.enabled is False
    assert "BASE_URL" not in os.environ
    assert "API_KEY" not in os.environ


@pytest.mark.parametrize(
    "bad_section, bad_value",
    [
        ("llm_config", "not-a-mapping"),
        ("proactive", {"trigger_interval": "not-a-number"}),
        ("memory", {"holographic": {"hrr_dim": "not-a-number"}}),
    ],
)
def test_bad_section_preserves_later_sections(
    tmp_path, monkeypatch, bad_section, bad_value
):
    path = tmp_path / "conf.yaml"
    data = {
        "proactive": {"enabled": False},
        "auto_update": {"enabled": False},
        "enable_notification": False,
        "preferred_language": "en",
    }
    data[bad_section] = bad_value
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(config_loader, "_ensure_config_up_to_date", lambda path: None)
    monkeypatch.setattr(config_loader.MCPConfigLoader, "load_config", lambda: None)
    monkeypatch.setattr(config_loader, "load_user_model_config", lambda: None)

    config = config_loader.load_conf(path)

    if bad_section != "proactive":
        assert config.proactive_config.enabled is False
    assert config.auto_update_config.enabled is False
    assert config.enable_notification is False
    assert config.preferred_language == "en"
    assert path.read_bytes() == original


def test_yaml_diagnostic_does_not_write_protocol_stdout_or_secret(
    tmp_path, monkeypatch, capsys, caplog
):
    path = tmp_path / "conf.yaml"
    path.write_text("api_key: *sk-test-private-alias\n", encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(
        conf_store.logger._logger,
        "handlers",
        [*conf_store.logger.handlers, caplog.handler],
    )
    monkeypatch.setattr(config_loader, "_ensure_config_up_to_date", lambda path: None)
    monkeypatch.setattr(config_loader.MCPConfigLoader, "load_config", lambda: None)
    monkeypatch.setattr(config_loader, "load_user_model_config", lambda: None)
    monkeypatch.setattr(InputOutput, "_instance", None)
    InputOutput(pretty=False, fancy_input=False)
    config = config_loader.load_conf(path)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "line 1, column" in captured.err
    assert "sk-test-private-alias" not in captured.err + caplog.text
    assert config.llm_config.api_key is None
    assert path.read_bytes() == original


def test_yaml_update_error_does_not_log_secret_or_change_file(
    tmp_path, monkeypatch, caplog
):
    path = tmp_path / "conf.yaml"
    path.write_text("api_key: *sk-test-private-alias\n", encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(
        conf_store.logger._logger,
        "handlers",
        [*conf_store.logger.handlers, caplog.handler],
    )

    assert conf_store.save_conf_fields({"preferred_language": "en"}, path) is False
    assert "line 1, column" in caplog.text
    assert "sk-test-private-alias" not in caplog.text
    assert path.read_bytes() == original


@pytest.mark.parametrize("operation", ["write", "update"])
def test_config_save_error_keeps_original_file_and_omits_exception_payload(
    tmp_path, monkeypatch, caplog, operation
):
    path = tmp_path / "conf.yaml"
    path.write_text("preferred_language: en\n", encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(
        conf_store.logger._logger,
        "handlers",
        [*conf_store.logger.handlers, caplog.handler],
    )

    def fail_write(*args, **kwargs):
        raise OSError("API_KEY=sk-test-save-payload")

    monkeypatch.setattr(conf_store, "_atomic_write_text", fail_write)
    if operation == "write":
        saved = conf_store.write_conf_dict({"preferred_language": "zh"}, path)
    else:
        saved = conf_store.save_conf_fields({"preferred_language": "zh"}, path)

    assert saved is False
    assert "OSError" in caplog.text
    assert "sk-test-save-payload" not in caplog.text
    assert path.read_bytes() == original


def test_invalid_config_encoding_reports_safe_error_without_changing_file(
    tmp_path, monkeypatch, caplog
):
    path = tmp_path / "conf.yaml"
    path.write_bytes(b"api_key: sk-test-encoding-payload\xff\n")
    original = path.read_bytes()
    diagnostics = []
    monkeypatch.setattr(
        conf_store.logger._logger,
        "handlers",
        [*conf_store.logger.handlers, caplog.handler],
    )

    assert conf_store.read_conf_dict(path, on_error=diagnostics.append) == {}
    assert "UnicodeDecodeError" in diagnostics[0]
    assert "sk-test-encoding-payload" not in "".join(diagnostics) + caplog.text
    assert path.read_bytes() == original