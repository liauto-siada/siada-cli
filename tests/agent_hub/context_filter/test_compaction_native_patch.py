"""Compaction summarization must accept native Responses apply_patch history.

``call_llm_to_compact`` converts the history slice with the ChatCompletions
``Converter`` (the summarization call is chat-shaped regardless of the main
model).  Before the fix, any native ``apply_patch_call`` item in the slice
raised ``UserError("Unhandled item type or structure")``, silently breaking
compaction for GPT-5/Astra sessions.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)


def _model_config() -> SimpleNamespace:
    """Minimal stand-in for ``ModelRunConfig``.

    ``call_llm_to_compact`` only reads ``provider`` / ``model_name`` (and the
    token counter only ``model_name``), so a tiny stub keeps these tests
    offline -- constructing the real config can trigger a remote
    model-config fetch.
    """
    return SimpleNamespace(
        model_name="gpt-4o-mini",
        provider="default",
        context_window=128_000,
    )


def _patch_history() -> list:
    return [
        {"role": "user", "content": "update a.py"},
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [{"type": "summary_text", "text": "thinking"}],
        },
        {
            "type": "apply_patch_call",
            "id": "apc_1",
            "call_id": "c1",
            "status": "completed",
            "operation": {"type": "update_file", "path": "a.py", "diff": "@@"},
        },
        {
            "type": "apply_patch_call_output",
            "id": "apco_1",
            "call_id": "c1",
            "status": "completed",
            "output": "Done!",
        },
        {"role": "user", "content": "thanks"},
    ]


class TestCallLlmToCompactWithNativePatchItems:
    @pytest.mark.asyncio
    async def test_accepts_native_patch_history(self, monkeypatch):
        monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)

        strategy = SummarizeWithHeaderCompaction()
        model_config = _model_config()

        message = SimpleNamespace(content="<context>summary</context>")
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        client = SimpleNamespace(completion=AsyncMock(return_value=response))

        with patch(
            "siada.agent_hub.context_filter.compaction_strategy.get_client",
            return_value=client,
        ):
            summary = await strategy.call_llm_to_compact(model_config, _patch_history())

        assert summary == "<context>summary</context>"

        sent = client.completion.await_args.kwargs["messages"]
        # The summarization request carries the function-call-shaped proxy,
        # paired exactly like the native call/output pair.
        assistant_calls = [m for m in sent if m.get("tool_calls")]
        assert assistant_calls, "expected an assistant message with tool_calls"
        assert assistant_calls[0]["tool_calls"][0]["function"]["name"] == "apply_patch"
        tool_messages = [m for m in sent if m.get("role") == "tool"]
        assert tool_messages and tool_messages[0]["tool_call_id"] == "c1"

    def test_raw_conversion_anchor(self):
        """Without the rewrite the SDK converter raises -- this is the bug."""
        from agents.exceptions import UserError
        from agents.models.chatcmpl_converter import Converter

        with pytest.raises(UserError, match="Unhandled item type or structure"):
            Converter.items_to_messages(_patch_history())


class TestCompactedHistoryChatReplay:
    """The compaction acknowledgment message must survive chat conversions.

    Both strategies build an id-less assistant ``output_text`` message as the
    acknowledgment.  Before the rewrite, that shape crashed every later chat
    conversion: the second compaction's summarization call, token counting,
    and any model switch replay.
    """

    def _compacted_history(self) -> list:
        strategy = SummarizeWithHeaderCompaction()
        return strategy.create_compressed_message_history(
            header_message=[{"role": "user", "content": "original task"}],
            summary="<context>summary of earlier work</context>",
            history_to_keep=[{"role": "user", "content": "next request"}],
        )

    @pytest.mark.asyncio
    async def test_second_compaction_summarization_succeeds(self, monkeypatch):
        monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)

        strategy = SummarizeWithHeaderCompaction()
        model_config = _model_config()

        message = SimpleNamespace(content="<context>second summary</context>")
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        client = SimpleNamespace(completion=AsyncMock(return_value=response))

        with patch(
            "siada.agent_hub.context_filter.compaction_strategy.get_client",
            return_value=client,
        ):
            summary = await strategy.call_llm_to_compact(
                model_config, self._compacted_history()
            )

        assert summary == "<context>second summary</context>"

    def test_token_counting_no_longer_raises_on_compacted_history(self):
        """Anchor for the silent token-count degradation after compaction.

        Before the rewrite, ``_calculate_tokens`` raised ``UserError`` on the
        ack message, so ``calculate_tokens`` always fell back to the rough
        char-based estimate once a session had been compacted.
        """
        from siada.agent_hub.context_filter.utils import _calculate_tokens

        result = _calculate_tokens("gpt-4o-mini", self._compacted_history())

        assert isinstance(result, int) and result > 0