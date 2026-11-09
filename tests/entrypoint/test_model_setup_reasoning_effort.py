"""reasoning_effort capability is tri-state at model-setup time.

A model that DECLARES its capabilities without listing reasoning_effort is a
real denial (an explicit "does not support"). A model whose capabilities are
undeclared (``supports_extra_params`` is None - e.g. a name absent from every
catalogue, synthesized by the provider-catalogue fallback) is NOT: only the
former may fail or print an error; the latter passes the value through for the
gateway to judge.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.config.config_loader import Config, LLMConfig
from siada.entrypoint.helpers import model_setup
from siada.entrypoint.helpers.model_setup import get_config_from_conf
from siada.models import model_base_config
from siada.models.model_base_config import ModelBaseConfig


@pytest.fixture(autouse=True)
def _default_provider_credentials(monkeypatch):
    """get_config exits early without default-provider credentials."""
    monkeypatch.setenv("BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("API_KEY", "sk-test")


def _undeclared_model_entry(name):
    return ModelBaseConfig(
        model_name=name,
        context_window=128_000,
        parallel_tool_calls=True,
    )


def _reasoning_args(model, reasoning_effort=None):
    return SimpleNamespace(
        model=model,
        provider=None,
        verbose=False,
        reasoning_effort=reasoning_effort,
        thinking=None,
        parallel_tool_calls=None,
    )


def test_conf_effort_passes_through_undeclared_model(monkeypatch):
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


def test_cli_effort_on_undeclared_model_passes_through(monkeypatch):
    monkeypatch.setattr(
        model_base_config, "_user_model_settings", [_undeclared_model_entry("undeclared-y")]
    )
    io = Mock()
    conf = Config(llm_config=LLMConfig(provider="default", model="undeclared-y"))

    config = model_setup.get_config(_reasoning_args("undeclared-y", "high"), io, conf)

    assert config.model_name == "undeclared-y"
    assert config.reasoning_effort == "high"
    io.print_error.assert_not_called()


def test_cli_effort_on_explicitly_unsupported_model_raises(monkeypatch):
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
        model_setup.get_config(_reasoning_args("thinking-only", "high"), io, conf)

    io.print_error.assert_called()