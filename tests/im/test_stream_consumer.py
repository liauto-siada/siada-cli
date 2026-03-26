"""Tests for LarkStreamConsumer - tool card group splitting logic.

Verifies that:
1. Consecutive tool calls (without reasoning/text in between) stay in one card group
2. Tool calls separated by reasoning content get split into different card groups
3. Tool calls separated by text content get split into different card groups
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
from openai.types.responses import (
    ResponseCreatedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)


# ── Helper: build a mock RunResultStreaming ──────────────────────────

class _MockRunResultStreaming:
    """Yields predefined events via async iterator."""

    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for ev in self._events:
            yield ev


# ── Dummy formatter that just echoes tool name + args ────────────────

class _EchoFormatter:
    def format_input_im(self, call_id, tool_name, arguments, default_workspace=""):
        return f"**{tool_name}**({arguments})", ""


# ── Event factory helpers using model_construct to bypass validation ──

def _mc(cls, **kwargs):
    """Create a pydantic model instance bypassing validation."""
    return cls.model_construct(**kwargs)


def _make_response_created():
    """Build a minimal ResponseCreatedEvent."""
    from openai.types.responses import Response
    resp = _mc(Response, id="resp_1", created_at=0, model="test",
               object="response", output=[], parallel_tool_calls=False,
               tool_choice="auto", tools=[])
    return _mc(ResponseCreatedEvent, response=resp, type="response.created",
               sequence_number=0)


def _make_reasoning_delta(delta: str):
    """Build a ResponseReasoningSummaryTextDeltaEvent."""
    return _mc(ResponseReasoningSummaryTextDeltaEvent,
               delta=delta, item_id="item_r", output_index=0,
               summary_index=0, sequence_number=0,
               type="response.reasoning_summary_text.delta")


def _make_text_delta(delta: str):
    """Build a ResponseTextDeltaEvent."""
    return _mc(ResponseTextDeltaEvent,
               content_index=0, delta=delta, item_id="item_t",
               output_index=0, sequence_number=0, logprobs=None,
               type="response.output_text.delta")


def _msg_id_gen():
    """Generator producing unique message IDs for send_card_get_id."""
    n = 0
    while True:
        n += 1
        yield f"msg_{n}"


def _make_card_sender():
    """Create a mock LarkCardSender with tracked calls."""
    cs = MagicMock()
    cs._has_credentials = MagicMock(return_value=True)
    cs.send_card_get_id = AsyncMock(side_effect=_msg_id_gen())
    cs.patch_card_content = AsyncMock()
    cs.send_card_message = AsyncMock()
    cs.send_im = AsyncMock()
    cs.create_streaming_card = MagicMock(return_value=None)  # no streaming card
    return cs


def _tool_call_events(call_id: str, item_id: str, tool_name: str, arguments: str):
    """Generate the raw event sequence for one complete tool call."""
    tool_item = _mc(ResponseFunctionToolCall,
                    id=item_id, call_id=call_id, name=tool_name,
                    arguments="", type="function_call", status="in_progress")
    tool_item_done = _mc(ResponseFunctionToolCall,
                         id=item_id, call_id=call_id, name=tool_name,
                         arguments=arguments, type="function_call", status="completed")
    return [
        RawResponsesStreamEvent(
            data=_mc(ResponseOutputItemAddedEvent,
                     item=tool_item, output_index=0, sequence_number=0,
                     type="response.output_item.added"),
            type="raw_response_event",
        ),
        RawResponsesStreamEvent(
            data=_mc(ResponseFunctionCallArgumentsDeltaEvent,
                     delta=arguments, item_id=item_id, output_index=0,
                     sequence_number=0,
                     type="response.function_call_arguments.delta"),
            type="raw_response_event",
        ),
        RawResponsesStreamEvent(
            data=_mc(ResponseOutputItemDoneEvent,
                     item=tool_item_done, output_index=0, sequence_number=0,
                     type="response.output_item.done"),
            type="raw_response_event",
        ),
    ]


def _tool_result_event(call_id: str, output: str = "ok"):
    """Generate a RunItemStreamEvent for tool result."""
    item = MagicMock(spec=ToolCallOutputItem)
    item.raw_item = {"call_id": call_id}
    item.output = output
    return RunItemStreamEvent(item=item, name="tool_call_output")


def _raw(data):
    """Wrap a raw response data into RawResponsesStreamEvent."""
    return RawResponsesStreamEvent(data=data, type="raw_response_event")


# ── Tests ────────────────────────────────────────────────────────────

class TestToolCardGroupSplitting:
    """Test that tool card groups are correctly split by reasoning/text boundaries."""

    @pytest.fixture(autouse=True)
    def _patch_formatter(self):
        """Patch ToolCallFormatterFactory to use echo formatter."""
        mock_factory = MagicMock()
        mock_factory.get_formatter = MagicMock(return_value=_EchoFormatter())
        with patch(
            "siada.tools.tool_call_format.formatter_factory.ToolCallFormatterFactory",
            mock_factory,
        ):
            yield

    @pytest.mark.asyncio
    async def test_consecutive_tools_stay_in_one_card(self):
        """Tool calls across LLM turns WITHOUT reasoning/text stay in one card group.

        Scenario:
          Turn 1: ResponseCreated -> ToolCall_A -> ToolResult_A
          Turn 2: ResponseCreated -> ToolCall_B -> ToolResult_B
        Expected: only 1 send_card_get_id call (one card group).
        """
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            *_tool_call_events("call_2", "item_2", "run_cmd", '{"cmd":"ls"}'),
            _tool_result_event("call_2"),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 1

    @pytest.mark.asyncio
    async def test_reasoning_splits_tool_card_groups(self):
        """Reasoning content between tool call groups forces a new card.

        Scenario:
          Turn 1: ResponseCreated -> ToolCall_A -> ToolResult_A
          Turn 2: ResponseCreated -> Reasoning -> ToolCall_B -> ToolResult_B
        Expected: 2 send_card_get_id calls.
        """
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            _raw(_make_reasoning_delta("Let me think...")),
            *_tool_call_events("call_2", "item_2", "run_cmd", '{"cmd":"ls"}'),
            _tool_result_event("call_2"),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 2

    @pytest.mark.asyncio
    async def test_text_content_splits_tool_card_groups(self):
        """Text content between tool call groups forces a new card.

        Scenario:
          Turn 1: ResponseCreated -> ToolCall_A -> ToolResult_A
          Turn 2: ResponseCreated -> TextDelta -> ToolCall_B -> ToolResult_B
        Expected: 2 send_card_get_id calls.
        """
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            _raw(_make_text_delta("Here's what I found")),
            *_tool_call_events("call_2", "item_2", "run_cmd", '{"cmd":"ls"}'),
            _tool_result_event("call_2"),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 2

    @pytest.mark.asyncio
    async def test_three_tool_groups_with_reasoning_boundaries(self):
        """Three tool groups separated by reasoning -> 3 separate card groups."""
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            _raw(_make_reasoning_delta("thinking 1")),
            *_tool_call_events("call_2", "item_2", "run_cmd", '{"cmd":"ls"}'),
            _tool_result_event("call_2"),
            _raw(_make_response_created()),
            _raw(_make_reasoning_delta("thinking 2")),
            *_tool_call_events("call_3", "item_3", "web_search", '{"q":"test"}'),
            _tool_result_event("call_3"),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 3

    @pytest.mark.asyncio
    async def test_close_tool_card_called_on_reasoning_boundary(self):
        """When reasoning appears after pending tools, tool card is finalized via patch."""
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            _raw(_make_reasoning_delta("hmm")),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        # patch_card_content called at least once to finalize tool card
        assert cs.patch_card_content.call_count >= 1

    @pytest.mark.asyncio
    async def test_close_tool_card_called_on_text_boundary(self):
        """When text content appears after pending tools, tool card is closed."""
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "edit_file", '{"command":"view"}'),
            _tool_result_event("call_1"),
            _raw(_make_response_created()),
            _raw(_make_text_delta("done")),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.patch_card_content.call_count >= 1

    @pytest.mark.asyncio
    async def test_single_tool_call_single_card(self):
        """A single tool call should produce exactly one card."""
        events = [
            _raw(_make_response_created()),
            *_tool_call_events("call_1", "item_1", "run_cmd", '{"cmd":"echo hi"}'),
            _tool_result_event("call_1"),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 1

    @pytest.mark.asyncio
    async def test_no_tool_calls_no_card(self):
        """When there are no tool calls, no tool card should be created."""
        events = [
            _raw(_make_response_created()),
            _raw(_make_text_delta("Hello world")),
        ]

        cs = _make_card_sender()
        consumer = self._make_consumer(cs)
        await consumer.consume_stream(
            _MockRunResultStreaming(events), "req_1", "chat_1", "/workspace")

        assert cs.send_card_get_id.call_count == 0

    def _make_consumer(self, card_sender):
        from siada.im.feishu.stream_consumer import LarkStreamConsumer
        return LarkStreamConsumer(card_sender=card_sender, mode="direct")
