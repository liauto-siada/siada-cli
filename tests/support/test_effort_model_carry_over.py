"""
Tests for cross-model carry-over of /effort and /thinking settings.

/model keeps the user's session-level reasoning settings when switching
models: /thinking on|off is a model-agnostic boolean, and the effort intent
is mapped onto the levels the new model accepts — same-name levels pass
through (low→low, high→high, max→max), everything else maps to the nearest
strength neighbour with ties resolving to the STRONGER level (medium→high,
xhigh→max on domestic low/high/max models). The ORIGINAL intent is kept in
``user_reasoning_effort`` so chained switches never drift.
"""
from unittest.mock import MagicMock, patch

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.models.model_base_config import coerce_reasoning_effort
from siada.models.model_run_config import ModelRunConfig
from siada.support.slash_commands import SlashCommands


# ---------------------------------------------------------------------------
# coerce_reasoning_effort — the pure mapping function
# ---------------------------------------------------------------------------

class TestCoerceReasoningEffort:
    def test_same_name_levels_pass_through(self):
        # GLM-5.3+/Kimi K3+/DeepSeek: low/high/max
        for model in ("glm-5.3", "kimi-k3", "deepseek-v4-flash"):
            assert coerce_reasoning_effort(model, "low") == "low"
            assert coerce_reasoning_effort(model, "high") == "high"
            assert coerce_reasoning_effort(model, "max") == "max"
        # Claude accepts everything
        assert coerce_reasoning_effort("claude-sonnet-5", "xhigh") == "xhigh"
        assert coerce_reasoning_effort("claude-sonnet-5", "medium") == "medium"

    def test_domestic_models_map_ties_to_the_stronger_level(self):
        # medium is the default tier abroad, high is the default tier at
        # home; xhigh (stronger-than-high abroad) maps to max (stronger-than-
        # high at home).
        for model in ("glm-5.3", "kimi-k3", "deepseek-v4-flash"):
            assert coerce_reasoning_effort(model, "medium") == "high"
            assert coerce_reasoning_effort(model, "xhigh") == "max"

    def test_glm_52_has_no_low(self):
        assert coerce_reasoning_effort("glm-5.2", "low") == "high"
        assert coerce_reasoning_effort("glm-5.2", "medium") == "high"
        assert coerce_reasoning_effort("glm-5.2", "xhigh") == "max"

    def test_qwen_maps_high_and_max_to_xhigh(self):
        # Qwen's tiers are low/medium/xhigh — its strong tier is named xhigh.
        assert coerce_reasoning_effort("qwen3.7-max", "high") == "xhigh"
        assert coerce_reasoning_effort("qwen3.7-max", "max") == "xhigh"
        assert coerce_reasoning_effort("qwen3.7-max", "low") == "low"

    def test_generic_models_map_extended_levels_down(self):
        # Plain low/medium/high families (e.g. gemini-3.5-flash).
        assert coerce_reasoning_effort("gemini-3.5-flash", "xhigh") == "high"
        assert coerce_reasoning_effort("gemini-3.5-flash", "max") == "high"
        assert coerce_reasoning_effort("gemini-3.5-flash", "low") == "low"

    def test_model_default_stays_selectable(self):
        # gpt-5.6 ships default_reasoning_effort="max" — valid only via the
        # model_default escape hatch, so max passes through for it.
        assert coerce_reasoning_effort("gpt-5.6-terra", "max", "max") == "max"
        # xhigh is equidistant between high(2) and max(4) on gpt-5.6's
        # low/medium/high/max scale — the tie resolves to the stronger level.
        assert coerce_reasoning_effort("gpt-5.6-terra", "xhigh", "max") == "max"

    def test_unknown_effort_falls_back_to_model_default(self):
        assert coerce_reasoning_effort("claude-sonnet-5", "bogus", "xhigh") == "xhigh"
        assert coerce_reasoning_effort("claude-sonnet-5", "bogus") == "high"


# ---------------------------------------------------------------------------
# ModelRunConfig.carry_over_reasoning_settings
# ---------------------------------------------------------------------------

class TestCarryOverReasoningSettings:
    def test_effort_maps_and_intent_survives(self):
        old = ModelRunConfig("claude-sonnet-5")
        old.set_reasoning_effort("xhigh")
        new = ModelRunConfig("glm-5.3")

        carried = new.carry_over_reasoning_settings(old)

        assert carried == ("xhigh", "max")
        assert new.reasoning_effort == "max"
        assert new.user_reasoning_effort == "xhigh"

    def test_chained_switches_do_not_drift(self):
        # medium → GLM-5.3 (high) → Qwen must land on medium again, NOT on
        # the intermediate "high" (which would map to xhigh on Qwen). This is
        # why the original intent is kept separately from the mapped level.
        claude = ModelRunConfig("claude-sonnet-5")
        claude.set_reasoning_effort("medium")

        glm = ModelRunConfig("glm-5.3")
        glm.carry_over_reasoning_settings(claude)
        assert glm.reasoning_effort == "high"

        qwen = ModelRunConfig("qwen3.7-max")
        qwen.carry_over_reasoning_settings(glm)
        assert qwen.reasoning_effort == "medium"

    def test_domestic_to_foreign_maps_same_name(self):
        # GLM max → Claude is a same-name level, no remapping needed.
        old = ModelRunConfig("glm-5.3")
        old.set_reasoning_effort("max")
        new = ModelRunConfig("claude-sonnet-5")

        carried = new.carry_over_reasoning_settings(old)

        assert carried == ("max", "max")
        assert new.reasoning_effort == "max"

    def test_thinking_off_is_carried_and_clears_budget(self):
        old = ModelRunConfig("glm-5.2")
        old.enable_thinking = False
        new = ModelRunConfig("claude-sonnet-5")

        # No user effort set — nothing to report, but thinking carries over.
        assert new.carry_over_reasoning_settings(old) is None
        assert new.enable_thinking is False
        assert new.thinking_tokens is None

    def test_thinking_on_is_carried(self):
        old = ModelRunConfig("gemini-3.5-flash")
        old.enable_thinking = True
        new = ModelRunConfig("claude-sonnet-5")

        new.carry_over_reasoning_settings(old)

        assert new.enable_thinking is True

    def test_model_defaults_are_not_carried(self):
        # The user never set an effort; every model keeps its own default.
        old = ModelRunConfig("claude-sonnet-5")  # default high
        assert old.reasoning_effort == "high"

        new = ModelRunConfig("glm-5.3")  # default max

        assert new.carry_over_reasoning_settings(old) is None
        assert new.reasoning_effort == new.default_reasoning_effort
        assert new.user_reasoning_effort is None

    def test_unsupported_model_keeps_intent_without_setting_effort(self):
        # glm-5.2 does not support the reasoning_effort param at all
        # (thinking_tokens only). The intent is preserved for a later switch
        # to a supporting model, but no effort is set on this model.
        old = ModelRunConfig("claude-sonnet-5")
        old.set_reasoning_effort("high")
        new = ModelRunConfig("glm-5.2")

        assert new.carry_over_reasoning_settings(old) is None
        assert new.user_reasoning_effort == "high"
        assert new.reasoning_effort == new.default_reasoning_effort

    def test_intent_restored_when_switching_back_to_supporting_model(self):
        # Chain: claude high → glm-5.2 (no effort param) → kimi k3: the
        # intent set on claude survives the glm-5.2 hop.
        claude = ModelRunConfig("claude-sonnet-5")
        claude.set_reasoning_effort("high")

        glm52 = ModelRunConfig("glm-5.2")
        glm52.carry_over_reasoning_settings(claude)

        kimi = ModelRunConfig("kimi-k3")
        carried = kimi.carry_over_reasoning_settings(glm52)

        assert carried == ("high", "high")
        assert kimi.reasoning_effort == "high"

    def test_legacy_config_without_user_marker_is_detected(self):
        # Configs built before user_reasoning_effort existed: an effort that
        # differs from the model default is treated as user-set.
        old = ModelRunConfig("claude-sonnet-5")  # default xhigh
        old.reasoning_effort = "low"  # set without set_reasoning_effort()

        new = ModelRunConfig("glm-5.3")
        carried = new.carry_over_reasoning_settings(old)

        assert carried == ("low", "low")

    def test_none_old_config_is_a_noop(self):
        new = ModelRunConfig("claude-sonnet-5")
        assert new.carry_over_reasoning_settings(None) is None


# ---------------------------------------------------------------------------
# cmd_model integration — settings survive the switch
# ---------------------------------------------------------------------------

def _make_slash_commands() -> SlashCommands:
    io = MagicMock()
    io.acp_adapter = None
    return SlashCommands(io=io)


def _make_session(model: str) -> MagicMock:
    session = MagicMock()
    session.siada_config.llm_config = ModelRunConfig(model)
    # Skip api-messages tracking persistence during the switch.
    session.state.openai_session.session_folder = None
    return session


class TestCmdModelCarryOver:
    def test_cmd_model_carries_and_maps_effort(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.set_reasoning_effort("xhigh")

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            event = sc.cmd_model(session, "glm-5.3")

        assert event is not None and event.kwargs["model"] == "glm-5.3"
        cfg = session.siada_config.llm_config
        assert cfg.model_name == "glm-5.3"
        assert cfg.reasoning_effort == "max"
        assert cfg.user_reasoning_effort == "xhigh"
        # The mapping is surfaced to the user.
        printed = " ".join(str(c) for c in sc.io.print_info.call_args_list)
        assert "xhigh → max" in printed

    def test_cmd_model_carries_thinking_off(self):
        sc = _make_slash_commands()
        session = _make_session("glm-5.2")
        session.siada_config.llm_config.enable_thinking = False

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_model(session, "claude-sonnet-5")

        cfg = session.siada_config.llm_config
        assert cfg.enable_thinking is False
        assert cfg.thinking_tokens is None
        printed = " ".join(str(c) for c in sc.io.print_info.call_args_list)
        assert "Thinking stays disabled" in printed

    def test_cmd_model_without_user_settings_uses_new_model_defaults(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")  # defaults only

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_model(session, "glm-5.3")

        cfg = session.siada_config.llm_config
        assert cfg.reasoning_effort == cfg.default_reasoning_effort
        assert cfg.enable_thinking is None

    def test_cmd_model_pushes_reasoning_state_to_ui(self):
        # Even without user-set effort, the switch must push the NEW model's
        # effort to the UI — otherwise the status bar keeps showing the
        # previous model's effort label next to the new model name.
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")  # default effort: high
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_model(session, "glm-5.3")  # default effort: max

        sent = [c[0][0] for c in adapter.transport.send_sync.call_args_list]
        assert any(
            m.method == "ui/reasoningEffortChanged" and m.params["effort"] == "max"
            for m in sent
        )
        # The thinking switch state is synced too (None = model default).
        assert any(m.method == "ui/thinkingChanged" for m in sent)

    def test_cmd_model_pushes_thinking_off_to_ui(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = False
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_model(session, "glm-5.3")

        sent = [c[0][0] for c in adapter.transport.send_sync.call_args_list]
        assert any(
            m.method == "ui/thinkingChanged" and m.params["thinking"] is False
            for m in sent
        )


# ---------------------------------------------------------------------------
# cmd_effort / set_reasoning_effort record the user intent
# ---------------------------------------------------------------------------

class TestEffortIntentRecording:
    def test_set_reasoning_effort_records_intent(self):
        cfg = ModelRunConfig("claude-sonnet-5")
        cfg.set_reasoning_effort("xhigh")
        assert cfg.user_reasoning_effort == "xhigh"

    def test_cmd_effort_records_intent(self):
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_effort(session, "low")

        cfg = session.siada_config.llm_config
        assert cfg.reasoning_effort == "low"
        assert cfg.user_reasoning_effort == "low"


# ---------------------------------------------------------------------------
# Controller rebuild — the /model SwitchEvent handler rebuilds the llm_config
# once more AFTER cmd_model; that rebuild must not drop the carried settings.
# ---------------------------------------------------------------------------

class TestControllerRebuildKeepsSettings:
    def _make_controller(self, siada_config):
        from siada.entrypoint.interaction.controller import Controller

        controller = Controller.__new__(Controller)
        controller.config = siada_config
        return controller

    def test_full_switch_flow_keeps_thinking_off(self):
        # Real flow: /thinking off → /model (cmd_model carries the switch onto
        # the new session llm_config) → the Controller's SwitchEvent handler
        # rebuilds the llm_config once more. Before the fix, this rebuild
        # silently re-enabled thinking (fresh ModelRunConfig, enable_thinking
        # back to None = model default).
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.enable_thinking = False

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            event = sc.cmd_model(session, "glm-5.3")
        assert event is not None
        # cmd_model already swapped the (shared) session llm_config.
        assert session.siada_config.llm_config.enable_thinking is False

        # Controller SwitchEvent handling rebuilds it a second time. The
        # controller's config IS the session's siada_config (same RunningConfig
        # object), exactly as in production.
        controller = self._make_controller(session.siada_config)
        controller._update_llm_config_for_model(event.kwargs["model"])

        cfg = session.siada_config.llm_config
        assert cfg is controller.config.llm_config
        assert cfg.model_name == "glm-5.3"
        assert cfg.enable_thinking is False
        assert cfg.thinking_tokens is None

    def test_full_switch_flow_keeps_mapped_effort(self):
        # /effort xhigh on Claude → /model to GLM-5.3: the controller rebuild
        # must keep mapping from the user's ORIGINAL intent (xhigh → max).
        sc = _make_slash_commands()
        session = _make_session("claude-sonnet-5")
        session.siada_config.llm_config.set_reasoning_effort("xhigh")

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            event = sc.cmd_model(session, "glm-5.3")
        assert event is not None
        assert session.siada_config.llm_config.reasoning_effort == "max"

        controller = self._make_controller(session.siada_config)
        controller._update_llm_config_for_model(event.kwargs["model"])

        cfg = session.siada_config.llm_config
        assert cfg.reasoning_effort == "max"
        assert cfg.user_reasoning_effort == "xhigh"

    def test_rebuild_without_user_settings_uses_new_model_defaults(self):
        from types import SimpleNamespace

        controller = self._make_controller(
            SimpleNamespace(llm_config=ModelRunConfig("claude-sonnet-5"))
        )
        controller._update_llm_config_for_model("glm-5.3")

        cfg = controller.config.llm_config
        assert cfg.model_name == "glm-5.3"
        assert cfg.reasoning_effort == cfg.default_reasoning_effort
        assert cfg.enable_thinking is None
