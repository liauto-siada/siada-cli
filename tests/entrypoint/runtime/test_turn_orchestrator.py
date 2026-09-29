"""Unit tests for the TurnOrchestrator (run_agent + TurnEvent pipeline)."""
from types import SimpleNamespace
from typing import Any

import pytest
from agents import RawResponsesStreamEvent
from openai.types.responses import (
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseTextDeltaEvent,
)

from siada.entrypoint.runtime.turn_event import (
    TEXT_DELTA,
    TOOL_ARGS_DELTA,
    TOOL_CALL_START,
    TurnEvent,
    translate_stream_events,
)
from siada.entrypoint.runtime.turn_orchestrator import TurnOrchestrator

_BASE = dict(logprobs=[], sequence_number=0)


class _FakeStreamResult:
    def __init__(self, events: list[Any]):
        self._events = events
        self.stream_started = False

    async def stream_events(self):
        self.stream_started = True
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_run_agent_turn_yields_translated_events(monkeypatch):
    events = [
        RawResponsesStreamEvent(data=ResponseTextDeltaEvent(
            type="response.output_text.delta", item_id="i1",
            output_index=0, content_index=0, delta="hello", **_BASE,
        )),
        SimpleNamespace(noise=True),
        RawResponsesStreamEvent(data=ResponseOutputItemAddedEvent(
            type="response.output_item.added", output_index=0,
            item=ResponseFunctionToolCall(
                id="item_1", call_id="call_1", name="run_cmd",
                arguments="{}", type="function_call", status="completed",
            ),
            sequence_number=0,
        )),
    ]
    fake_result = _FakeStreamResult(events)
    captured_kwargs: dict = {}

    async def fake_run_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_result

    monkeypatch.setattr(
        "siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent
    )

    orchestrator = TurnOrchestrator()
    session = SimpleNamespace(session_id="s1")
    received = [
        te async for te in orchestrator.run_agent_turn(
            session=session, user_input="<user_input>hi</user_input>",
            agent_name="coder", workspace="/tmp/w",
        )
    ]

    assert [te.kind for te in received] == [TEXT_DELTA, TOOL_CALL_START]
    assert received[0].delta == "hello"
    assert received[1].name == "run_cmd"
    assert captured_kwargs == dict(
        agent_name="coder",
        user_input="<user_input>hi</user_input>",
        workspace="/tmp/w",
        session=session,
        stream=True,
    )


@pytest.mark.asyncio
async def test_run_agent_turn_forwards_optional_kwargs(monkeypatch):
    fake_result = _FakeStreamResult([])
    captured_kwargs: dict = {}

    async def fake_run_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_result

    monkeypatch.setattr(
        "siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent
    )

    orchestrator = TurnOrchestrator()
    mcp_servers = [SimpleNamespace(name="browser")]
    async for _ in orchestrator.run_agent_turn(
        session=SimpleNamespace(), user_input="x", agent_name="coder",
        workspace="/tmp/w", extra_mcp_servers=mcp_servers,
        runtime_source="lark_controller",
    ):
        pass

    assert captured_kwargs["extra_mcp_servers"] is mcp_servers
    assert captured_kwargs["runtime_source"] == "lark_controller"


@pytest.mark.asyncio
async def test_run_agent_turn_propagates_run_agent_errors(monkeypatch):
    """run_agent fails lazily on first iteration, inside the caller's try."""
    calls: list[int] = []

    async def failing_run_agent(**kwargs):
        calls.append(1)
        raise RuntimeError("provider down")

    monkeypatch.setattr(
        "siada.services.siada_runner.SiadaRunner.run_agent", failing_run_agent
    )

    orchestrator = TurnOrchestrator()
    with pytest.raises(RuntimeError, match="provider down"):
        async for _ in orchestrator.run_agent_turn(
            session=SimpleNamespace(), user_input="x",
            agent_name="coder", workspace="/tmp/w",
        ):
            pass
    assert calls == [1]


@pytest.mark.asyncio
async def test_translate_stream_events_helper_composes_with_orchestrator_events():
    """The module-level helper stays the single translation entry point."""
    events = [
        RawResponsesStreamEvent(data=ResponseFunctionCallArgumentsDeltaEvent(
            type="response.function_call_arguments.delta", item_id="item_1",
            output_index=0, delta='{"a"', sequence_number=0,
        )),
    ]
    translated = [te async for te in translate_stream_events(iter_stream(events))]
    assert translated == [
        TurnEvent(kind=TOOL_ARGS_DELTA, item_id="item_1", delta='{"a"')
    ]


async def iter_stream(events):
    for event in events:
        yield event
