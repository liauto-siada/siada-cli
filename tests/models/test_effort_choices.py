"""Configured effort choices control hints, selectors and model transitions."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401
from siada.config.model_config import UserModelConfig
from siada.entrypoint.helpers.model_setup import _user_model_settings
from siada.models import model_base_config
from siada.models.model_base_config import (
    ModelBaseConfig,
    coerce_reasoning_effort,
    get_valid_reasoning_efforts,
)
from siada.models.model_run_config import ModelRunConfig
from siada.support.slash_commands import SlashCommands, get_argument_hint


@pytest.fixture
def catalogue(monkeypatch):
    monkeypatch.setattr("siada.config.model_config.load_user_model_config", lambda: None)
    monkeypatch.setattr(
        "siada.entrypoint.helpers.model_setup.get_api_key_provider_models", lambda *args: []
    )
    entries = [
        ModelBaseConfig(
            model_name="bailian-kimi-k3",
            context_window=600_000,
            supports_extra_params=["reasoning_effort"],
            default_reasoning_effort="max",
            effort_choices=["max"],
        ),
        ModelBaseConfig(
            model_name="kivy-kimi-k3",
            context_window=600_000,
            supports_extra_params=["reasoning_effort"],
            default_reasoning_effort="max",
        ),
        ModelBaseConfig(
            model_name="claude-sonnet-5",
            context_window=200_000,
            supports_extra_params=["reasoning_effort"],
            default_reasoning_effort="high",
        ),
    ]
    monkeypatch.setattr(model_base_config, "_user_model_settings", entries)
    return entries


def test_local_and_user_config_preserve_choices(catalogue):
    data = {
        "model_name": "bailian-kimi-k3", "context_window": 600_000,
        "supports_extra_params": ["reasoning_effort"],
        "default_reasoning_effort": "max", "effort_choices": ["max"],
    }
    entry = ModelBaseConfig(**data)
    assert entry.effort_choices == ["max"]
    user = UserModelConfig.from_dict(data)
    assert user.to_dict()["effort_choices"] == ["max"]
    assert user.to_dict()["default_reasoning_effort"] == "max"
    assert _user_model_settings(MagicMock(models=[user]))[0].effort_choices == ["max"]


@pytest.mark.parametrize("invalid", [[], "max", ["ultra"], [1]])
def test_invalid_local_choices_are_rejected(invalid):
    with pytest.raises(ValueError, match="effort_choices"):
        ModelBaseConfig(model_name="example", context_window=1000, effort_choices=invalid)


def test_choices_override_family_and_default(catalogue):
    assert get_valid_reasoning_efforts("bailian-kimi-k3", "high") == ["max"]
    assert get_valid_reasoning_efforts("kivy-kimi-k3") == ["low", "high", "max"]
    assert get_valid_reasoning_efforts("custom", effort_choices=["low", "max"]) == ["low", "max"]
    assert get_argument_hint("effort", ModelRunConfig("bailian-kimi-k3")) == "[max]"
    assert get_argument_hint("effort", ModelRunConfig("kivy-kimi-k3")) == "[low | high | max]"
    assert get_argument_hint("model") == "[<model_name>]"


def test_selector_notification_contains_only_max(catalogue):
    io = MagicMock()
    io.acp_adapter.transport.is_connected = True
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig("bailian-kimi-k3")
    SlashCommands(io=io).cmd_effort(session, "")
    message = io.acp_adapter.transport.send_sync.call_args.args[0]
    assert message.method == "ui/showEffortSelector"
    assert message.params["efforts"] == ["max"]
    assert message.params["current"] == "max"


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh"])
def test_disallowed_command_does_not_persist_or_change_effort(catalogue, level):
    io = MagicMock(acp_adapter=None)
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig("bailian-kimi-k3")
    with patch("siada.config.config_loader.save_conf_field") as save:
        SlashCommands(io=io).cmd_effort(session, level)
    save.assert_not_called()
    assert session.siada_config.llm_config.reasoning_effort == "max"
    assert "Valid values for bailian-kimi-k3: max" in io.print_error.call_args.args[0]


def test_allowed_command_persists(catalogue):
    io = MagicMock(acp_adapter=None)
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig("bailian-kimi-k3")
    with patch("siada.config.config_loader.save_conf_field", return_value=True) as save:
        SlashCommands(io=io).cmd_effort(session, "max")
    save.assert_called_once_with("llm_config.reasoning_effort", "max")
    io.print_error.assert_not_called()


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max", "unknown"])
def test_mapping_never_escapes_choices(catalogue, level):
    assert coerce_reasoning_effort("bailian-kimi-k3", level, "high") == "max"


def test_chained_switch_preserves_intent(catalogue):
    old = ModelRunConfig("claude-sonnet-5")
    old.set_reasoning_effort("low")
    restricted = ModelRunConfig("bailian-kimi-k3")
    assert restricted.carry_over_reasoning_settings(old) == ("low", "max")
    restored = ModelRunConfig("claude-sonnet-5")
    assert restored.carry_over_reasoning_settings(restricted) == ("low", "low")


def test_default_outside_choices_is_mapped(catalogue):
    catalogue[0].default_reasoning_effort = "high"
    assert ModelRunConfig("bailian-kimi-k3").reasoning_effort == "max"


def test_banner_hint_refreshes_after_model_switch(catalogue):
    from siada.entrypoint.interaction.controller_ui import ControllerUI

    config = SimpleNamespace(
        acp_mode=True, io=MagicMock(), agent_name="test",
        llm_config=ModelRunConfig("bailian-kimi-k3"),
    )
    commands = MagicMock()
    commands.get_commands.return_value = ["/effort"]
    ui = ControllerUI(config, commands, lambda: None)
    with patch.object(ui, "_send_if_acp") as send, \
            patch.object(ui, "_resolve_ui_theme", return_value="dark"):
        ui.show_announcements()
        first = json.loads(send.call_args.args[0].params["content"])
        assert first["slash_commands"][0]["argument_hint"] == "[max]"
        config.llm_config = ModelRunConfig("claude-sonnet-5")
        ui.show_announcements()
        second = json.loads(send.call_args.args[0].params["content"])
        assert second["slash_commands"][0]["argument_hint"] == "[low | medium | high | xhigh | max]"


@pytest.mark.parametrize("cli_effort", [None, "high", "max"])
def test_startup_respects_choices(catalogue, cli_effort):
    from siada.entrypoint.helpers import model_setup

    args = SimpleNamespace(
        model="bailian-kimi-k3", provider="default", verbose=False,
        reasoning_effort=cli_effort, thinking=None, parallel_tool_calls=None,
    )
    conf = SimpleNamespace(model_config=None, llm_config=SimpleNamespace(
        model="bailian-kimi-k3", provider="default", reasoning_effort="low",
        enable_thinking=None, thinking=None, parallel_tool_calls=None,
    ))
    with patch.object(ModelRunConfig, "get_default_config",
                      side_effect=lambda: ModelRunConfig("bailian-kimi-k3")), \
            patch("siada.entrypoint.set_current_provider"):
        if cli_effort == "high":
            with pytest.raises(ValueError, match="Valid values for bailian-kimi-k3: max"):
                model_setup.get_config(args, MagicMock(), conf)
        else:
            config = model_setup.get_config(args, MagicMock(), conf)
            assert config.reasoning_effort == "max"
            assert config.user_reasoning_effort == (cli_effort or "low")