"""Provider-first ordering preserves local models and their metadata."""
from siada.entrypoint.helpers import model_setup
from siada.models import model_base_config
from siada.models.model_base_config import ModelBaseConfig
from siada.config.config_loader import LLMConfig


def test_provider_precedes_user_catalogue_without_duplicates(monkeypatch):
    local = ModelBaseConfig(model_name="local", context_window=42000, max_tokens=512)
    existing = [local]
    monkeypatch.setattr(model_base_config, "_user_model_settings", existing)
    monkeypatch.setattr("siada.config.model_config.load_user_model_config", lambda: None)
    model_setup.merge_provider_models_into_user_settings([
        ModelBaseConfig(model_name="active", context_window=128000, max_tokens=8192),
        ModelBaseConfig(model_name="local", context_window=128000, max_tokens=8192),
        ModelBaseConfig(model_name="active", context_window=128000, max_tokens=8192),
    ])
    assert [m.model_name for m in existing] == ["active", "local"]
    assert existing[1] is local


def test_config_preserves_provider_identity():
    config = LLMConfig.from_dict({"provider": "default", "provider_id": "custom"})
    assert config.provider_id == "custom"
    assert config.to_dict()["provider_id"] == "custom"


def test_custom_uses_only_the_entered_model(monkeypatch):
    from siada.provider import models_dev
    def unexpected_lookup():
        raise AssertionError("Custom must not query a provider catalogue")
    monkeypatch.setattr(models_dev, "get_providers_for_ui", unexpected_lookup)
    models = models_dev.get_provider_model_configs("custom", "entered", "https://api.deepseek.com/v1")
    assert [m.model_name for m in models] == ["entered"]