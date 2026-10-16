"""Offline recovery tests, including real SDK streaming and tool persistence."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from agents import Model, RunConfig, function_tool
from openai import APIStatusError, PermissionDeniedError
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from siada.foundation.code_agent_context import CodeAgentContext
from siada.provider import retry as model_retry
from siada.services.model_wrapper import ModelWrapper
from siada.tools.agent import run_subtask as subtask
from siada.tools.agent import subagent_async
from siada.tools.agent.subagent_persistence import subagents_dir
from siada.utils import DirectoryUtils
from tests.tools.agent.test_run_subtask_reasoning_retry import (
    _MockedSubtaskRun,
    _reasoning_only_result,
    _stream_that_raises,
    _text_result,
)


@pytest.fixture
def no_delay(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(subtask.asyncio, "sleep", sleep)
    return sleep


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("synthetic timeout"),
    httpx.RemoteProtocolError("synthetic disconnect"),
    subtask.MissingFinalResponseError(
        model="synthetic", response_id="response-1",
        last_event="response.output_text.delta", output_exposed=True,
    ),
    APIStatusError(
        "synthetic unavailable",
        response=httpx.Response(503, request=httpx.Request("POST", "https://model.test")),
        body=None,
    ),
    PermissionDeniedError(
        "synthetic authentication failure",
        response=httpx.Response(403, request=httpx.Request("POST", "https://model.test")),
        body={"error": "Authentication failed", "code": 403},
    ),
])
async def test_transient_failure_continues_without_terminal_failure(error, no_delay):
    failed = _text_result()
    failed.stream_events = _stream_that_raises(error)
    with _MockedSubtaskRun([failed, _text_result("Recovered.")], with_definition=True) as run:
        assert await run.run() == "Recovered."
    assert run.run_streamed.call_count == 2
    assert run.subtask_agent.call_count == 1
    assert run.finish_statuses == ["completed"]
    assert run.mcp_servers.enter_count == run.mcp_servers.exit_count == 1
    assert run.streamed_kwargs[0]["session"] is run.streamed_kwargs[1]["session"]
    no_delay.assert_awaited_once_with(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    ValueError("invalid configuration"),
    RuntimeError("Event loop is closed"),
    asyncio.CancelledError(),
    APIStatusError(
        "synthetic unauthorized",
        response=httpx.Response(401, request=httpx.Request("POST", "https://model.test")),
        body=None,
    ),
])
async def test_non_transient_failure_is_not_retried(error, no_delay):
    failed = _text_result()
    failed.stream_events = _stream_that_raises(error)
    with _MockedSubtaskRun([failed, _text_result("Unexpected.")], with_definition=True) as run:
        with pytest.raises(type(error)) as caught:
            await run.run()
    assert caught.value is error
    assert run.run_streamed.call_count == 1
    assert run.finish_statuses == ["failed"]
    assert run.mcp_servers.exit_count == 1
    no_delay.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_failure", [False, True], ids=["timeout", "403"])
async def test_retry_budget_preserves_final_exception_and_closes_mcp(no_delay, auth_failure):
    errors = [
        PermissionDeniedError(
            f"synthetic-{index}",
            response=httpx.Response(403, request=httpx.Request("POST", "https://model.test")),
            body={"error": "Authentication failed", "code": 403},
        ) if auth_failure else httpx.ReadTimeout(f"synthetic-{index}")
        for index in range(3)
    ]
    results = [_text_result() for _ in errors]
    for result, error in zip(results, errors):
        result.stream_events = _stream_that_raises(error)
    with _MockedSubtaskRun(results, with_definition=True) as run:
        with pytest.raises(type(errors[-1])) as caught:
            await run.run()
    assert caught.value is errors[-1]
    assert run.run_streamed.call_count == 3
    assert run.finish_statuses == ["failed"]
    assert run.mcp_servers.exit_count == 1
    assert [call.args for call in no_delay.await_args_list] == [(1,), (2,)]


@pytest.mark.asyncio
async def test_cancellation_during_backoff_stops_recovery(monkeypatch):
    cancelled = asyncio.CancelledError()
    sleep = AsyncMock(side_effect=cancelled)
    monkeypatch.setattr(subtask.asyncio, "sleep", sleep)
    failed = _text_result()
    failed.stream_events = _stream_that_raises(httpx.ReadTimeout("synthetic"))
    with _MockedSubtaskRun([failed, _text_result("Unexpected.")], with_definition=True) as run:
        with pytest.raises(asyncio.CancelledError) as caught:
            await run.run()
    assert caught.value is cancelled
    assert run.run_streamed.call_count == 1
    assert run.finish_statuses == ["failed"]
    assert run.mcp_servers.exit_count == 1


@pytest.mark.asyncio
async def test_error_recovery_does_not_reset_reasoning_retry_budget(no_delay):
    failed = _text_result()
    failed.stream_events = _stream_that_raises(httpx.ReadTimeout("synthetic"))
    results = [
        _reasoning_only_result(), _reasoning_only_result(), failed,
        _reasoning_only_result(), _text_result("Unexpected."),
    ]
    with _MockedSubtaskRun(results) as run:
        with pytest.raises(RuntimeError, match="empty reasoning-only result"):
            await run.run()
    assert run.run_streamed.call_count == 4
    assert run.finish_statuses == ["failed"]


def _completed(output, call):
    return ResponseCompletedEvent(
        type="response.completed", sequence_number=0,
        response=Response(
            id=f"response-{call}", created_at=0, model="synthetic",
            object="response", output=output, parallel_tool_calls=False,
            tool_choice="auto", tools=[],
        ),
    )


class InterruptedModel(Model):
    """Complete a tool turn, then interrupt reasoning before the final answer."""

    model = "synthetic"
    supports_native_responses_items = True

    def __init__(self, with_tool=False, failure_mode="answer"):
        self.with_tool = with_tool
        self.failure_mode = failure_mode
        self.failures = 3 if failure_mode == "empty" else 1
        self.inputs = []
        self.closed = 0

    async def get_response(self, *args, **kwargs):
        raise AssertionError("Expected streaming")

    async def stream_response(
        self, system_instructions, input, model_settings, tools,
        output_schema, handoffs, tracing, **kwargs,
    ):
        self.inputs.append(input)
        call = len(self.inputs)
        try:
            if self.with_tool and call == 1:
                yield _completed([ResponseFunctionToolCall(
                    id="tool-item", call_id="completed-action",
                    name="record_action", arguments="{}", type="function_call",
                )], call)
            elif call <= self.failures + int(self.with_tool):
                if self.failure_mode != "empty":
                    yield ResponseReasoningSummaryTextDeltaEvent(
                        type="response.reasoning_summary_text.delta", sequence_number=0,
                        item_id="interrupted-reasoning", output_index=0, summary_index=0,
                        delta="Use the completed action and continue.",
                    )
                if self.failure_mode in {"answer", "eof"}:
                    yield ResponseTextDeltaEvent(
                        type="response.output_text.delta", sequence_number=1,
                        item_id="interrupted-message", output_index=1, content_index=0,
                        delta="Partial answer.", logprobs=[],
                    )
                if self.failure_mode == "eof":
                    return
                raise httpx.ReadTimeout("synthetic interruption")
            else:
                yield _completed([ResponseOutputMessage(
                    id=f"message-{call}", type="message", role="assistant",
                    status="completed", content=[ResponseOutputText(
                        type="output_text", text="Recovered.", annotations=[],
                    )],
                )], call)
        finally:
            self.closed += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("with_tool", [False, True])
@pytest.mark.parametrize("failure_mode", ["answer", "reasoning", "empty", "eof"])
async def test_real_sdk_continuation_preserves_tools_and_accounting(
    tmp_path, monkeypatch, no_delay, background, with_tool, failure_mode,
):
    actions = []

    @function_tool
    def record_action() -> str:
        """Record a synthetic action exactly once."""
        actions.append("done")
        return "action completed"

    monkeypatch.setattr(
        "siada.agent_hub.coder.sub_task_agent._build_default_tools",
        lambda **kwargs: [record_action] if with_tool else [],
    )
    monkeypatch.setattr(
        DirectoryUtils, "get_global_sessions_dir", lambda _: str(tmp_path / "sessions"),
    )
    if failure_mode == "reasoning":
        # Exercise subtask recovery independently of whether the provider
        # permits replay after reasoning. Empty streams still test exhaustion
        # of the provider's normal transport retry budget.
        monkeypatch.setattr(model_retry, "_MAX_RETRIES", 0)
    model = InterruptedModel(with_tool=with_tool, failure_mode=failure_mode)
    run_config = RunConfig(model=ModelWrapper(model), tracing_disabled=True)
    context = CodeAgentContext(
        root_dir=str(tmp_path), root_session_id="synthetic-recovery",
    )
    monkeypatch.setattr(subtask, "build_sub_agent_run_config", lambda *a, **k: run_config)
    notifications = []
    monkeypatch.setattr(
        "siada.services.session_runtime_state.stage_notification",
        lambda _context, note: notifications.append(note),
    )
    if background:
        task_id = subagent_async.register_background_subtask(
            context, lambda: subtask.run_subtask_impl("Do the assigned task.", context),
        )
        task = subagent_async._SESSION_TASKS[context.session_id or "unknown-session"][task_id]
        await asyncio.wait_for(task, timeout=5)
        assert len(notifications) == 1
        assert "completed" in notifications[0]
        assert "failed" not in notifications[0]
    else:
        assert await subtask.run_subtask_impl("Do the assigned task.", context) == "Recovered."

    assert actions == (["done"] if with_tool else [])
    assert len(model.inputs) == model.failures + int(with_tool) + 1
    assert model.closed == len(model.inputs)
    retry_input = model.inputs[-1]
    user_inputs = [item.get("content") for item in retry_input if item.get("role") == "user"]
    assert user_inputs.count("Do the assigned task.") == 1
    assert subtask._STREAM_ERROR_RETRY_INPUT in user_inputs
    if with_tool:
        assert sum(item.get("type") == "function_call" for item in retry_input) == 1
        outputs = [item for item in retry_input if item.get("type") == "function_call_output"]
        assert len(outputs) == 1
        assert outputs[0]["call_id"] == "completed-action"

    directory = subagents_dir(str(tmp_path), context.root_session_id)
    entries = json.loads((directory / "index.json").read_text())["agents"]
    assert len(entries) == 1
    entry = next(iter(entries.values()))
    assert entry["status"] == "completed"
    transcript = (directory / entry["log_file"]).read_text()
    assert transcript.count("REQUEST_RETRY") == 1
    assert transcript.count("Status: retrying") == 1
    assert transcript.count("SUB-AGENT USAGE SUMMARY") == 1
    assert "Status: completed" in transcript
