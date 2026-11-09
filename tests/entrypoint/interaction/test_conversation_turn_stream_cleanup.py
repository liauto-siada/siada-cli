"""Abnormal consumers cancel the real SDK producer before closing its stream."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import Agent, RunConfig, Runner
from agents.models.interface import Model
from openai.types.responses import (
    Response, ResponseCompletedEvent, ResponseCreatedEvent, ResponseOutputMessage,
    ResponseOutputText, ResponseTextDeltaEvent,
)

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn


class GatedModel(Model):
    def __init__(self):
        self.closed = asyncio.Event()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def get_response(self, *args, **kwargs):
        raise AssertionError("Only streaming is allowed")

    async def stream_response(self, *args, **kwargs):
        try:
            self.started.set()
            response = Response(
                id="synthetic-response", created_at=0, model="synthetic", object="response",
                output=[], parallel_tool_calls=False, tool_choice="auto", tools=[],
            )
            yield ResponseCreatedEvent(type="response.created", sequence_number=0, response=response)
            yield ResponseTextDeltaEvent(
                type="response.output_text.delta", sequence_number=1, item_id="synthetic-text",
                output_index=0, content_index=0, delta="partial answer", logprobs=[],
            )
            await self.release.wait()
            response.output = [ResponseOutputMessage(
                id="synthetic-text", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="complete answer", annotations=[])],
            )]
            yield ResponseCompletedEvent(type="response.completed", sequence_number=2, response=response)
        finally:
            self.closed.set()


def make_turn(result):
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        llm_config=SimpleNamespace(model_name="synthetic"),
        io=SimpleNamespace(acp_enabled=True, pretty=False),
    )
    turn.current_result = result
    turn.mdstream = None
    turn._message_counter = 0
    turn._current_message_id = None
    turn._stream_start_id = None
    turn._stop_waiting_spinner = Mock()
    turn._send_lifecycle_event = Mock()
    turn._live_incremental_response = Mock()
    turn._print_context_usage = Mock()
    turn._feed_repetition_guard = Mock()
    return turn


def run_model(model):
    return Runner.run_streamed(
        Agent(name="offline", model=model), input="synthetic task",
        run_config=RunConfig(tracing_disabled=True),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["render", "guard"])
@pytest.mark.parametrize("error_type", [ValueError, asyncio.CancelledError])
async def test_stream_error_cancels_producer_and_preserves_error(location, error_type):
    model = GatedModel()
    result = run_model(model)
    turn = make_turn(result)
    error = error_type("synthetic consumer failure")
    if location == "render":
        turn._live_incremental_response.side_effect = error
    else:
        turn._feed_repetition_guard.side_effect = error
    consumer = asyncio.create_task(turn.output_stream_content(result))
    try:
        done, _ = await asyncio.wait({consumer}, timeout=1)
        assert consumer in done, "Stream closure must not wait for the gated model"
        with pytest.raises(error_type) as raised:
            await consumer
        assert raised.value is error
        assert model.closed.is_set()
        assert result.run_loop_task.done()
    finally:
        result.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("render_stream", [False, True])
async def test_external_consumer_cancellation_closes_model(render_stream):
    model = GatedModel()
    result = run_model(model)
    turn = make_turn(result)
    turn.render_stream = render_stream
    consumer = asyncio.create_task(turn.output_stream_content(result))
    try:
        await asyncio.wait_for(model.started.wait(), timeout=1)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(consumer, timeout=1)
        assert model.closed.is_set()
        assert result.run_loop_task.done()
    finally:
        result.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("render_stream", [False, True])
async def test_normal_completion_does_not_cancel_execution(render_stream):
    model = GatedModel()
    model.release.set()
    result = run_model(model)
    result.cancel = Mock(wraps=result.cancel)
    turn = make_turn(result)
    turn.render_stream = render_stream
    await asyncio.wait_for(turn.output_stream_content(result), timeout=1)
    assert result.final_output == "complete answer"
    assert model.closed.is_set()
    result.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_error_does_not_replace_original_render_error():
    model = GatedModel()
    result = run_model(model)
    result._await_model_provider_cleanup = AsyncMock(side_effect=RuntimeError("synthetic cleanup failure"))
    turn = make_turn(result)
    error = ValueError("synthetic render failure")
    turn._live_incremental_response.side_effect = error
    with pytest.raises(ValueError) as raised:
        await asyncio.wait_for(turn.output_stream_content(result), timeout=1)
    assert raised.value is error
    assert model.closed.is_set()
