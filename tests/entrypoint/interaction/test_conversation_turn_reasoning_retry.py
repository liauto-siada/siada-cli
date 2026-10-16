"""Thinking display ownership when a model transport attempt restarts."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import RawResponsesStreamEvent
from openai.types.responses import (
    ResponseCreatedEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn


@pytest.mark.asyncio
async def test_retry_closes_thinking_before_starting_new_display():
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        io=SimpleNamespace(acp_enabled=True),
        llm_config=SimpleNamespace(model_name="synthetic-model"),
    )
    turn._message_counter = 0
    turn._current_message_id = None
    turn._stream_start_id = None
    turn._stop_waiting_spinner = Mock()
    turn._feed_repetition_guard = Mock()
    turn._send_lifecycle_event = Mock()
    display = Mock()
    turn.mdstream = display
    streamed = []

    def record(delta, content, **kwargs):
        streamed.append((delta, content, turn._stream_start_id))

    turn._live_incremental_response = record

    def raw(cls, **kwargs):
        return RawResponsesStreamEvent(data=cls.model_construct(**kwargs))

    async def events():
        yield raw(ResponseCreatedEvent, type="response.created", response=None)
        yield raw(
            ResponseReasoningSummaryTextDeltaEvent,
            type="response.reasoning_summary_text.delta", delta="failed thinking",
        )
        yield raw(ResponseCreatedEvent, type="response.created", response=None)
        yield raw(
            ResponseReasoningSummaryTextDeltaEvent,
            type="response.reasoning_summary_text.delta", delta="fresh thinking",
        )
        yield raw(ResponseTextDeltaEvent, type="response.output_text.delta", delta="answer")

    await turn.output_stream_content(SimpleNamespace(stream_events=events))
    lifecycle = [call.args[0] for call in turn._send_lifecycle_event.call_args_list]
    assert [(event["type"], event["message_type"]) for event in lifecycle] == [
        ("message_start", "thinking"),
        ("message_end", "thinking"),
        ("message_start", "thinking"),
        ("message_end", "thinking"),
        ("message_start", "answer"),
    ]
    assert lifecycle[0]["message_id"] == lifecycle[1]["message_id"]
    assert lifecycle[2]["message_id"] == lifecycle[3]["message_id"]
    assert lifecycle[0]["message_id"] != lifecycle[2]["message_id"]
    assert streamed[0][2] != streamed[1][2]
    assert "failed thinking" not in streamed[-1][1]
    assert "fresh thinking" in streamed[-1][1]
    assert streamed[-1][2] == streamed[1][2]
    display.close.assert_called_once()