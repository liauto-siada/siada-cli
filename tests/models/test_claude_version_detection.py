"""Tests for Claude version detection (is_claude_4_6_or_newer).

Adaptive thinking (``thinking: {"type": "adaptive"}``) is a Claude-exclusive
capability first available on Claude 4.6. The detector must handle every
naming variant: dot/dash separators, family-first / version-first ordering,
date suffixes, and provider prefixes (aws-, anthropic/, bedrock/,
us.anthropic...).
"""

from __future__ import annotations

from siada.models.model_base_config import is_claude_4_6_or_newer


class TestIsClaude46OrNewerPositive:
    def test_family_first_dash(self):
        assert is_claude_4_6_or_newer("claude-sonnet-4-6") is True

    def test_family_first_dot(self):
        assert is_claude_4_6_or_newer("claude-sonnet-4.6") is True

    def test_version_first_dash(self):
        assert is_claude_4_6_or_newer("claude-4-6-sonnet") is True

    def test_version_first_dot(self):
        assert is_claude_4_6_or_newer("claude-4.6-sonnet") is True

    def test_with_date_suffix(self):
        assert is_claude_4_6_or_newer("claude-sonnet-4-6-20250929") is True

    def test_opus_46(self):
        assert is_claude_4_6_or_newer("claude-opus-4-6") is True

    def test_claude_5_family_first(self):
        assert is_claude_4_6_or_newer("claude-sonnet-5") is True

    def test_claude_5_version_first(self):
        assert is_claude_4_6_or_newer("claude-5-sonnet") is True

    def test_claude_5_5(self):
        assert is_claude_4_6_or_newer("claude-sonnet-5.5") is True

    def test_aws_prefix(self):
        assert is_claude_4_6_or_newer("aws-claude-sonnet-4-6") is True

    def test_anthropic_slash_prefix(self):
        assert is_claude_4_6_or_newer("anthropic/claude-sonnet-4.6") is True

    def test_bedrock_prefix(self):
        assert is_claude_4_6_or_newer("bedrock/claude-opus-4-6") is True

    def test_us_anthropic_full_prefix(self):
        assert is_claude_4_6_or_newer(
            "us.anthropic.claude-sonnet-4-6-20250929-v1:0"
        ) is True

    def test_aws_prefix_claude_5(self):
        assert is_claude_4_6_or_newer("aws-claude-sonnet-5") is True


class TestIsClaude46OrNewerNegative:
    def test_claude_45_dash(self):
        assert is_claude_4_6_or_newer("claude-sonnet-4-5") is False

    def test_claude_45_dot(self):
        assert is_claude_4_6_or_newer("claude-sonnet-4.5") is False

    def test_claude_41(self):
        assert is_claude_4_6_or_newer("claude-opus-4-1") is False

    def test_claude_4_with_date_not_parsed_as_minor(self):
        # "claude-sonnet-4-20250514" is Claude 4.0 (no minor); the date must
        # not be mistaken for a minor version.
        assert is_claude_4_6_or_newer("claude-sonnet-4-20250514") is False

    def test_old_style_35(self):
        assert is_claude_4_6_or_newer("claude-3-5-sonnet") is False

    def test_old_style_35_with_date(self):
        assert is_claude_4_6_or_newer("claude-3-5-haiku-20241022") is False

    def test_claude_3_haiku(self):
        assert is_claude_4_6_or_newer("claude-3-haiku") is False

    def test_no_version(self):
        assert is_claude_4_6_or_newer("claude-haiku") is False

    def test_non_claude_models(self):
        for name in (
            "kivy-deepseek-v4-flash",
            "kivy-qwen-3.8-max",
            "kivy-glm-5.2",
            "bailian-kimi-k3",
            "gemini-3.5-flash",
            "gpt-5.6-luna",
        ):
            assert is_claude_4_6_or_newer(name) is False, name

    def test_empty_and_none(self):
        assert is_claude_4_6_or_newer("") is False
        assert is_claude_4_6_or_newer(None) is False
