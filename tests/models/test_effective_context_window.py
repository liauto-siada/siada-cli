"""Request admission refreshes its window from local model configuration."""

from types import SimpleNamespace

from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter
from siada.models import model_base_config
from siada.models.model_base_config import ModelBaseConfig


def test_local_context_window_replaces_stale_request_value(monkeypatch):
    monkeypatch.setattr(model_base_config, "_user_model_settings", [
        ModelBaseConfig(model_name="custom-model", context_window=128_000),
    ])
    config = SimpleNamespace(model_name="custom-model", context_window=1_000_000)
    context = SimpleNamespace(model_run_config=config)
    filter_ = ApiMessageTransferFilter()
    filter_._resolve_effective_context_window(context)
    assert config.context_window == 128_000
    filter_._resolve_effective_context_window(context)
    assert config.context_window == 128_000


def test_unknown_model_keeps_request_window(monkeypatch):
    monkeypatch.setattr(model_base_config, "_user_model_settings", [])
    config = SimpleNamespace(model_name="custom-model", context_window=128_000)
    ApiMessageTransferFilter()._resolve_effective_context_window(
        SimpleNamespace(model_run_config=config)
    )
    assert config.context_window == 128_000