"""Compaction summarization must accept native Responses apply_patch history.

``call_llm_to_compact`` sends native history to the wrapped SDK model, while
token accounting still uses the ChatCompletions converter. Before the fix,
any native ``apply_patch_call`` item in the slice
raised ``UserError("Unhandled item type or structure")``, silently breaking
compaction for GPT-5/Astra sessions.
"""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agents import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage

from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)
from siada.provider import one_shot


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

        response = ModelResponse(
            output=[ResponseOutputMessage.model_validate({
                "id": "msg-synthetic", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "<context>summary</context>", "annotations": []}],
            })],
            usage=Usage(), response_id="response-synthetic",
        )
        completion = AsyncMock(return_value=response)

        with patch(
            "siada.agent_hub.context_filter.compaction_strategy.one_shot_completion",
            completion,
        ):
            summary = await strategy.call_llm_to_compact(model_config, _patch_history())

        assert summary == "<context>summary</context>"

        sent = completion.await_args.args[0]
        # Native history reaches the shared boundary without losing operations;
        # ModelWrapper selects native replay or function-call proxies by protocol.
        calls = [item for item in sent if item.get("type") == "apply_patch_call"]
        outputs = [item for item in sent if item.get("type") == "apply_patch_call_output"]
        assert calls[0]["operation"]["path"] == "a.py"
        assert calls[0]["call_id"] == outputs[0]["call_id"] == "c1"
        assert sent[-1]["role"] == "user"
        assert completion.await_args.kwargs["provider"] == "default"
        assert completion.await_args.kwargs["agent_name"] == "context_compaction"
        assert completion.await_args.kwargs["stream"] is True

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

        response = ModelResponse(
            output=[ResponseOutputMessage.model_validate({
                "id": "msg-synthetic", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "<context>second summary</context>", "annotations": []}],
            })],
            usage=Usage(), response_id="response-synthetic",
        )

        with patch(
            "siada.agent_hub.context_filter.compaction_strategy.one_shot_completion",
            AsyncMock(return_value=response),
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


def _custom_history() -> list:
    return [
        {"role": "user", "content": "synthetic task"},
        {"type": "custom_tool_call", "id": "custom-item", "call_id": "custom-call",
         "name": "unavailable_custom", "input": "raw patch\nnot JSON"},
        {"type": "custom_tool_call_output", "call_id": "custom-call", "output": "not found"},
    ]


@pytest.mark.asyncio
async def test_custom_history_reaches_real_compaction_chat_boundary(monkeypatch):
    from agents.models.chatcmpl_converter import Converter
    from openai.types.responses import Response, ResponseCompletedEvent

    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    history = _custom_history()
    original = deepcopy(history)
    seen = []

    async def stream_response(**kwargs):
        messages = Converter.items_to_messages(kwargs["input"])
        seen.extend(messages)
        response = Response.model_construct(
            id="summary-response", object="response", created_at=0, model="gpt-4o-mini",
            status="completed", output=[ResponseOutputMessage.model_validate({
                "id": "summary", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "<context>summary</context>", "annotations": []}],
            })], usage=None,
        )
        yield ResponseCompletedEvent(type="response.completed", response=response, sequence_number=0)

    model = SimpleNamespace(model="gpt-4o-mini", stream_response=stream_response)
    provider = SimpleNamespace(get_model=Mock(return_value=model))
    monkeypatch.setattr(one_shot, "get_provider", lambda name: provider)
    summary = await SummarizeWithHeaderCompaction().call_llm_to_compact(_model_config(), history)
    assert summary == "<context>summary</context>"
    call = next(message["tool_calls"][0] for message in seen if message.get("tool_calls"))
    assert call["function"]["name"] == "unavailable_custom"
    assert json.loads(call["function"]["arguments"]) == {"input": "raw patch\nnot JSON"}
    assert next(message for message in seen if message["role"] == "tool") == {
        "role": "tool", "tool_call_id": "custom-call", "content": "not found",
    }
    assert history == original


def test_custom_history_token_counting_uses_converter():
    from siada.agent_hub.context_filter.utils import _calculate_tokens

    assert _calculate_tokens("gpt-4o-mini", _custom_history()) > 0


@pytest.mark.parametrize("orphan_type", ["custom_tool_call", "custom_tool_call_output"])
def test_compaction_removes_orphan_custom_tool_items(orphan_type):
    strategy = SummarizeWithHeaderCompaction()
    history = _custom_history()
    assert strategy._repair_tool_pairs(history) == history
    orphan = next(item for item in history if item.get("type") == orphan_type)
    assert strategy._repair_tool_pairs([history[0], orphan]) == history[:1]


def test_compaction_preserves_complete_trailing_custom_pair():
    strategy = SummarizeWithHeaderCompaction()
    history = _custom_history()
    assert strategy.adjust_compression_index_for_boundary_cases(history, len(history)) == 1
    assert strategy._repair_tool_pairs(history[1:], require_user_start=False) == history[1:]