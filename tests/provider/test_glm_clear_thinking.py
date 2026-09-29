"""Tests for GLM clear_thinking parameter propagation.

Verifies that when GLM models have reasoning/thinking enabled, the
``clear_thinking=False`` parameter is correctly nested inside a ``thinking``
dict in ``ModelSettings.extra_body``, and that the default provider forwards
``extra_body`` as-is to litellm's ``extra_body`` argument (merged into the
request body).

The GLM API expects:
    extra_body = {"thinking": {"type": "enabled", "clear_thinking": False}}
"""

from __future__ import annotations

import copy

from agents import ModelSettings

from siada.models.model_base_config import is_glm_model
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_config(model_name: str, *, thinking_tokens=None, reasoning_effort=None) -> ModelRunConfig:
    """Build a ModelRunConfig for the given model with optional reasoning settings."""
    config = ModelRunConfig(model_name)
    if thinking_tokens is not None:
        config.set_thinking_tokens(thinking_tokens)
    else:
        # Ensure thinking is off by default for this helper
        config.thinking_tokens = None
    if reasoning_effort is not None:
        config.set_reasoning_effort(reasoning_effort)
    else:
        config.reasoning_effort = None
    return config


# ---------------------------------------------------------------------------
# Converter tests
# ---------------------------------------------------------------------------

class TestConverterSetsClearThinkingForGLM:
    """ModelSettingsConverter should add a "thinking" dict with clear_thinking=False
    to extra_body for GLM models when reasoning is enabled."""

    def test_glm_with_thinking_tokens(self):
        config = _make_run_config("glm-5.2", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert settings.extra_body is not None
        assert "thinking" in settings.extra_body
        assert settings.extra_body["thinking"]["clear_thinking"] is False
        assert settings.extra_body["thinking"]["type"] == "enabled"

    def test_glm_53_with_thinking_tokens(self):
        config = _make_run_config("glm-5.3", thinking_tokens="1k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert settings.extra_body["thinking"]["clear_thinking"] is False

    def test_glm_default_thinking_tokens(self):
        """GLM models have default_thinking_tokens=1024; even without explicit
        set_thinking_tokens, reasoning should be on and clear_thinking set."""
        config = ModelRunConfig("glm-5.2")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert settings.extra_body["thinking"]["clear_thinking"] is False

    def test_glm_no_top_level_clear_thinking(self):
        """clear_thinking must NOT be a top-level key in extra_body — it must
        be nested inside the 'thinking' dict."""
        config = _make_run_config("glm-5.2", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert "clear_thinking" not in settings.extra_body

    def test_glm_no_reasoning_dict(self):
        """GLM should NOT have a 'reasoning' dict in extra_body — it uses
        a 'thinking' dict instead."""
        config = _make_run_config("glm-5.2", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        assert "reasoning" not in settings.extra_body


class TestConverterNoClearThinkingWhenReasoningOff:
    """clear_thinking should NOT be set when reasoning is disabled for GLM."""

    def test_glm_without_thinking_tokens(self):
        config = _make_run_config("glm-5.2", thinking_tokens="0")
        settings = ModelSettingsConverter.convert_model_settings(config)
        # extra_body may be empty or not contain thinking
        if settings.extra_body:
            assert "thinking" not in settings.extra_body
            assert "clear_thinking" not in settings.extra_body


class TestConverterNoClearThinkingForNonGLM:
    """clear_thinking should NOT be set for non-GLM models even with reasoning."""

    def test_deepseek_with_thinking_tokens(self):
        config = _make_run_config("deepseek-v4-pro", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        # Non-GLM uses the outer enable_thinking switch (no GLM "thinking"
        # dict); the thinking_tokens value itself never emits a budget —
        # effort is the only strength control.
        assert settings.extra_body is not None
        assert "thinking" not in settings.extra_body
        assert settings.extra_body.get("enable_thinking") is True
        assert settings.extra_args is None  # no thinking_budget

    def test_kimi_with_thinking_tokens(self):
        config = _make_run_config("kimi-k3", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        if settings.extra_body:
            assert "thinking" not in settings.extra_body

    def test_claude_with_thinking_tokens(self):
        # Must use a Claude name present in the built-in MODEL_SETTING registry:
        # an unknown name silently falls back to DEFAULT_MODEL_NAME, which would
        # make this assertion test the wrong model's settings instead.
        config = _make_run_config("claude-sonnet-4-6", thinking_tokens="2k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        # Claude uses "thinking" dict but without clear_thinking
        if settings.extra_body and "thinking" in settings.extra_body:
            assert "clear_thinking" not in settings.extra_body["thinking"]


# ---------------------------------------------------------------------------
# is_glm_model helper tests
# ---------------------------------------------------------------------------

class TestIsGlmModel:
    def test_glm_names(self):
        assert is_glm_model("glm-5.2") is True
        assert is_glm_model("glm-5.3") is True

    def test_non_glm(self):
        assert is_glm_model("deepseek-v4-pro") is False
        assert is_glm_model("claude-sonnet-4.5") is False
        assert is_glm_model("kimi-k2.6") is False


# ---------------------------------------------------------------------------
# DefaultProvider path: extra_body forwarded as-is to litellm
# ---------------------------------------------------------------------------

class TestDefaultProviderClearThinkingForwarded:
    """Simulate the LitellmModel._fetch_response extra_body handling to ensure
    the thinking dict (with clear_thinking) is preserved inside extra_body."""

    def _simulate_litellm_extra_body(self, model_settings: ModelSettings) -> dict | None:
        """Reproduce the extra_body forwarding logic from LitellmModel._fetch_response."""
        if model_settings.extra_body is not None:
            extra_body = copy.copy(model_settings.extra_body)
            # For GLM, reasoning_effort is None so the pop branch is skipped
            if isinstance(extra_body, dict) and extra_body:
                return extra_body
        return None

    def test_glm_thinking_dict_in_extra_body(self):
        config = _make_run_config("glm-5.2", thinking_tokens="1k")
        settings = ModelSettingsConverter.convert_model_settings(config)
        forwarded = self._simulate_litellm_extra_body(settings)

        assert forwarded is not None
        assert "thinking" in forwarded
        assert forwarded["thinking"]["clear_thinking"] is False
        assert forwarded["thinking"]["type"] == "enabled"
