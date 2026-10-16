"""Reasoning remains live while the model request can still be retried."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from agents import Agent, RunConfig, Runner
from litellm.exceptions import MidStreamFallbackError
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseOutputItemDoneEvent,
    ResponseReasoningItem,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from siada.provider import retry
from siada.services.model_wrapper import ModelWrapper


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["midstream", "timeout", "eof"])
@pytest.mark.parametrize("empty_final_output", [False, True])
async def test_runner_retries_after_live_thinking_with_one_final_answer(
    failure, empty_final_output, monkeypatch,
):
    monkeypatch.setattr(retry, "_backoff", AsyncMock())
    attempts = []
    closed = []

    async def stream(**kwargs):
        attempt = len(attempts)
        attempts.append(attempt)
        response = Response.model_construct(
            id=f"resp-{attempt}", created_at=1, model="synthetic", object="response",
            status="in_progress", output=[], error=None, usage=None,
        )
        try:
            yield ResponseCreatedEvent.model_construct(
                type="response.created", response=response, sequence_number=0,
            )
            for index in range(70):
                yield ResponseReasoningSummaryTextDeltaEvent.model_construct(
                    type="response.reasoning_summary_text.delta",
                    item_id=f"think-{attempt}", output_index=0, summary_index=0,
                    delta=f"thinking-{attempt}-{index}", sequence_number=index + 1,
                )
            reasoning = ResponseReasoningItem.model_construct(
                id=f"think-{attempt}", type="reasoning", status="completed", summary=[],
            )
            yield ResponseOutputItemDoneEvent.model_construct(
                type="response.output_item.done", output_index=0,
                item=reasoning, sequence_number=71,
            )
            if attempt == 0:
                if failure == "midstream":
                    raise MidStreamFallbackError(
                        message="synthetic interruption", model="synthetic", llm_provider="openai",
                    )
                if failure == "timeout":
                    raise httpx.ReadTimeout("synthetic interruption")
                return
            yield ResponseTextDeltaEvent.model_construct(
                type="response.output_text.delta", item_id="msg-final", output_index=0,
                content_index=0, delta="ok", sequence_number=72,
            )
            response.status = "completed"
            message = ResponseOutputMessage.model_construct(
                id="msg-final", type="message", role="assistant", status="completed",
                content=[ResponseOutputText.model_construct(
                    type="output_text", text="ok", annotations=[],
                )],
            )
            yield ResponseOutputItemDoneEvent.model_construct(
                type="response.output_item.done", output_index=1,
                item=message, sequence_number=73,
            )
            response.output = [] if empty_final_output else [reasoning, message]
            yield ResponseCompletedEvent.model_construct(
                type="response.completed", response=response, sequence_number=74,
            )
        finally:
            closed.append(attempt)

    wrapper = ModelWrapper(SimpleNamespace(model="synthetic", stream_response=stream))
    result = Runner.run_streamed(
        Agent(name="ReasoningRetryTest", model=wrapper), input="hello",
        run_config=RunConfig(tracing_disabled=True),
    )
    raw = [event.data async for event in result.stream_events()
           if event.type == "raw_response_event"]
    assert attempts == closed == [0, 1]
    assert result.final_output == "ok"
    assert [event.response.id for event in raw if event.type == "response.created"] == [
        "resp-0", "resp-1",
    ]
    assert [event.delta for event in raw if event.type == "response.reasoning_summary_text.delta"] == [
        f"thinking-{attempt}-{index}" for attempt in range(2) for index in range(70)
    ]
    assert [event.delta for event in raw if event.type == "response.output_text.delta"] == ["ok"]
    assert [event.item.id for event in raw if event.type == "response.output_item.done"] == [
        "think-1", "msg-final",
    ]
    assert [item.raw_item.id for item in result.new_items] == ["think-1", "msg-final"]
    retry._backoff.assert_awaited_once()