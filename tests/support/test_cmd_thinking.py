"""
Tests for cmd_thinking in SlashCommands.

/thinking shows, enables or disables thinking/reasoning. "off" sets
llm_config.enable_thinking=False — the absolute off-switch consumed by
ModelSettingsConverter (disable wire per family); "on" sets True (model
default reasoning). The value is persisted to conf.yaml
(llm_config.enable_thinking) and takes effect from the next turn.
"""
from unittest.mock import MagicMock, patch

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.support.slash_commands import SlashCommands


def _make_slash_commands() -> SlashCommands:
    io = MagicMock()
    io.acp_adapter = None
    return SlashCommands(io=io)


def _make_session(model: str) -> MagicMock:
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig(model)
    return session


class TestCmdThinkingShow:
    def test_no_args_shows_unset_model_default(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = None

        sc.cmd_thinking(session, "")

        sc.io.print_info.assert_called_once_with(
            "Thinking: unset (model default), effort: high"
        )

    def test_no_args_shows_on(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = True

        sc.cmd_thinking(session, "   ")

        sc.io.print_info.assert_called_once_with(
            "Thinking: on (model default), effort: high"
        )

    def test_no_args_shows_off(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = False

        sc.cmd_thinking(session, "")

        sc.io.print_info.assert_called_once_with(
            "Thinking: off (explicitly disabled), effort: high"
        )


class TestCmdThinkingSet:
    def test_off_updates_config_and_persists(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_thinking(session, "off")

        assert session.siada_config.llm_config.enable_thinking is False
        save_mock.assert_called_once_with("llm_config.enable_thinking", False)

    def test_on_updates_config_and_persists(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = False

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_thinking(session, "on")

        assert session.siada_config.llm_config.enable_thinking is True
        save_mock.assert_called_once_with("llm_config.enable_thinking", True)

    def test_true_false_aliases_accepted(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_thinking(session, "TRUE")
            assert session.siada_config.llm_config.enable_thinking is True
            sc.cmd_thinking(session, "false")
            assert session.siada_config.llm_config.enable_thinking is False

    def test_invalid_value_rejected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        sc.cmd_thinking(session, "maybe")

        sc.io.print_error.assert_called_once_with(
            "Invalid value 'maybe'. Usage: /thinking [on | off]"
        )
        # config untouched, nothing persisted
        assert session.siada_config.llm_config.enable_thinking is None


class TestCmdThinkingAcpPush:
    """The status bar shows ``model(thinking off)`` when disabled — /thinking
    must push the state to the ACP frontend so it updates live."""

    def test_off_pushes_acp_notification_when_connected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_thinking(session, "off")

        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/thinkingChanged"
        assert msg.params["thinking"] is False

    def test_on_pushes_acp_notification_when_connected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_thinking(session, "on")

        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/thinkingChanged"
        assert msg.params["thinking"] is True

    def test_skips_acp_push_when_disconnected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        adapter = MagicMock()
        adapter.transport.is_connected = False
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_thinking(session, "off")

        adapter.transport.send_sync.assert_not_called()


class TestThinkingConverterIntegration:
    def test_off_produces_disable_wire_per_family(self):
        # After /thinking off, the converter emits the family-specific
        # disable form from the next turn on.
        cases = {
            # model -> (extra_args, extra_body)
            "claude-sonnet-4-6": ({"thinking": {"type": "disabled"}}, None),
            "kimi-k3": (None, {"thinking": {"type": "disabled"}}),
            "qwen3.8-max": (None, {"enable_thinking": False}),
            # GLM-5.3 cannot disable — degrades to the minimum effort
            "glm-5.3": (
                None,
                {"thinking": {"type": "enabled", "clear_thinking": False},
                 "reasoning_effort": "low"},
            ),
        }
        for model, (expected_args, expected_body) in cases.items():
            cfg = ModelRunConfig(model)
            cfg.enable_thinking = False
            settings = ModelSettingsConverter.convert_model_settings(cfg)
            assert settings.extra_args == expected_args, f"{model} extra_args"
            assert settings.extra_body == expected_body, f"{model} extra_body"

    def test_on_restores_default_wire(self):
        # /thinking on (True): the model default reasoning applies again —
        # e.g. Claude 4.6+ adaptive thinking.
        cfg = ModelRunConfig("claude-sonnet-4-6")
        cfg.enable_thinking = True
        settings = ModelSettingsConverter.convert_model_settings(cfg)
        assert settings.extra_args["thinking"] == {
            "type": "adaptive", "display": "summarized"
        }
