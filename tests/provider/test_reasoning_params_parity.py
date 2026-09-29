"""Parity tests for the reasoning-params refactor.

The refactor (see ModelSettingsConverter docstring) moved ALL
reasoning-parameter translation into ``ModelSettingsConverter`` and removed
the post-processing that used to live in the provider layer, replacing the
OpenRouter-style ``extra_body.reasoning = {effort, max_tokens, adaptive}``
intermediate format with litellm-native params.

Correctness contract, verified by these tests:

1. **Responses path — byte-identical.** ``ResponsesModel._build_request_params``
   output for GPT-6 must equal the pre-refactor golden snapshots
   (``reasoning_parity_golden_responses.json``).

2. **default path — unchanged for claude/gemini.** The default provider
   (SDK LitellmModel) must behave identically for Claude and Gemini families
   (compared against the frozen pre-refactor snapshot
   ``reasoning_parity_default_before_refactor.json``).

3. **default path — intentional new behavior elsewhere.** For
   deepseek/qwen/glm/kimi the OpenRouter-style ``extra_body.reasoning`` dict
   is gone; native litellm params are used instead (asserted explicitly).

Regenerating the golden files (from the repo root):

    PYTHONPATH=. poetry run python tests/provider/_gen_reasoning_parity_golden.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest import mock as unittest_mock

import litellm
import pytest

from reasoning_parity_harness import (
    MODELS,
    RESPONSES_ONLY_MODELS,
    VARIANTS,
    build_settings,
    capture_default,
    capture_responses,
    is_unreachable,
    make_config,
)
from siada.models.model_base_config import is_claude_4_6_or_newer
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter

HERE = Path(__file__).parent


def _load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


GOLDEN_RESPONSES = _load("reasoning_parity_golden_responses.json")
DEFAULT_BEFORE_REFACTOR = _load("reasoning_parity_default_before_refactor.json")


def _matrix() -> list[tuple[str, str]]:
    return [(m, v) for m in MODELS for v in VARIANTS if not is_unreachable(m, v)]




# ---------------------------------------------------------------------------
# 1. Responses path: byte-identical to the pre-refactor golden snapshots
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model,variant", _matrix())
def test_responses_path_matches_golden(model: str, variant: str):
    if model not in RESPONSES_ONLY_MODELS:
        pytest.skip("non-responses-only models never take the ResponsesModel path")
    settings = build_settings(model, variant)
    actual = capture_responses(model, settings)
    expected = GOLDEN_RESPONSES[f"{model}|{variant}"]
    assert actual == expected


# ---------------------------------------------------------------------------
# 2. default path: unchanged for claude / gemini families
# ---------------------------------------------------------------------------

def _is_claude_or_gemini(model: str) -> bool:
    lower = model.lower()
    return "claude" in lower or "gemini" in lower


@pytest.mark.parametrize("model,variant", _matrix())
def test_default_path_unchanged_for_claude_and_gemini(model: str, variant: str):
    if model in RESPONSES_ONLY_MODELS or not _is_claude_or_gemini(model):
        pytest.skip("only claude/gemini families are covered here")
    settings = build_settings(model, variant)
    actual = asyncio.run(capture_default(model, settings))
    expected = DEFAULT_BEFORE_REFACTOR[f"{model}|{variant}"]
    # Claude 4.6+ unconditional adaptive thinking (intentional post-refactor
    # change): these variants deliberately diverge from the frozen
    # pre-refactor snapshots — 4.6+ now ALWAYS sends adaptive thinking (or
    # {"type": "disabled"} for an explicit disable), where the old code gated
    # it on thinking_tokens / model defaults.
    if is_claude_4_6_or_newer(model) and variant in (
        "no_reasoning", "effort_low", "effort_max", "thinking_off", "thinking_off_tokens",
    ):
        expected = dict(expected)
        if variant in ("no_reasoning", "effort_low", "effort_max"):
            expected["thinking"] = {"type": "adaptive", "display": "summarized"}
            if variant == "no_reasoning":
                expected["reasoning_effort"] = "high"
        else:
            # Explicit disable: {"type": "disabled"} and no default effort —
            # a top-level reasoning_effort would override the disable.
            expected["thinking"] = {"type": "disabled"}
            expected["reasoning_effort"] = None
    assert actual == expected, (
        f"default path diverged for {model}|{variant}:\n"
        f"  expected: {json.dumps(_reasoning_projection(expected), sort_keys=True)}\n"
        f"  actual:   {json.dumps(_reasoning_projection(actual), sort_keys=True)}"
    )


# ---------------------------------------------------------------------------
# 3. default path: intentional new behavior (OpenRouter format removed)
# ---------------------------------------------------------------------------
# The default provider's LitellmModel subclass (KeepExtraBodyReasoningEffortMixin,
# siada/provider/default/effort_channel.py) does NOT hoist
# extra_body["reasoning_effort"] into a top-level kwarg — the SDK's hoist
# would get the kwarg silently DROPPED by litellm's global drop_params=True
# for openai-protocol models (glm/deepseek/qwen/kimi). The value stays in
# extra_body and is merged verbatim into the HTTP request body (verified by
# request capture; see tests below). Claude/Gemini's ModelSettings.reasoning
# is still hoisted — those providers natively accept the top-level kwarg.

def _default_projection(model: str, variant: str) -> dict:
    settings = build_settings(model, variant)
    kwargs = asyncio.run(capture_default(model, settings))
    return _reasoning_projection(kwargs)


def test_default_deepseek_effort_only_no_switch():
    # deepseek effort-only: no outer enable_thinking — the gateway defaults
    # it on its own when reasoning params are present. The effort stays in
    # extra_body: the SDK subclass does not hoist it, because a top-level
    # kwarg would be dropped by litellm's drop_params for openai-protocol
    # models.
    p = _default_projection("deepseek-v4-flash", "effort_low")
    assert p == {
        "reasoning_effort": None,  # SDK always passes the kwarg; None is ignored
        "extra_body": {"reasoning_effort": "low"},
        "temperature": None,
    }


def test_default_kimi_effort_has_no_switch():
    # Non-qwen models with effort only: no enable_thinking; low/high ride in
    # extra_body (survives drop_params; a hoisted top-level kwarg would not).
    p = _default_projection("kimi-k3", "effort_low")
    assert p == {
        "reasoning_effort": None,
        "extra_body": {"reasoning_effort": "low"},
        "temperature": None,
    }

    p = _default_projection("kimi-k3", "effort_max")
    # The converter always emits the effort (even "max"); the default path
    # keeps it.
    assert p == {
        "reasoning_effort": None,
        "extra_body": {"reasoning_effort": "max"},
        "temperature": None,
    }


def test_default_deepseek_tokens_is_enable_only():
    # thinking_tokens no longer emits a budget — it only carries the
    # enable_thinking signal; effort is the sole strength control.
    p = _default_projection("deepseek-v4-flash", "tokens_2048")
    assert p["extra_body"] == {"enable_thinking": True}
    assert "thinking_budget" not in p


def test_default_deepseek_thinking_off():
    # The GENERIC disable form for openai-protocol models (deepseek/kimi) is
    # the thinking dict.
    p = _default_projection("deepseek-v4-flash", "thinking_off")
    assert p["extra_body"] == {"thinking": {"type": "disabled"}}


def test_default_qwen_effort_preserves_thinking():
    # Qwen preserved thinking: extra_body carries enable_thinking +
    # preserve_thinking (DashScope contract); the effort also stays in
    # extra_body (drop_params-safe channel for openai-protocol models).
    p = _default_projection("qwen3.8-max", "effort_low")
    assert p["extra_body"] == {
        "enable_thinking": True,
        "preserve_thinking": True,
        "reasoning_effort": "low",
    }


def test_default_qwen_tokens_preserves_thinking():
    p = _default_projection("qwen3.8-max", "tokens_2048")
    assert p["extra_body"] == {"enable_thinking": True, "preserve_thinking": True}
    assert "thinking_budget" not in p


def test_default_kimi_tokens_temperature_none():
    # When reasoning is on, temperature is always left at None (not sent) —
    # the Kimi temperature=1.0 rule was removed. And a configured
    # thinking_tokens only raises enable_thinking, never a budget.
    p = _default_projection("kimi-k3", "tokens_2048")
    assert p["extra_body"] == {"enable_thinking": True}
    assert "thinking_budget" not in p
    assert p["temperature"] is None


def test_default_glm_52_thinking_dict_unchanged():
    p = _default_projection("glm-5.2", "default")
    assert p["extra_body"] == {"thinking": {"type": "enabled", "clear_thinking": False}}


def test_default_glm_53_effort_via_extra_body():
    p = _default_projection("glm-5.3", "effort_low")
    assert p["extra_body"]["reasoning_effort"] == "low"


def test_default_glm_53_max_effort_omitted():
    p = _default_projection("glm-5.3", "effort_max")
    # "max" effort is omitted (gateway default), but the preserved-thinking
    # dict is still sent.
    assert p["reasoning_effort"] is None
    assert p["extra_body"] == {"thinking": {"type": "enabled", "clear_thinking": False}}

def _reasoning_projection(kwargs: dict) -> dict:
    """The reasoning-related subset of captured acompletion kwargs."""
    keys = (
        "reasoning_effort", "extra_body", "enable_thinking", "thinking_budget",
        "thinking", "output_config", "temperature",
    )
    return {k: v for k, v in kwargs.items() if k in keys}


# ---------------------------------------------------------------------------
# 4. Explicit rules: effort-only / qwen preserved thinking / glm
# ---------------------------------------------------------------------------

def test_effort_only_needs_no_switch():
    # openai-protocol models: no outer enable_thinking — the gateway
    # defaults it on its own when reasoning params are present.
    s = build_settings("deepseek-v4-flash", "effort_low")
    assert s.extra_body == {"reasoning_effort": "low"}
    assert s.extra_args is None


def test_adaptive_budget_not_forwarded():
    # A -1 budget (Claude's adaptive marker) is Claude-exclusive; on the
    # other families it just means "thinking on, no fixed budget" — no
    # adaptive thinking param, no thinking_budget, and (since the gateway
    # defaults enable_thinking) no outer switch either.
    s = build_settings("deepseek-v4-flash", "tokens_neg1")
    assert s.extra_body is None
    assert s.extra_args is None


def test_claude_46_adaptive_thinking():
    # Adaptive thinking is Claude 4.6+ exclusive: the model default (DT=-1)
    # activates it. (claude-sonnet-4-6 also has DRE=high, so output_config
    # is present alongside.)
    s = build_settings("claude-sonnet-4-6", "default")
    assert s.extra_args == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "high"},
    }


def test_claude_5_adaptive_thinking_with_explicit_budget():
    # On Claude 5 (DT=-1), an explicit budget still yields adaptive mode:
    # the model default takes precedence (pre-existing behavior).
    s = build_settings("claude-sonnet-5", "tokens_2048")
    assert s.extra_args == {"thinking": {"type": "adaptive", "display": "summarized"}}


def test_pre_46_claude_never_adaptive():
    # Claude 4.5 does not support adaptive thinking; an explicit -1 budget
    # must not produce an invalid budget_tokens=-1 request either.
    cfg = make_config("claude-sonnet-5", "tokens_neg1")
    cfg.model_name = "claude-sonnet-4-5"  # simulate a pre-4.6 Claude
    cfg.default_thinking_tokens = None
    from siada.models.model_setting_converter import ModelSettingsConverter

    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None  # no adaptive, no invalid budget
    # effort default still applies
    assert s.reasoning is not None and s.reasoning.effort == "high"


def test_pre_46_claude_prefixed_variant_never_adaptive():
    # Provider-prefixed pre-4.6 variants (aws-, anthropic/, bedrock/) are
    # detected by name and never get adaptive thinking.
    cfg = make_config("claude-sonnet-5", "tokens_neg1")
    cfg.model_name = "aws-claude-sonnet-4-5"
    cfg.default_thinking_tokens = None
    from siada.models.model_setting_converter import ModelSettingsConverter

    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None


def test_claude_46_prefixed_variant_adaptive():
    cfg = make_config("claude-sonnet-5", "tokens_neg1")
    cfg.model_name = "anthropic/claude-sonnet-4-6"
    cfg.default_thinking_tokens = -1
    from siada.models.model_setting_converter import ModelSettingsConverter

    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args == {"thinking": {"type": "adaptive", "display": "summarized"}}


def test_claude_46_unconditional_adaptive_thinking():
    # 4.6+ ALWAYS thinks adaptively — no thinking_tokens / model-default
    # gating. Even a fully-cleared config (no_reasoning) keeps adaptive on,
    # with the default effort=high via ModelSettings.reasoning.
    s = build_settings("claude-sonnet-4-6", "no_reasoning")
    assert s.extra_args == {"thinking": {"type": "adaptive", "display": "summarized"}}
    assert s.reasoning is not None and s.reasoning.effort == "high"

    # effort-only: adaptive + output_config, no default reasoning item.
    s = build_settings("claude-sonnet-4-6", "effort_low")
    assert s.extra_args == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "low"},
    }
    assert s.reasoning is None


def test_claude_46_explicit_disable_sends_disabled():
    # --no-thinking / enable_thinking: false on a 4.6+ Claude:
    # {"type": "disabled"} — omitting the param would fall back to the
    # model default (thinking ON). No default effort either: a top-level
    # reasoning_effort would override the disable in litellm's anthropic
    # transformation.
    s = build_settings("claude-sonnet-4-6", "thinking_off")
    assert s.extra_args == {"thinking": {"type": "disabled"}}
    assert s.reasoning is None

    # Disable wins over a concurrently configured thinking_tokens (the
    # token signal no longer gates anything on 4.6+).
    s = build_settings("claude-sonnet-4-6", "thinking_off_tokens")
    assert s.extra_args == {"thinking": {"type": "disabled"}}
    assert s.reasoning is None


def test_claude_46_disable_beats_effort():
    # An explicit disable is the ABSOLUTE off-switch — it wins over any
    # effort (including the model's default_reasoning_effort, which would
    # otherwise keep the disable from ever taking effect on models that
    # ship a DRE). No output_config either: an effort is meaningless with
    # reasoning off.
    cfg = make_config("claude-sonnet-5", "thinking_off")
    cfg.set_reasoning_effort("low")
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args == {"thinking": {"type": "disabled"}}
    assert s.reasoning is None


def test_pre_46_claude_disable_sends_nothing():
    # Pre-4.6 has no thinking param to disable — its default is thinking OFF.
    cfg = make_config("claude-sonnet-5", "thinking_off")
    cfg.model_name = "claude-sonnet-4-5"
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None
    assert s.reasoning is None


def test_pre_46_claude_explicit_effort_not_forwarded():
    # output_config (effort) is a 4.6+-ONLY capability — a pre-4.6 Claude
    # never sends it (the old models don't support the effort param).
    cfg = make_config("claude-sonnet-5", "no_reasoning")
    cfg.model_name = "claude-sonnet-4-5"
    cfg.set_reasoning_effort("low")
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None  # no thinking, no output_config
    assert s.reasoning is None  # no default either (effort configured)


def test_glm_adaptive_budget_falls_back_to_enabled():
    # GLM-5.2 with a -1 budget: "adaptive" is not a valid GLM type —
    # thinking is enabled with preserved reasoning instead.
    s = build_settings("glm-5.2", "tokens_neg1")
    assert s.extra_body == {"thinking": {"type": "enabled", "clear_thinking": False}}


def test_gpt5_adaptive_budget_not_forwarded():
    # GPT-5.x (Responses path): a -1 budget is not forwarded — neither as
    # "adaptive" (Claude-exclusive) nor as an invalid max_tokens=-1.
    s = build_settings("gpt-6-luna", "tokens_neg1")
    assert s.extra_body is None or "adaptive" not in (s.extra_body or {})
    if s.extra_body and "reasoning" in s.extra_body:
        assert "max_tokens" not in s.extra_body["reasoning"]


def test_kimi_effort_only_no_switch():
    s = build_settings("kimi-k3", "effort_low")
    assert s.extra_body == {"reasoning_effort": "low"}
    assert s.extra_args is None
    # temperature stays at its default None — no family-specific overrides.
    assert s.temperature is None


def test_effort_only_has_no_switch():
    s = build_settings("kimi-k3", "effort_low")
    assert s.extra_body == {"reasoning_effort": "low"}
    assert s.extra_args is None


def test_qwen_preserved_thinking_structure():
    # Qwen: extra_body={"enable_thinking": True, "preserve_thinking": True}
    # (+ reasoning_effort when set) — the Qwen counterpart of GLM-5.2's
    # clear_thinking=False.
    s = build_settings("qwen3.8-max", "effort_low")
    assert s.extra_body == {
        "enable_thinking": True,
        "preserve_thinking": True,
        "reasoning_effort": "low",
    }
    # enable_thinking never travels as a top-level kwarg (single channel)
    assert s.extra_args is None


def test_qwen_tokens_gets_preserve_thinking():
    # Qwen: a configured thinking_tokens raises enable+preserve thinking
    # (DashScope contract) but never emits a budget.
    s = build_settings("qwen3.8-max", "tokens_2048")
    assert s.extra_body == {"enable_thinking": True, "preserve_thinking": True}
    assert s.extra_args is None  # no thinking_budget — budgets are never emitted


def test_qwen_thinking_off_no_preserve():
    s = build_settings("qwen3.8-max", "thinking_off")
    assert s.extra_body == {"enable_thinking": False}


def test_glm_52_keeps_thinking_dict_no_outer_switch():
    # GLM preserved thinking stays in the thinking dict; no outer
    # enable_thinking even for GLM-5.2.
    s = build_settings("glm-5.2", "default")
    assert s.extra_body == {"thinking": {"type": "enabled", "clear_thinking": False}}
    assert "enable_thinking" not in s.extra_body
    assert s.extra_args is None


def test_glm_52_also_sends_reasoning_effort():
    # GLM (ALL versions) transmits effort via reasoning_effort, with "max"
    # omitted (the Zhipu gateway default) — not just GLM-5.3+.
    s = build_settings("glm-5.2", "effort_low")
    assert s.extra_body == {
        "thinking": {"type": "enabled", "clear_thinking": False},
        "reasoning_effort": "low",
    }

    # "max" is omitted for every GLM version.
    cfg = make_config("glm-5.2", "no_reasoning")
    cfg.set_reasoning_effort("max")
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_body == {"thinking": {"type": "enabled", "clear_thinking": False}}


def test_glm_53_also_gets_preserved_thinking():
    # GLM-5.3 sends the same preserved-thinking dict as GLM-5.2, plus its
    # reasoning_effort strength control.
    s = build_settings("glm-5.3", "effort_low")
    assert s.extra_body == {
        "thinking": {"type": "enabled", "clear_thinking": False},
        "reasoning_effort": "low",
    }


def test_glm_53_default_effort_omitted_but_thinking_kept():
    # glm-5.3 defaults to effort="max", which is omitted (Zhipu
    # rejects an explicit "max"), but preserved thinking is always on.
    s = build_settings("glm-5.3", "default")
    assert s.extra_body == {"thinking": {"type": "enabled", "clear_thinking": False}}


def test_tokens_act_as_enable_thinking_signal_only():
    # thinking_tokens > 0 never emits a budget; it only raises the
    # enable_thinking switch (a request-body field, hence extra_body) —
    # same final HTTP switch as before, just without the budget.
    s = build_settings("deepseek-v4-flash", "tokens_2048")
    assert s.extra_body == {"enable_thinking": True}
    assert s.extra_args is None


def test_disable_thinking_generic_dict_form():
    # The generic disable for deepseek/kimi/gpt-4.x is the thinking dict;
    # Qwen keeps the DashScope enable_thinking switch.
    s = build_settings("deepseek-v4-flash", "thinking_off")
    assert s.extra_body == {"thinking": {"type": "disabled"}}
    assert s.extra_args is None

    s = build_settings("kimi-k3", "thinking_off")
    assert s.extra_body == {"thinking": {"type": "disabled"}}

    s = build_settings("qwen3.8-max", "thinking_off")
    assert s.extra_body == {"enable_thinking": False}


def test_glm_53_disable_degrades_to_min_effort():
    # GLM-5.3 CANNOT turn thinking off — the gateway rejects
    # {"type": "disabled"} with "该模型始终思考，不支持关闭思考；请使用
    # low、high 或 max" (verified against the test gateway). The disable
    # therefore degrades to the minimum effort per that guidance.
    for variant in ("thinking_off", "thinking_off_tokens"):
        s = build_settings("glm-5.3", variant)
        assert s.extra_body == {
            "thinking": {"type": "enabled", "clear_thinking": False},
            "reasoning_effort": "low",
        }


def test_glm_52_disable_sends_disabled_dict():
    # GLM-5.2: the gateway currently ignores {"type": "disabled"} (keeps
    # thinking) but accepts it without error — send it anyway for forward
    # compatibility.
    s = build_settings("glm-5.2", "thinking_off")
    assert s.extra_body == {"thinking": {"type": "disabled"}}


# ---------------------------------------------------------------------------
# 5. Budgets are never emitted — effort is the only strength control
# ---------------------------------------------------------------------------

def test_budget_never_emitted_but_family_switches_kept():
    # Token budgets are never emitted (effort is the only strength control);
    # the family switches still apply (qwen preserved thinking), and a
    # configured thinking_tokens still carries the enable_thinking signal.
    s = build_settings("deepseek-v4-flash", "effort_low_tokens")
    # thinking_tokens>0 raises enable_thinking (the "thinking on" signal)
    assert s.extra_body == {"enable_thinking": True, "reasoning_effort": "low"}
    assert s.extra_args is None  # no thinking_budget

    s = build_settings("qwen3.8-max", "effort_low_tokens")
    assert s.extra_body == {
        "enable_thinking": True,
        "preserve_thinking": True,
        "reasoning_effort": "low",
    }
    assert s.extra_args is None


def test_user_budget_config_has_no_wire_effect():
    # A user-configured thinking_tokens (here on a model whose
    # default_reasoning_effort is "high") produces NO budget parameter — the
    # effort still flows (model default), and the enable_thinking signal is
    # the only trace of the thinking_tokens configuration.
    cfg = ModelRunConfig("deepseek-v4-flash")
    assert cfg.reasoning_effort == "high"  # model default
    cfg.thinking_tokens = 2048  # user config — no wire effect on depth
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None  # no thinking_budget
    assert (s.extra_body or {}).get("enable_thinking") is True
    assert (s.extra_body or {}).get("reasoning_effort") == "high"


def test_claude_non_adaptive_tokens_maps_to_default_effort():
    # On a pre-4.6 Claude (no adaptive), a configured thinking_tokens emits
    # NO budget_tokens — thinking is requested via the default effort=high
    # (ModelSettings.reasoning) instead.
    cfg = make_config("claude-sonnet-5", "tokens_2048")
    cfg.model_name = "claude-sonnet-4-5"  # simulate a pre-4.6 Claude
    cfg.default_thinking_tokens = None
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_args is None  # no thinking dict, no budget
    assert s.reasoning is not None and s.reasoning.effort == "high"


# ---------------------------------------------------------------------------
# 6. GPT-6 explicit thinking disable -> effort="none" (Responses API)
# ---------------------------------------------------------------------------

def test_responses_explicit_disable_sends_effort_none():
    # --no-thinking / enable_thinking: false on a GPT-6 model must send
    # reasoning={effort: "none"} — the Responses API value that fully turns
    # reasoning OFF. Without it, ResponsesModel's low-effort default would
    # silently re-enable reasoning.
    s = build_settings("gpt-6-luna", "thinking_off")
    assert s.extra_body == {"reasoning": {"effort": "none"}}

    # thinking_off_tokens (disable + a thinking_tokens config): the disable
    # still wins — budgets are never emitted anyway.
    s = build_settings("gpt-6-luna", "thinking_off_tokens")
    assert s.extra_body == {"reasoning": {"effort": "none"}}


def test_responses_disable_beats_effort():
    # An explicit disable wins over any effort (including the model's DRE):
    # effort="none" fully turns reasoning OFF.
    cfg = make_config("gpt-6-luna", "thinking_off")
    cfg.set_reasoning_effort("low")
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_body == {"reasoning": {"effort": "none"}}


def test_responses_effort_none_never_carries_summary():
    # _normalize_reasoning must NOT attach summary="auto" to effort="none"
    # (the Responses API rejects that combination), and must strip a summary
    # that a caller supplied alongside.
    from siada.provider.responses.responses_model import _normalize_reasoning

    assert _normalize_reasoning({"effort": "none"}) == {"effort": "none"}
    assert _normalize_reasoning({"effort": "none", "summary": "auto"}) == {"effort": "none"}
    # sanity: regular efforts still get the auto summary
    assert _normalize_reasoning({"effort": "low"}) == {"effort": "low", "summary": "auto"}


def test_gpt6_and_newer_route_to_responses():
    # GPT-5 and EVERY newer GPT generation (gpt-6, gpt-6-codex, ...) speak
    # the Responses API only; gpt-4.x stays on Chat Completions.
    from siada.provider.responses.responses_model import is_responses_only_model

    assert is_responses_only_model("gpt-6-luna") is True
    assert is_responses_only_model("gpt-5-codex") is True
    assert is_responses_only_model("gpt-6") is True
    assert is_responses_only_model("gpt-6-codex") is True
    assert is_responses_only_model("GPT-6-Terra") is True  # case-insensitive
    assert is_responses_only_model("gpt-4o") is False
    assert is_responses_only_model("gpt-4o-mini") is False
    assert is_responses_only_model("gpt-4.1") is False
    assert is_responses_only_model("claude-sonnet-5") is False
    assert is_responses_only_model("gemini-3.5-flash") is False
    assert is_responses_only_model(None) is False
    assert is_responses_only_model("") is False


def test_gpt6_converter_uses_responses_branch():
    # The converter routes gpt-6 through the Responses branch (effort rides
    # extra_body["reasoning"], explicit disable sends effort="none").
    s = build_settings("gpt-6-luna", "effort_low")
    assert s.extra_body == {"reasoning": {"effort": "low"}}

    # A hypothetical gpt-6 model follows the same branch.
    cfg = make_config("gpt-6-luna", "thinking_off")
    cfg.model_name = "gpt-6-terra"
    s = ModelSettingsConverter.convert_model_settings(cfg)
    assert s.extra_body == {"reasoning": {"effort": "none"}}


# ---------------------------------------------------------------------------
# 7. Default path: effort must survive litellm's drop_params (HTTP body level)
# ---------------------------------------------------------------------------
# The kwargs-level parity above cannot catch this: a top-level
# reasoning_effort kwarg LOOKS fine in captured acompletion kwargs but is
# silently DROPPED by litellm (drop_params=True, set globally by
# siada.entrypoint._configure_litellm) for openai-protocol models. Only the
# final HTTP request body tells the truth — these tests intercept httpx.


def _capture_default_http_body(litellm_model: str, settings) -> dict | None:
    """Run the default provider's model class end-to-end and capture the
    final HTTP request body (past litellm's param dropping)."""
    import httpx
    from agents.models.interface import ModelTracing
    from siada.provider.default.kimi_tool_ordering import (
        get_kimi_tool_ordering_litellm_model_cls,
    )

    captured: list[tuple[str, dict | None]] = []

    async def fake_send(self, request, **kwargs):
        try:
            body = json.loads(request.content) if request.content else None
        except Exception:
            body = None
        captured.append((str(request.url), body))
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 1,
            "model": "test",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "hi"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }, request=request)

    model = get_kimi_tool_ordering_litellm_model_cls()(
        model=litellm_model, base_url="http://test.local", api_key="k"
    )
    from unittest.mock import MagicMock

    # Other test files (e.g. test_default_provider_openrouter) call
    # _configure_litellm(), which sets global litellm state (success
    # callbacks, retries). Those callbacks run reporting code against the
    # intercepted client and can abort the request — isolate this test from
    # all of it; only the wire format is under test here.
    with unittest_mock.patch.object(httpx.AsyncClient, "send", fake_send), \
         unittest_mock.patch.object(litellm, "drop_params", True), \
         unittest_mock.patch.object(litellm, "num_retries", 0), \
         unittest_mock.patch.object(litellm, "success_callback", []), \
         unittest_mock.patch.object(litellm, "failure_callback", []), \
         unittest_mock.patch.object(litellm, "callbacks", []):
        try:
            asyncio.run(model._fetch_response(
                "You are a test", [{"role": "user", "content": "hi"}],
                settings, [], None, [], MagicMock(), ModelTracing.DISABLED,
                stream=False,
            ))
        except Exception:
            # Response parsing may fail on provider-specific fake payloads;
            # only the captured request body matters here.
            pass
    # Only the model request matters — other real httpx traffic (e.g. the
    # remote model-config fetch) may also be intercepted. The model request is
    # the only one aimed at our stub base_url (note: the anthropic path ends
    # in /v1/messages, not /chat/completions).
    chat_bodies = [b for url, b in captured if url.startswith("http://test.local")]
    return chat_bodies[-1] if chat_bodies else None


def test_default_effort_survives_drop_params_in_http_body():
    # glm/deepseek/kimi via the openai/deepseek/moonshot providers: a
    # top-level reasoning_effort kwarg is dropped by drop_params, so the
    # effort must travel in extra_body and land in the request body.
    s = build_settings("glm-5.3", "effort_low")
    body = _capture_default_http_body("openai/glm-5.3", s)
    assert body is not None
    assert body.get("reasoning_effort") == "low"
    assert body.get("thinking") == {"type": "enabled", "clear_thinking": False}

    s = build_settings("kimi-k3", "effort_low")
    body = _capture_default_http_body("moonshot/kimi-k3", s)
    assert body is not None
    assert body.get("reasoning_effort") == "low"


def test_default_claude_channels_survive_drop_params():
    # Claude: ModelSettings.reasoning / extra_args channels are natively
    # accepted top-level by the anthropic provider — the mixin must keep
    # hoisting reasoning_item while output_config/thinking ride extra_args.
    cfg = make_config("claude-sonnet-5", "effort_low")
    cfg.reasoning_effort = None  # simulate no explicit effort
    cfg.thinking_tokens = 4096  # thinking on, no effort -> adaptive (DT=-1)
    s = ModelSettingsConverter.convert_model_settings(cfg)
    body = _capture_default_http_body("anthropic/claude-sonnet-5", s)
    assert body is not None
    assert body.get("thinking") == {"type": "adaptive", "display": "summarized"}

