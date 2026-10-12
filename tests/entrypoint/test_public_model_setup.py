"""Model setup remains available before API-key configuration.

The second-launch pre-load (``get_config`` ->
``_pre_load_default_provider_models``) fills default-provider model settings
from the catalogue. When a models.json catalogue is already loaded for this
session it must MERGE catalogue models in (missing names only), never replace
the user's entries: custom thinking budgets / prices and models the catalogue
does not know must survive. Nothing here writes models.json.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import siada.config.conf_store as conf_store
import siada.config.model_config as model_config
from siada.config.config_loader import Config, LLMConfig
from siada.entrypoint.helpers import model_setup
from siada.entrypoint.helpers.model_setup import get_config_from_conf
from siada.models import model_base_config
from siada.models.model_base_config import DEFAULT_MODEL_NAME, ModelBaseConfig


@pytest.fixture(autouse=True)
def temp_siada_home(tmp_path, monkeypatch):
    """Redirect ``~/.siada-cli`` so no real models.json/conf.yaml is touched."""
    home = tmp_path / ".siada-cli"
    home.mkdir()
    monkeypatch.setattr(conf_store, "SIADA_HOME", home)
    monkeypatch.setattr(model_config, "SIADA_HOME", home)
    return home


def _catalog_entry(name):
    return ModelBaseConfig(
        model_name=name,
        context_window=128_000,
        max_tokens=8192,
        parallel_tool_calls=True,
    )


def test_first_launch_can_resolve_model_before_credentials(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    with patch("siada.entrypoint.helpers.model_setup.os.getenv", return_value=None):
        config = get_config_from_conf(Mock(), Config())
    assert config.provider == "default"
    assert config.model_name == DEFAULT_MODEL_NAME


@pytest.mark.parametrize("base_url, api_key", [(42, ["test"]), (None, None), (" ", "")])
def test_model_setup_without_usable_credentials_leaves_login_available(
    monkeypatch, base_url, api_key
):
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    conf = Config(llm_config=LLMConfig(provider="default", base_url=base_url, api_key=api_key))

    config = get_config_from_conf(Mock(), conf)

    assert config.provider == "default"
    assert model_setup.os.getenv("BASE_URL") is None
    assert model_setup.os.getenv("API_KEY") is None


def test_preload_merges_and_keeps_user_defined_thinking_and_prices(
    monkeypatch, temp_siada_home
):
    """A loaded models.json entry is never replaced by the catalogue entry."""
    user_entry = ModelBaseConfig(
        model_name="gpt-5.2",
        context_window=42_000,
        max_tokens=2048,
        default_thinking_tokens=4096,
        default_reasoning_effort="high",
        input_price=1.25,
        output_price=5.5,
        cache_write_price=0.5,
        cache_read_price=0.1,
    )
    existing = [user_entry]
    monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
    provider_models = [_catalog_entry("gpt-5.2"), _catalog_entry("brand-new-model")]
    monkeypatch.setattr(
        model_setup, "get_api_key_provider_models", lambda *a, **k: provider_models
    )
    replace_calls = []
    monkeypatch.setattr(
        model_base_config,
        "set_user_model_settings",
        lambda models: replace_calls.append(models),
    )
    conf = SimpleNamespace(
        llm_config=SimpleNamespace(
            provider_id="openai", base_url="https://api.openai.com/v1"
        )
    )

    model_setup._pre_load_default_provider_models(conf, "gpt-5.2")

    # The user's catalogue object is extended, not swapped out.
    assert model_base_config._user_model_settings is existing
    assert [entry.model_name for entry in existing] == ["gpt-5.2", "brand-new-model"]
    kept = existing[0]
    assert kept.default_thinking_tokens == 4096
    assert kept.default_reasoning_effort == "high"
    assert kept.input_price == 1.25
    assert kept.output_price == 5.5
    assert kept.cache_write_price == 0.5
    assert kept.cache_read_price == 0.1
    assert kept.context_window == 42_000
    assert kept.max_tokens == 2048
    assert replace_calls == []
    assert not (temp_siada_home / "models.json").exists()


def test_preload_installs_catalogue_when_no_models_json(monkeypatch, temp_siada_home):
    """Without a user catalogue the provider catalogue is still the source."""
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    provider_models = [_catalog_entry("gpt-5.2")]
    monkeypatch.setattr(
        model_setup, "get_api_key_provider_models", lambda *a, **k: provider_models
    )
    conf = SimpleNamespace(
        llm_config=SimpleNamespace(
            provider_id="openai", base_url="https://api.openai.com/v1"
        )
    )

    model_setup._pre_load_default_provider_models(conf, "gpt-5.2")

    assert model_base_config._user_model_settings is provider_models
    assert not (temp_siada_home / "models.json").exists()


def test_provider_switch_loads_existing_models_json_before_merging(
    monkeypatch, temp_siada_home
):
    """Switching providers preserves a catalogue not loaded at startup."""
    path = temp_siada_home / "models.json"
    path.write_text(json.dumps({
        "models": [{
            "model_name": "gpt-5.2",
            "context_window": 42_000,
            "max_tokens": 512,
            "default_thinking_tokens": 2048,
            "default_reasoning_effort": "high",
            "input_price": 1.25,
            "output_price": 5.5,
            "cache_write_price": 0.5,
            "cache_read_price": 0.1,
        }],
    }), encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)

    model_setup.merge_provider_models_into_user_settings(
        [_catalog_entry("gpt-5.2"), _catalog_entry("new-model")]
    )

    kept, appended = model_base_config._user_model_settings
    assert kept.model_name == "gpt-5.2"
    assert kept.context_window == 42_000
    assert kept.max_tokens == 512
    assert kept.default_thinking_tokens == 2048
    assert kept.default_reasoning_effort == "high"
    assert (kept.input_price, kept.output_price) == (1.25, 5.5)
    assert (kept.cache_write_price, kept.cache_read_price) == (0.5, 0.1)
    assert appended.model_name == "new-model"
    assert path.read_bytes() == original


@pytest.mark.parametrize("payload", [
    '{"models": ["sk-test-private-payload"]',
    '{"models": [{"sk-test-private-payload": 1}]}',
    '{"models": "sk-test-private-payload"}',
])
@pytest.mark.parametrize("io_present", [False, True])
def test_invalid_models_json_keeps_protocol_stdout_and_values_private(
    monkeypatch, temp_siada_home, capsys, payload, io_present
):
    from siada.io.io import InputOutput

    path = temp_siada_home / "models.json"
    path.write_text(payload, encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(model_base_config, "_user_model_settings", None)
    monkeypatch.setattr(InputOutput, "_instance", None)
    if io_present:
        InputOutput(pretty=False, fancy_input=False)

    model_setup.merge_provider_models_into_user_settings([_catalog_entry("new-model")])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "models.json" in captured.err
    assert "sk-test-private-payload" not in captured.err
    assert model_base_config._user_model_settings[0].model_name == "new-model"
    assert path.read_bytes() == original


# ---------------------------------------------------------------------------
# reasoning_effort capability is tri-state
#
# A model that DECLARES its capabilities without listing reasoning_effort is a
# real denial; a model whose capabilities are undeclared (supports_extra_params
# is None — e.g. a name absent from every catalogue, synthesized by the
# provider-catalogue fallback) is NOT. Only the former may fail/print an error;
# the latter passes the value through for the gateway to judge.
# ---------------------------------------------------------------------------

def _undeclared_model_entry(name):
    return ModelBaseConfig(
        model_name=name,
        context_window=128_000,
        parallel_tool_calls=True,
    )


def _make_reasoning_args(model, reasoning_effort=None):
    return SimpleNamespace(
        model=model,
        provider=None,
        verbose=False,
        reasoning_effort=reasoning_effort,
        thinking=None,
        parallel_tool_calls=None,
    )


def test_conf_effort_passes_through_undeclared_model(monkeypatch, temp_siada_home):
    monkeypatch.setattr(
        model_base_config, "_user_model_settings", [_undeclared_model_entry("undeclared-x")]
    )
    io = Mock()
    conf = Config(
        llm_config=LLMConfig(
            provider="default", model="undeclared-x", reasoning_effort="medium"
        )
    )

    config = get_config_from_conf(io, conf)

    assert config.model_name == "undeclared-x"
    assert config.reasoning_effort == "medium"
    io.print_error.assert_not_called()


def test_cli_effort_on_undeclared_model_passes_through(monkeypatch, temp_siada_home):
    monkeypatch.setattr(
        model_base_config, "_user_model_settings", [_undeclared_model_entry("undeclared-y")]
    )
    io = Mock()
    conf = Config(llm_config=LLMConfig(provider="default", model="undeclared-y"))

    config = model_setup.get_config(_make_reasoning_args("undeclared-y", "high"), io, conf)

    assert config.model_name == "undeclared-y"
    assert config.reasoning_effort == "high"
    io.print_error.assert_not_called()


def test_cli_effort_on_explicitly_unsupported_model_raises(monkeypatch, temp_siada_home):
    entry = ModelBaseConfig(
        model_name="thinking-only",
        context_window=128_000,
        supports_extra_params=["thinking_tokens"],
        parallel_tool_calls=True,
    )
    monkeypatch.setattr(model_base_config, "_user_model_settings", [entry])
    io = Mock()
    conf = Config(llm_config=LLMConfig(provider="default", model="thinking-only"))

    with pytest.raises(ValueError, match="does not support reasoning effort"):
        model_setup.get_config(_make_reasoning_args("thinking-only", "high"), io, conf)

    io.print_error.assert_called()