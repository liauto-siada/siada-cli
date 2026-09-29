"""
Tests for cmd_effort in SlashCommands.

/effort shows or sets the reasoning effort level of the current model at
runtime. The new value is written to session.siada_config.llm_config (taking
effect from the next turn, since ModelSettings are rebuilt from the live
llm_config on every run) and persisted to conf.yaml.
"""
from unittest.mock import MagicMock, patch

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.models.model_run_config import ModelRunConfig
from siada.support.slash_commands import SlashCommands


def _make_slash_commands() -> SlashCommands:
    io = MagicMock()
    io.acp_adapter = None
    return SlashCommands(io=io)


def _make_session(model: str) -> MagicMock:
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig(model)
    return session


class TestCmdEffortShow:
    def test_no_args_shows_current_and_default(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: high (model default: high)"
        )

    def test_no_args_shows_off_when_unset(self):
        sc = _make_slash_commands()
        session = _make_session("gemini-3.5-flash")
        session.siada_config.llm_config.reasoning_effort = None

        sc.cmd_effort(session, "   ")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: off (model default: low)"
        )

    def test_no_args_shows_thinking_budget_when_effort_unset_but_thinking_on(self):
        # Some models reason via a token budget even when reasoning_effort is
        # off (e.g. GLM-5.2 defaults to thinking_tokens=1024 -> "1k"). Display
        # should not read "(off)" as if no reasoning happens at all.
        sc = _make_slash_commands()
        session = _make_session("glm-5.2")
        session.siada_config.llm_config.reasoning_effort = None

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: off (thinking budget 1k ON) (model default: (none))"
        )


class TestCmdEffortSet:
    def test_set_valid_level_updates_config_and_persists(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_effort(session, "max")

        assert session.siada_config.llm_config.get_reasoning_effort() == "max"
        save_mock.assert_called_once_with("llm_config.reasoning_effort", "max")
        sc.io.print_info.assert_called_once_with("Reasoning effort set to: max")

    def test_set_pushes_acp_notification_when_connected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ):
            sc.cmd_effort(session, "low")

        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/reasoningEffortChanged"
        assert msg.params["effort"] == "low"

    def test_set_skips_acp_push_when_disconnected(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        adapter = MagicMock()
        adapter.transport.is_connected = False
        sc.io.acp_adapter = adapter

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ):
            sc.cmd_effort(session, "low")

        adapter.transport.send_sync.assert_not_called()

    def test_claude_model_accepts_xhigh(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_effort(session, "xhigh")

        assert session.siada_config.llm_config.get_reasoning_effort() == "xhigh"

    def test_non_claude_model_rejects_xhigh(self):
        sc = _make_slash_commands()
        session = _make_session("gemini-3.5-flash")

        sc.cmd_effort(session, "xhigh")

        assert session.siada_config.llm_config.get_reasoning_effort() == "low"
        sc.io.print_error.assert_called_once()
        assert "xhigh" in sc.io.print_error.call_args[0][0]

    def test_model_default_is_always_accepted(self):
        # gpt-5.6 ships with default_reasoning_effort="max" even though it is
        # not a Claude model — the model's own default must stay selectable.
        sc = _make_slash_commands()
        session = _make_session("gpt-5.6-terra")
        session.siada_config.llm_config.reasoning_effort = "low"

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_effort(session, "max")

        assert session.siada_config.llm_config.get_reasoning_effort() == "max"

    def test_invalid_level_prints_error_and_keeps_value(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        sc.cmd_effort(session, "ultra")

        assert session.siada_config.llm_config.get_reasoning_effort() == "high"
        sc.io.print_error.assert_called_once()
        assert "ultra" in sc.io.print_error.call_args[0][0]

    def test_model_without_effort_support_prints_error(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.supports_extra_params = ["thinking_tokens"]

        sc.cmd_effort(session, "high")

        assert session.siada_config.llm_config.get_reasoning_effort() == "high"
        sc.io.print_error.assert_called_once_with(
            "Model claude-sonnet-5 does not support reasoning effort"
        )


class TestCmdEffortKimiK3:
    """Kimi K3 always reasons; valid efforts are low/high/max (no medium),
    default "max", sent as the top-level reasoning_effort request field
    (routed through extra_body to survive litellm's drop_params)."""

    def test_default_is_max(self):
        sc = _make_slash_commands()
        session = _make_session("kimi-k3")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: max (model default: max)"
        )

    def test_accepts_low_high_max(self):
        for level in ("low", "high", "max"):
            sc = _make_slash_commands()
            session = _make_session("kimi-k3")

            with patch(
                "siada.config.config_loader.save_conf_field", return_value=True
            ):
                sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == level
            sc.io.print_error.assert_not_called()

    def test_rejects_medium(self):
        sc = _make_slash_commands()
        session = _make_session("kimi-k3")

        sc.cmd_effort(session, "medium")

        assert session.siada_config.llm_config.get_reasoning_effort() == "max"
        sc.io.print_error.assert_called_once_with(
            "Invalid effort level 'medium'. Valid values for kimi-k3: "
            "low, high, max"
        )

    def test_converter_routes_effort_via_reasoning_dict(self):
        from siada.models.model_setting_converter import ModelSettingsConverter

        config = ModelRunConfig("kimi-k3")
        config.set_reasoning_effort("low")
        settings = ModelSettingsConverter.convert_model_settings(config)

        # Non-Claude/non-Gemini models carry effort in
        # extra_body["reasoning_effort"], merged into the request body as the
        # top-level reasoning_effort field.
        assert settings.extra_body["reasoning_effort"] == "low"

    def test_converter_always_emits_max(self):
        # The converter emits every effort level unconditionally (even
        # "max") — Kimi K3+'s max-omission is a gateway concern, not a
        # converter one.
        from siada.models.model_setting_converter import ModelSettingsConverter

        config = ModelRunConfig("kimi-k3")
        config.set_reasoning_effort("max")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert settings.extra_body["reasoning_effort"] == "max"


class TestCmdEffortGlm:
    """GLM-5.3 supports reasoning_effort (low/high/max, default "max").
    GLM-5.2 uses the older thinking_tokens+clear_thinking path and does NOT
    support reasoning_effort."""

    def test_glm52_does_not_support_effort(self):
        sc = _make_slash_commands()
        session = _make_session("glm-5.2")

        sc.cmd_effort(session, "high")

        assert session.siada_config.llm_config.get_reasoning_effort() is None
        sc.io.print_error.assert_called_once_with(
            "Model glm-5.2 does not support reasoning effort"
        )

    def test_glm53_default_is_max(self):
        sc = _make_slash_commands()
        session = _make_session("glm-5.3")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: max (model default: max)"
        )

    def test_glm53_accepts_low_high_max(self):
        for level in ("low", "high", "max"):
            sc = _make_slash_commands()
            session = _make_session("glm-5.3")

            with patch(
                "siada.config.config_loader.save_conf_field", return_value=True
            ):
                sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == level
            sc.io.print_error.assert_not_called()

    def test_glm53_converter_omits_effort_at_max(self):
        from siada.models.model_setting_converter import ModelSettingsConverter

        # GLM-5.3 (official): always reasons via reasoning_effort, but sending
        # "max" makes Zhipu reject the request. When effort is "max" (also
        # the default) we omit the parameter and let Zhipu use its built-in default.
        config = ModelRunConfig("glm-5.3")
        settings = ModelSettingsConverter.convert_model_settings(config)

        assert settings.extra_body is None or "reasoning" not in settings.extra_body

    def test_glm53_converter_sends_low_high_via_reasoning(self):
        from siada.models.model_setting_converter import ModelSettingsConverter

        # glm-5.3 carries the effort via extra_body["reasoning_effort"],
        # landing as the top-level reasoning_effort request field and avoiding
        # drop_params.
        for level in ("low", "high"):
            config = ModelRunConfig("glm-5.3")
            config.set_reasoning_effort(level)
            settings = ModelSettingsConverter.convert_model_settings(config)

            assert settings.extra_body["reasoning_effort"] == level


class TestCmdEffortDeepSeek:
    """DeepSeek thinking intensity control: {"reasoning_effort": "low/high/max"}
    (level-based, not a token budget). Default "high"."""

    def test_default_is_high(self):
        sc = _make_slash_commands()
        session = _make_session("deepseek-v4-flash")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: high (model default: high)"
        )

    def test_accepts_low_high_max(self):
        for model in ("deepseek-v4-pro", "deepseek-v4-pro-0813"):
            for level in ("low", "high", "max"):
                sc = _make_slash_commands()
                session = _make_session(model)

                with patch(
                    "siada.config.config_loader.save_conf_field", return_value=True
                ):
                    sc.cmd_effort(session, level)

                assert session.siada_config.llm_config.get_reasoning_effort() == level
                sc.io.print_error.assert_not_called()

    def test_rejects_medium(self):
        sc = _make_slash_commands()
        session = _make_session("deepseek-v4-pro")

        sc.cmd_effort(session, "medium")

        assert session.siada_config.llm_config.get_reasoning_effort() == "high"
        sc.io.print_error.assert_called_once_with(
            "Invalid effort level 'medium'. Valid values for deepseek-v4-pro: "
            "low, high, max"
        )

    def test_baidu_deepseek_v4_pro_supports_effort(self):
        sc = _make_slash_commands()
        session = _make_session("deepseek-v4-pro")

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ):
            sc.cmd_effort(session, "high")

        assert session.siada_config.llm_config.get_reasoning_effort() == "high"
        sc.io.print_error.assert_not_called()

    def test_converter_sends_effort_without_token_budget(self):
        from siada.models.model_setting_converter import ModelSettingsConverter

        config = ModelRunConfig("deepseek-v4-flash")
        settings = ModelSettingsConverter.convert_model_settings(config)

        # Level-based control only — no thinking_tokens / thinking_budget.
        # Effort travels via extra_body["reasoning_effort"]: litellm drops a
        # top-level reasoning_effort for these openai-protocol models.
        assert settings.extra_body["reasoning_effort"] == "high"
        assert "thinking_budget" not in (settings.extra_args or {})


class TestCmdEffortQwen:
    """Qwen controls thinking intensity by level instead of a token count:
    extra_body={"enable_thinking": True, "reasoning_effort": "medium"}.
    Valid values: low/medium/xhigh, default "xhigh"."""

    def test_default_is_xhigh(self):
        sc = _make_slash_commands()
        session = _make_session("qwen3.7-plus")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: xhigh (model default: xhigh)"
        )

    def test_accepts_low_medium_xhigh(self):
        for level in ("low", "medium", "xhigh"):
            sc = _make_slash_commands()
            session = _make_session("qwen3.7-plus")

            with patch(
                "siada.config.config_loader.save_conf_field", return_value=True
            ):
                sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == level
            sc.io.print_error.assert_not_called()

    def test_rejects_high_and_max(self):
        for level in ("high", "max"):
            sc = _make_slash_commands()
            session = _make_session("qwen3.7-plus")

            sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == "xhigh"
            sc.io.print_error.assert_called_once_with(
                f"Invalid effort level '{level}'. Valid values for "
                "qwen3.7-plus: low, medium, xhigh"
            )

    def test_converter_sends_effort_without_token_budget(self):
        from siada.models.model_setting_converter import ModelSettingsConverter

        config = ModelRunConfig("qwen3.7-plus")
        settings = ModelSettingsConverter.convert_model_settings(config)

        # Level-based control replaces the token budget entirely; Qwen also
        # gets enable_thinking + preserve_thinking (DashScope preserved
        # thinking) alongside the effort.
        assert settings.extra_body == {
            "enable_thinking": True,
            "preserve_thinking": True,
            "reasoning_effort": "xhigh",
        }


class TestCompletionsEffort:
    def test_returns_base_levels(self):
        sc = _make_slash_commands()
        assert sc.get_completions("/effort") == ["high", "low", "medium"]


class TestCmdEffortGpt:
    """GPT-5-and-newer models share one reasoning_effort ladder:
    low/medium/high/max — identical for gpt-5.x and gpt-6-astra, regardless of
    the default each entry declares (gpt-6-astra declares "low", the gpt-5.6
    entries declare "max")."""

    def test_gpt6_astra_default_is_low(self):
        sc = _make_slash_commands()
        session = _make_session("gpt-6-astra")

        sc.cmd_effort(session, "")

        sc.io.print_info.assert_called_once_with(
            "Reasoning effort: low (model default: low)"
        )

    def test_gpt6_astra_accepts_low_medium_high_max(self):
        for level in ("low", "medium", "high", "max"):
            sc = _make_slash_commands()
            session = _make_session("gpt-6-astra")

            with patch(
                "siada.config.config_loader.save_conf_field", return_value=True
            ):
                sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == level
            sc.io.print_error.assert_not_called()

    def test_gpt6_astra_rejects_xhigh(self):
        # "xhigh" is not part of the GPT ladder (it is Claude's extra tier and
        # Qwen's strong tier); a model switch maps it to "max" instead.
        sc = _make_slash_commands()
        session = _make_session("gpt-6-astra")

        sc.cmd_effort(session, "xhigh")

        assert session.siada_config.llm_config.get_reasoning_effort() == "low"
        sc.io.print_error.assert_called_once_with(
            "Invalid effort level 'xhigh'. Valid values for gpt-6-astra: "
            "low, medium, high, max"
        )

    def test_gpt56_terra_accepts_the_same_four_levels(self):
        for level in ("low", "medium", "high", "max"):
            sc = _make_slash_commands()
            session = _make_session("gpt-5.6-terra")
            session.siada_config.llm_config.reasoning_effort = None

            with patch(
                "siada.config.config_loader.save_conf_field", return_value=True
            ):
                sc.cmd_effort(session, level)

            assert session.siada_config.llm_config.get_reasoning_effort() == level
            sc.io.print_error.assert_not_called()
