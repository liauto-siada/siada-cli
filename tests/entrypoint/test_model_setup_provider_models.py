"""API-key provider model setup when the models.dev cache is unavailable."""

from unittest.mock import MagicMock

import pytest

from siada.entrypoint.helpers import model_setup
from siada.models.model_base_config import ModelBaseConfig
from siada.provider import models_dev


def test_provider_models_are_used_without_rewriting_defaults(monkeypatch):
    provider_model = ModelBaseConfig(
        model_name="glm-5.3", context_window=200_000,
        supports_extra_params=["reasoning_effort"], default_reasoning_effort="max",
    )
    fetch = MagicMock(return_value=[provider_model])
    monkeypatch.setattr(models_dev, "get_provider_model_configs", fetch)

    assert model_setup.get_api_key_provider_models(
        "glm", "glm-5.3", "https://example.invalid/v1",
    ) == [provider_model]
    fetch.assert_called_once_with("glm", "glm-5.3", "https://example.invalid/v1")


def test_normal_no_cache_path_keeps_unspecified_capabilities(monkeypatch):
    monkeypatch.setattr(models_dev, "get_providers_for_ui", lambda: [])

    # A name outside the built-in catalogue must not gain declared capabilities.
    models = model_setup.get_api_key_provider_models("glm", "glm-5.10")

    assert len(models) == 1
    assert models[0].model_name == "glm-5.10"
    assert models[0].supports_extra_params is None
    assert models[0].default_reasoning_effort is None

    # An exact built-in match still inherits its explicit capabilities.
    known = model_setup.get_api_key_provider_models("glm", "glm-5.3")

    assert known[0].supports_extra_params == ["reasoning_effort"]
    assert known[0].default_reasoning_effort == "max"


@pytest.mark.parametrize(
    "error", [OSError("cache"), KeyError("models"), TypeError("data"), ValueError("data")],
)
def test_expected_cache_errors_use_unmodified_selected_model(monkeypatch, error):
    fetch = MagicMock(side_effect=error)
    warning = MagicMock()
    monkeypatch.setattr(models_dev, "get_provider_model_configs", fetch)
    monkeypatch.setattr(model_setup.logger, "warning", warning)

    models = model_setup.get_api_key_provider_models("glm", "glm-5.3")

    assert len(models) == 1
    assert models[0].model_name == "glm-5.3"
    assert (models[0].context_window, models[0].max_tokens) == (128_000, 8192)
    assert models[0].supports_extra_params is None
    assert models[0].default_reasoning_effort is None
    warning.assert_called_once()
    assert warning.call_args.args[1] is error
    fetch.assert_called_once_with("glm", "glm-5.3", "")


def test_cache_error_with_no_selected_model_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        models_dev, "get_provider_model_configs", MagicMock(side_effect=KeyError("models")),
    )
    assert model_setup.get_api_key_provider_models("glm", "") == []


def test_unexpected_provider_error_is_not_silently_swallowed(monkeypatch):
    monkeypatch.setattr(
        models_dev, "get_provider_model_configs", MagicMock(side_effect=RuntimeError("bug")),
    )
    with pytest.raises(RuntimeError, match="bug"):
        model_setup.get_api_key_provider_models("glm", "glm-5.3")