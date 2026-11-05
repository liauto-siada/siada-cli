"""Tests for GPT generation detection and the GPT-5-and-newer effort ladder.

``is_gpt_5_or_newer()`` drives the /effort validation ladder: GPT-5-and-newer
models (gpt-5.6-luna, gpt-6-astra, ...) all expose low/medium/high/max, and
that set must not depend on the default each MODEL_SETTING entry happens to
declare. Detection must handle provider-qualified names and Astra's unnumbered
alias without widening unrelated families.
"""

from __future__ import annotations

from siada.models.model_base_config import (
    coerce_reasoning_effort,
    get_valid_reasoning_efforts,
    is_gpt_5_or_newer,
)


class TestIsGpt5OrNewerPositive:
    def test_gpt_5_luna(self):
        assert is_gpt_5_or_newer("gpt-5.6-luna") is True

    def test_gpt_5_terra(self):
        assert is_gpt_5_or_newer("gpt-5.6-terra") is True

    def test_gpt_6_astra(self):
        assert is_gpt_5_or_newer("gpt-6-astra") is True

    def test_gpt_6_codex(self):
        assert is_gpt_5_or_newer("gpt-6-codex") is True

    def test_provider_qualified_name(self):
        assert is_gpt_5_or_newer("openai/gpt-5.6-luna") is True

    def test_bare_astra_alias(self):
        assert is_gpt_5_or_newer("astra") is True

    def test_later_generation_keeps_the_openai_ladder(self):
        # The numbered generations are matched as "5 or newer"; a future
        # generation that changes its ladder needs its own branch.
        assert is_gpt_5_or_newer("gpt-7-sol") is True


class TestIsGpt5OrNewerNegative:
    def test_gpt_4o(self):
        assert is_gpt_5_or_newer("gpt-4o") is False

    def test_gpt_35_turbo(self):
        assert is_gpt_5_or_newer("gpt-3.5-turbo") is False

    def test_unnumbered_gpt_name(self):
        assert is_gpt_5_or_newer("gpt-oss-120b") is False

    def test_astra_like_token_is_not_the_alias(self):
        assert is_gpt_5_or_newer("astral-projection") is False

    def test_other_families(self):
        for name in (
            "claude-sonnet-5",
            "gemini-3.5-flash",
            "kivy-qwen-3.8-max",
            "bailian-kimi-k3",
            "baidu-deepseek-v4-pro",
            "kivy-glm-5.2",
            "o3-mini",
        ):
            assert is_gpt_5_or_newer(name) is False, name

    def test_empty_and_none(self):
        assert is_gpt_5_or_newer("") is False
        assert is_gpt_5_or_newer(None) is False


class TestGptEffortLadder:
    def test_family_ladder_is_low_medium_high_max(self):
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra", "astra"):
            assert get_valid_reasoning_efforts(model) == [
                "low",
                "medium",
                "high",
                "max",
            ], model

    def test_ladder_does_not_depend_on_the_declared_default(self):
        # gpt-6-astra declares "low", the gpt-5.6 entries declare "max"; both
        # must expose exactly the same levels either way.
        assert get_valid_reasoning_efforts("gpt-6-astra", "low") == (
            get_valid_reasoning_efforts("gpt-5.6-terra", "max")
        )

    def test_xhigh_maps_to_max_like_gpt5(self):
        assert coerce_reasoning_effort("gpt-6-astra", "xhigh", "low") == "max"
        assert coerce_reasoning_effort("gpt-5.6-terra", "xhigh", "max") == "max"

    def test_other_families_are_unchanged(self):
        assert get_valid_reasoning_efforts("gemini-3.5-flash") == [
            "low",
            "medium",
            "high",
        ]
        assert get_valid_reasoning_efforts("claude-sonnet-5") == [
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ]
        assert get_valid_reasoning_efforts("bailian-kimi-k3") == [
            "low",
            "high",
            "max",
        ]
        assert get_valid_reasoning_efforts("kivy-qwen-3.7-plus") == [
            "low",
            "medium",
            "xhigh",
        ]