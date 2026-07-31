"""Tests for GLM reasoning-content replay in the LiModel provider.

Verifies that ``_should_replay_reasoning_content`` correctly replays reasoning
items for GLM models (glm-5.1, glm-5.2) while preserving the default DeepSeek
behaviour and rejecting cross-model contamination.
"""

from __future__ import annotations

from agents.models.chatcmpl_converter import Converter
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.models.reasoning_content_replay import (
    ReasoningContentReplayContext,
    ReasoningContentSource,
)

from siada.provider.reasoning_replay import should_replay_reasoning_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_reasoning_item(
    text: str = "thinking...",
    *,
    provider_data: dict | None = None,
) -> dict:
    """Build a minimal Responses-API reasoning item dict."""
    item: dict = {
        "id": FAKE_RESPONSES_ID,
        "type": "reasoning",
        "summary": [{"text": text, "type": "summary_text"}],
    }
    if provider_data is not None:
        item["provider_data"] = provider_data
    return item


def _make_context(
    model: str,
    reasoning_item: dict,
) -> ReasoningContentReplayContext:
    provider_data = reasoning_item.get("provider_data", {})
    origin_model = provider_data.get("model") if provider_data else None
    return ReasoningContentReplayContext(
        model=model,
        base_url=None,
        reasoning=ReasoningContentSource(
            item=reasoning_item,
            origin_model=origin_model or None,
            provider_data=provider_data,
        ),
    )


# ---------------------------------------------------------------------------
# Hook unit tests
# ---------------------------------------------------------------------------

class TestShouldReplayForGLM:
    """GLM models should replay reasoning content."""

    def test_glm_51_with_matching_origin(self):
        item = _make_reasoning_item(provider_data={"model": "glm-5.1"})
        ctx = _make_context("glm-5.1", item)
        assert should_replay_reasoning_content(ctx) is True

    def test_glm_52_with_matching_origin(self):
        item = _make_reasoning_item(provider_data={"model": "glm-5.2"})
        ctx = _make_context("glm-5.2", item)
        assert should_replay_reasoning_content(ctx) is True

    def test_lpai_glm_52_with_matching_origin(self):
        item = _make_reasoning_item(provider_data={"model": "lpai-glm-5.2"})
        ctx = _make_context("lpai-glm-5.2", item)
        assert should_replay_reasoning_content(ctx) is True

    def test_glm_with_empty_provider_data_backward_compat(self):
        """Reasoning items without provider_data (old non-streaming path)."""
        item = _make_reasoning_item(provider_data={})
        ctx = _make_context("glm-5.1", item)
        assert should_replay_reasoning_content(ctx) is True


class TestNoCrossModelContamination:
    """Reasoning from a different model family should NOT be replayed."""

    def test_deepseek_reasoning_not_replayed_to_glm(self):
        item = _make_reasoning_item(provider_data={"model": "deepseek-v4-pro"})
        ctx = _make_context("glm-5.1", item)
        assert should_replay_reasoning_content(ctx) is False

    def test_glm_reasoning_not_replayed_to_deepseek(self):
        item = _make_reasoning_item(provider_data={"model": "glm-5.1"})
        ctx = _make_context("deepseek-v4-pro", item)
        assert should_replay_reasoning_content(ctx) is False

    def test_glm_reasoning_not_replayed_to_claude(self):
        item = _make_reasoning_item(provider_data={"model": "glm-5.1"})
        ctx = _make_context("claude-sonnet-4-6", item)
        assert should_replay_reasoning_content(ctx) is False


class TestDeepSeekDefaultPreserved:
    """The default DeepSeek replay behaviour must still work."""

    def test_deepseek_with_matching_origin(self):
        item = _make_reasoning_item(provider_data={"model": "deepseek-v4-pro"})
        ctx = _make_context("deepseek-v4-pro", item)
        assert should_replay_reasoning_content(ctx) is True

    def test_deepseek_with_empty_provider_data(self):
        item = _make_reasoning_item(provider_data={})
        ctx = _make_context("deepseek-v4-pro", item)
        assert should_replay_reasoning_content(ctx) is True


# ---------------------------------------------------------------------------
# Integration: items_to_messages should inject reasoning_content for GLM
# ---------------------------------------------------------------------------

class TestItemsToMessagesReplay:
    """End-to-end check that ``items_to_messages`` injects ``reasoning_content``
    into the assistant message when targeting a GLM model."""

    def test_glm_reasoning_replayed_into_assistant_message(self):
        reasoning_item = _make_reasoning_item(
            "Let me analyze this step by step.",
            provider_data={"model": "glm-5.1"},
        )
        # In real flows the reasoning item is followed by an assistant output
        # message (the model's text response), then a user turn.
        assistant_output = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "The answer is 2."}],
            "status": "completed",
        }
        items = [
            reasoning_item,
            assistant_output,
            {"role": "user", "content": "What is 1+1?"},
        ]
        messages = Converter.items_to_messages(
            items,
            model="glm-5.1",
            should_replay_reasoning_content=should_replay_reasoning_content,
        )
        # The first message should be an assistant message with reasoning_content.
        assistant_msgs = [
            m for m in messages if m.get("role") == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        assert assistant_msgs[0].get("reasoning_content") == "Let me analyze this step by step."

    def test_glm_reasoning_not_replayed_when_origin_mismatch(self):
        reasoning_item = _make_reasoning_item(
            "DeepSeek thinking.",
            provider_data={"model": "deepseek-v4-pro"},
        )
        assistant_output = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "The answer is 2."}],
            "status": "completed",
        }
        items = [
            reasoning_item,
            assistant_output,
            {"role": "user", "content": "What is 1+1?"},
        ]
        messages = Converter.items_to_messages(
            items,
            model="glm-5.1",
            should_replay_reasoning_content=should_replay_reasoning_content,
        )
        assistant_msgs = [
            m for m in messages if m.get("role") == "assistant"
        ]
        # No assistant message should carry reasoning_content.
        for m in assistant_msgs:
            assert "reasoning_content" not in m
