"""Provider-catalogue models MERGE into the user's list, never replace it.

The second-launch pre-load (``get_config`` ->
``_pre_load_default_provider_models``) and a mid-session ``/configure`` both
fill default-provider model settings from the catalogue. When a models.json
catalogue is already loaded for the session they must MERGE (missing names
only): custom thinking budgets / prices and models the catalogue does not know
must survive. Before the fix they replaced the whole list, which made every
models.json model disappear from ``/model`` and report
``Model 'X' not supported.``
"""

import json
from types import SimpleNamespace

import pytest

import siada.config.conf_store as conf_store
import siada.config.model_config as model_config
from siada.entrypoint.helpers import model_setup
from siada.models import model_base_config
from siada.models.model_base_config import ModelBaseConfig


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


def _default_provider_conf():
    return SimpleNamespace(
        llm_config=SimpleNamespace(
            provider_id="openai", base_url="https://api.openai.com/v1"
        )
    )


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

    model_setup._pre_load_default_provider_models(_default_provider_conf(), "gpt-5.2")

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

    model_setup._pre_load_default_provider_models(_default_provider_conf(), "gpt-5.2")

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


def test_preload_keeps_user_models_selectable(monkeypatch, temp_siada_home):
    """Regression: the pre-load must not make the user's own models vanish.

    Before the fix the pre-load replaced the whole list with the single
    synthesized entry for the configured model, so ``/model`` reported
    ``Model 'X' not supported.`` for every models.json model. This is the
    reported field bug, asserted through the user-facing service.
    """
    from siada.services.model_info_service import ModelInfoService

    user_models = [
        ModelBaseConfig(
            model_name="openai/azure-gpt-6-astra",
            context_window=272_000,
            max_tokens=65536,
            supports_images=True,
            parallel_tool_calls=True,
        ),
        ModelBaseConfig(model_name="zai/kivy-glm-5_2", context_window=200_000),
    ]
    monkeypatch.setattr(model_base_config, "_user_model_settings", user_models)
    # conf.yaml's model is absent from models.json — that is what triggers the
    # pre-load fallback in the first place.
    monkeypatch.setattr(
        model_setup,
        "get_api_key_provider_models",
        lambda *a, **k: [ModelBaseConfig(
            model_name="azure-gpt-6_1-sol",
            context_window=128_000,
            max_tokens=8192,
            parallel_tool_calls=True,
        )],
    )
    conf = SimpleNamespace(
        llm_config=SimpleNamespace(provider_id="custom", base_url="http://gw.invalid/v1")
    )

    model_setup._pre_load_default_provider_models(conf, "azure-gpt-6_1-sol")

    names = ModelInfoService.get_model_names()
    assert names == [
        "openai/azure-gpt-6-astra",
        "zai/kivy-glm-5_2",
        "azure-gpt-6_1-sol",
    ]
    for name in names:
        assert ModelInfoService.is_model_supported(name) is True