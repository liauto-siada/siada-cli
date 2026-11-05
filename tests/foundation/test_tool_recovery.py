"""Offline missing-tool recovery through the real SDK execution loop."""

import asyncio
import copy
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents import Agent, ApplyPatchTool, CustomTool, Model, RunConfig, Runner, function_tool
from agents.editor import ApplyPatchResult
from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseApplyPatchToolCall,
    ResponseCompletedEvent,
    ResponseCustomToolCall,
    ResponseFunctionToolCall,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
)

from siada.foundation.agent_logging import LoggingRunner
from siada.foundation.sdk_patches import configure_sdk_run_config
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper


def _function_call(name, call_id="missing", arguments="{}"):
    return ResponseFunctionToolCall(
        type="function_call", id=f"item-{call_id}", call_id=call_id,
        name=name, arguments=arguments,
    )


def _missing_call(kind, call_id="missing"):
    operation = {"type": "create_file", "path": "synthetic.txt", "diff": "+test"}
    if kind in {"native", "native_dict"}:
        call = ResponseApplyPatchToolCall(
            type="apply_patch_call", id=f"item-{call_id}", call_id=call_id,
            status="completed", operation=operation,
        )
        return call.model_dump(exclude_unset=True) if kind == "native_dict" else call
    if kind in {"custom_patch", "custom_unknown"}:
        return ResponseCustomToolCall(
            type="custom_tool_call", id=f"item-{call_id}", call_id=call_id,
            name="apply_patch" if kind == "custom_patch" else "unavailable_custom",
            input="not valid JSON",
        )
    return _function_call(
        "apply_patch" if kind == "function_patch" else "unavailable_function",
        call_id=call_id, arguments="not valid JSON",
    )


def _final_message():
    return ResponseOutputMessage(
        type="message", id="final", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text="done", annotations=[])],
    )


class ScriptedModel(Model):
    """Replay responses without touching a provider, credentials, or network."""

    def __init__(self, steps):
        self.steps = deque(steps)
        self.requests = []
        self.closed = []

    def _next(self, input, tools):
        self.requests.append({"input": copy.deepcopy(input), "tools": list(tools)})
        assert self.steps, "Unexpected extra model request"
        return self.steps.popleft()

    async def get_response(self, system_instructions, input, model_settings, tools, *args, **kwargs):
        return ModelResponse(
            output=self._next(input, tools), usage=Usage(), response_id=None,
        )

    async def stream_response(self, system_instructions, input, model_settings, tools, *args, **kwargs):
        output = self._next(input, tools)
        try:
            for index, item in enumerate(output):
                if isinstance(item, dict):
                    item = ResponseApplyPatchToolCall.model_validate(item)
                yield ResponseOutputItemDoneEvent(
                    type="response.output_item.done", sequence_number=index,
                    output_index=index, item=item,
                )
            yield ResponseCompletedEvent(
                type="response.completed", sequence_number=len(output),
                response=Response(
                    id=f"response-{len(self.requests)}", created_at=0,
                    model="synthetic", object="response", output=output,
                    parallel_tool_calls=True, tool_choice="auto", tools=[],
                ),
            )
        finally:
            self.closed.append(len(self.requests))


async def _run(agent, config, *, stream, session=None, max_turns=8):
    kwargs = dict(input="start", run_config=config, session=session, max_turns=max_turns)
    if stream:
        result = LoggingRunner.run_streamed(agent, **kwargs)
        events = [event async for event in result.stream_events()]
    else:
        result = await LoggingRunner.run(agent, **kwargs)
        events = []
    return result, events


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", [
    "native", "native_dict", "function_patch", "custom_patch",
    "function_unknown", "custom_unknown",
])
async def test_missing_tool_returns_inventory_and_continues_without_replaying(
    tmp_path, monkeypatch, stream, kind,
):
    calls = []
    @function_tool
    async def edit_file(value: str) -> str:
        """Record a synthetic edit."""
        calls.append(value)
        return "edited"

    @function_tool(is_enabled=False)
    def disabled_tool() -> str:
        """A disabled tool must not appear in recovery hints."""
        raise AssertionError("Disabled tool executed")

    @function_tool
    def mcp_lookup() -> str:
        """A synthetic MCP tool."""
        return "found"

    get_mcp_tools = AsyncMock(return_value=[mcp_lookup])
    monkeypatch.setattr(Agent, "get_mcp_tools", get_mcp_tools)
    model = ScriptedModel([
        [_missing_call(kind), _function_call("edit_file", "valid", json.dumps({"value": "once"}))],
        [_final_message()],
    ])
    agent = Agent(name="recovery", model=model, tools=[edit_file, disabled_tool])
    session = FileSession("synthetic", sessions_dir=tmp_path)
    config = RunConfig(tracing_disabled=True)
    result, events = await _run(agent, config, stream=stream, session=session)

    assert result.final_output == "done"
    assert calls == ["once"]
    assert len(model.requests) == 2
    # Inventory formatting must not trigger a separate MCP fetch.
    assert get_mcp_tools.await_count == len(model.requests)
    assert all(request["tools"] == [mcp_lookup, edit_file] for request in model.requests)
    outputs = [item for item in model.requests[1]["input"]
               if item.get("call_id") == "missing" and item["type"].endswith("output")]
    assert len(outputs) == 1
    error = outputs[0]
    assert "not found" in error["output"]
    assert "Available tools" in error["output"]
    assert "edit_file" in error["output"] and "mcp_lookup" in error["output"]
    assert "disabled_tool" not in error["output"]
    if kind.startswith("native"):
        assert error["type"] == "apply_patch_call_output"
        assert error["status"] == "failed"
    elif kind.startswith("custom"):
        assert error["type"] == "custom_tool_call_output"
    else:
        assert error["type"] == "function_call_output"
    history = await session.get_items()
    assert sum(item.get("call_id") == "missing" and item["type"].endswith("output")
               for item in history) == 1
    assert not (tmp_path / "synthetic.txt").exists()
    assert config.tool_not_found_behavior == "raise_error"
    if kind.startswith("custom"):
        from agents.models.chatcmpl_converter import Converter

        native_wrapper = ModelWrapper(SimpleNamespace(supports_native_responses_items=True))
        assert native_wrapper._process_input(history) is history
        converted = ModelWrapper(SimpleNamespace(model="gpt-4o"))._process_input(history)
        messages = Converter.items_to_messages(converted)
        assert any(message.get("tool_call_id") == "missing" for message in messages)
        assert sum(item.get("type") == "custom_tool_call_output" for item in await session.get_items()) == 1
    if stream:
        assert model.closed == [1, 2]
        assert any(event.type == "run_item_stream_event" and event.name == "tool_output"
                   for event in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_registered_native_patch_still_uses_its_editor(stream):
    editor = AsyncMock()
    editor.create_file.return_value = ApplyPatchResult(status="completed", output="saved")
    tool = ApplyPatchTool(editor=editor)
    model = ScriptedModel([[_missing_call("native")], [_final_message()]])
    agent = Agent(name="registered", model=model, tools=[tool])
    result, _ = await _run(agent, RunConfig(tracing_disabled=True), stream=stream)
    assert result.final_output == "done"
    editor.create_file.assert_awaited_once()
    assert model.requests[1]["input"][-1]["output"] == "saved"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("call_type", ["custom", "function"])
@pytest.mark.parametrize("tool_name,call_name", [
    ("workspace_patch", "workspace_patch"), ("workspace_patch", " WORKSPACE_PATCH "),
    ("apply_patch", "apply_patch_v2"), ("apply_patch", "APPLY_PATCH"),
])
async def test_registered_patch_aliases_use_sdk_dispatch(stream, call_type, tool_name, call_name):
    editor = AsyncMock()
    editor.create_file.return_value = ApplyPatchResult(status="completed", output="saved")
    operation = {"type": "create_file", "path": "a.py", "diff": "+test"}
    payload = json.dumps({"operation": operation} if call_type == "custom" else operation)
    if call_type == "custom":
        call = ResponseCustomToolCall(
            type="custom_tool_call", id="alias", call_id="alias", name=call_name, input=payload,
        )
    else:
        call = _function_call(call_name, "alias", payload)
    model = ScriptedModel([[call], [_final_message()]])
    tool = ApplyPatchTool(name=tool_name, editor=editor)
    result, _ = await _run(Agent(name="alias", model=model, tools=[tool]),
                           RunConfig(tracing_disabled=True), stream=stream)
    assert result.final_output == "done"
    editor.create_file.assert_awaited_once()
    assert model.requests[1]["input"][-1]["output"] == "saved"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_real_custom_tool_keeps_priority_over_patch_alias(stream):
    editor = AsyncMock()
    invoke = AsyncMock(return_value="custom wins")
    custom = CustomTool(name="apply_patch_v2", description="Synthetic", on_invoke_tool=invoke)
    call = ResponseCustomToolCall(
        type="custom_tool_call", id="custom-priority", call_id="custom-priority",
        name="apply_patch_v2", input="raw input",
    )
    model = ScriptedModel([[call], [_final_message()]])
    agent = Agent(name="priority", model=model, tools=[ApplyPatchTool(editor=editor), custom])
    await _run(agent, RunConfig(tracing_disabled=True), stream=stream)
    invoke.assert_awaited_once()
    editor.create_file.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", ["custom_patch", "custom_unknown"])
async def test_recovered_custom_history_survives_chat_session_resume(tmp_path, stream, kind):
    from agents.models.chatcmpl_converter import Converter

    session = FileSession("custom-replay", sessions_dir=tmp_path)
    responses_model = ScriptedModel([[_missing_call(kind)], [_final_message()]])
    result, _ = await _run(Agent(name="responses", model=responses_model),
                           RunConfig(tracing_disabled=True), stream=stream, session=session)
    assert result.final_output == "done"
    native_history = copy.deepcopy(await session.get_items())

    class ChatReplayModel(ScriptedModel):
        def _next(self, input, tools):
            self.messages = Converter.items_to_messages(input)
            return super()._next(input, tools)

    chat_model = ChatReplayModel([[_final_message()]])
    result, _ = await _run(Agent(name="chat", model=ModelWrapper(chat_model)),
                           RunConfig(tracing_disabled=True), stream=stream, session=session)
    assert result.final_output == "done"
    assert any(message.get("tool_call_id") == "missing" for message in chat_model.messages)
    assert (await session.get_items())[:len(native_history)] == native_history


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_repeated_missing_tools_still_obey_max_turns(stream):
    model = ScriptedModel([[_missing_call("native", f"missing-{i}")] for i in range(3)])
    agent = Agent(name="bounded", model=model)
    with pytest.raises(MaxTurnsExceeded):
        await _run(agent, RunConfig(tracing_disabled=True), stream=stream, max_turns=2)
    assert len(model.requests) == 2
    assert "No tools are currently available" in model.requests[1]["input"][-1]["output"]


@pytest.mark.asyncio
async def test_configured_recovery_preserves_custom_error_formatter():
    formatter = AsyncMock(return_value="synthetic custom error")
    model = ScriptedModel([[_missing_call("native")], [_final_message()]])
    agent = Agent(name="custom-formatter", model=model)
    original = RunConfig(tracing_disabled=True, tool_error_formatter=formatter)
    config = configure_sdk_run_config(original)
    result, _ = await _run(agent, config, stream=False)
    assert result.final_output == "done"
    formatter.assert_awaited_once()
    assert formatter.call_args.args[0].kind == "tool_not_found"
    assert formatter.call_args.args[0].tool_type == "apply_patch"
    assert model.requests[1]["input"][-1]["output"] == "synthetic custom error"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_concurrent_runs_do_not_share_tool_inventory(stream):
    async def run(label):
        @function_tool(name_override=f"tool_{label}")
        def tool() -> str:
            """Synthetic tool for one run."""
            return label

        model = ScriptedModel([[_missing_call("native")], [_final_message()]])
        agent = Agent(name=label, model=model, tools=[tool])
        await _run(agent, RunConfig(tracing_disabled=True), stream=stream)
        return model.requests[1]["input"][-1]["output"]

    first, second = await asyncio.gather(run("first"), run("second"))
    assert "tool_first" in first and "tool_second" not in first
    assert "tool_second" in second and "tool_first" not in second


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "custom_unknown", "function_patch"])
async def test_unconfigured_sdk_runs_still_raise_for_missing_tools(kind):
    configure_sdk_run_config()
    model = ScriptedModel([[_missing_call(kind)]])
    agent = Agent(name="strict", model=model)
    with pytest.raises(ModelBehaviorError):
        await Runner.run(agent, input="start", run_config=RunConfig(tracing_disabled=True))
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["native", "custom_unknown", "function_unknown"])
async def test_missing_call_id_still_fails_before_valid_sibling_executes(kind):
    called = AsyncMock(return_value="unexpected")

    @function_tool
    async def valid() -> str:
        """A sibling that must not execute after invalid invocation metadata."""
        return await called()

    missing = _missing_call(kind, "")
    model = ScriptedModel([[missing, _function_call("valid", "valid-call")]])
    agent = Agent(name="invalid-id", model=model, tools=[valid])
    with pytest.raises(ModelBehaviorError, match="call ID"):
        await _run(agent, RunConfig(tracing_disabled=True), stream=False)
    called.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_registered_custom_tool_is_not_replaced(stream):
    invoke = AsyncMock(return_value="custom saved")
    tool = CustomTool(name="unavailable_custom", description="Synthetic", on_invoke_tool=invoke)
    model = ScriptedModel([[_missing_call("custom_unknown")], [_final_message()]])
    agent = Agent(name="registered-custom", model=model, tools=[tool])
    result, _ = await _run(agent, RunConfig(tracing_disabled=True), stream=stream)
    assert result.final_output == "done"
    invoke.assert_awaited_once()
    assert model.requests[1]["input"][-1]["output"] == "custom saved"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_formatter_failure_uses_default_feedback(stream):
    formatter = AsyncMock(side_effect=ValueError("synthetic formatter failure"))
    model = ScriptedModel([[_missing_call("native")], [_final_message()]])
    agent = Agent(name="fallback", model=model)
    result, _ = await _run(
        agent, RunConfig(tracing_disabled=True, tool_error_formatter=formatter), stream=stream,
    )
    assert result.final_output == "done"
    assert "No tools are currently available" in model.requests[1]["input"][-1]["output"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("alias", [False, True])
async def test_registered_patch_approval_is_not_bypassed(stream, alias):
    editor = AsyncMock()
    tool = ApplyPatchTool(editor=editor, needs_approval=True)
    call = _missing_call("native")
    if alias:
        call = ResponseCustomToolCall(
            type="custom_tool_call", id="approval-alias", call_id="approval-alias",
            name="APPLY_PATCH_v2", input=json.dumps({"operation": {
                "type": "create_file", "path": "a.py", "diff": "+test",
            }}),
        )
    model = ScriptedModel([[call]])
    agent = Agent(name="approval", model=model, tools=[tool])
    result, _ = await _run(agent, RunConfig(tracing_disabled=True), stream=stream)
    assert len(result.interruptions) == 1
    editor.create_file.assert_not_awaited()
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_recovery_cancellation_propagates_and_does_not_leak_inventory(stream):
    started = asyncio.Event()

    async def blocked_formatter(args):
        started.set()
        await asyncio.Event().wait()

    @function_tool
    def previous_tool() -> str:
        """Synthetic tool visible only to the cancelled run."""
        return "previous"

    model = ScriptedModel([[_missing_call("native")]])
    agent = Agent(name="cancelled", model=model, tools=[previous_tool])
    task = asyncio.create_task(_run(
        agent, RunConfig(tracing_disabled=True, tool_error_formatter=blocked_formatter), stream=stream,
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert len(model.requests) == 1
    if stream:
        assert model.closed == [1]

    next_model = ScriptedModel([[_missing_call("native")], [_final_message()]])
    next_agent = Agent(name="next-run", model=next_model)
    result, _ = await _run(next_agent, RunConfig(tracing_disabled=True), stream=stream)
    assert result.final_output == "done"
    output = next_model.requests[1]["input"][-1]["output"]
    assert "No tools are currently available" in output
    assert "previous_tool" not in output