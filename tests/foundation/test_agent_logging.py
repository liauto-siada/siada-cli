"""Runner configuration compatibility and provider ownership, without network calls."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from agents import Agent, RunConfig, Runner
from agents.models.multi_provider import MultiProvider
from agents.testing import ScriptedModel, assistant_message
from openai.types.responses import ResponseFunctionToolCall

from siada.foundation.agent_logging import LoggingRunner


@pytest.fixture(autouse=True)
def disable_tracing(monkeypatch):
    monkeypatch.setenv("OPENAI_AGENTS_DISABLE_TRACING", "1")


async def run_agent(runner, agent, stream, **kwargs):
    if stream:
        result = runner.run_streamed(agent, input="synthetic", **kwargs)
        async for _ in result.stream_events():
            pass
        return result
    return await runner.run(agent, input="synthetic", **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_logging_runner_accepts_dictionary_config_without_mutation(stream):
    model = ScriptedModel([[assistant_message("done")]])
    agent = Agent(name="dictionary", model=model)
    config = {"tracing_disabled": True, "workflow_name": "synthetic",
              "model_settings": {"temperature": 0.2}}
    original = deepcopy(config)
    result = await run_agent(LoggingRunner, agent, stream, run_config=config)
    assert result.final_output == "done"
    assert config == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_dictionary_config_keeps_missing_tool_recovery_enabled(stream):
    call = ResponseFunctionToolCall(
        type="function_call", id="missing", call_id="missing",
        name="unavailable", arguments="{}",
    )
    model = ScriptedModel([[call], [assistant_message("done")]])
    config = {"tracing_disabled": True}
    result = await run_agent(LoggingRunner, Agent(name="recovery", model=model), stream, run_config=config)
    assert result.final_output == "done"
    assert model.last_call.input[-1]["call_id"] == "missing"
    assert "No tools are currently available" in model.last_call.input[-1]["output"]
    assert config == {"tracing_disabled": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", [Runner, LoggingRunner])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("config_kind", [
    "omitted", "none", "dictionary", "object", "explicit-provider", "explicit-provider-object",
])
@pytest.mark.parametrize("failure", [False, True])
async def test_provider_cleanup_matches_sdk_ownership(monkeypatch, runner, stream, config_kind, failure):
    model = ScriptedModel([RuntimeError("synthetic failure")] if failure else [[assistant_message("done")]])
    close = AsyncMock()
    monkeypatch.setattr(MultiProvider, "get_model", lambda self, name: model)
    monkeypatch.setattr(MultiProvider, "aclose", close)
    kwargs = {}
    if config_kind == "none":
        kwargs["run_config"] = None
    elif config_kind == "dictionary":
        kwargs["run_config"] = {"tracing_disabled": True}
    elif config_kind == "object":
        kwargs["run_config"] = RunConfig(tracing_disabled=True)
    elif config_kind == "explicit-provider":
        kwargs["run_config"] = {"tracing_disabled": True, "model_provider": MultiProvider()}
    elif config_kind == "explicit-provider-object":
        kwargs["run_config"] = RunConfig(tracing_disabled=True, model_provider=MultiProvider())
    agent = Agent(name="ownership", model="synthetic-model")
    if failure:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            await run_agent(runner, agent, stream, **kwargs)
    else:
        result = await run_agent(runner, agent, stream, **kwargs)
        assert result.final_output == "done"
    assert close.await_count == (1 if config_kind in {"omitted", "none", "dictionary"} else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_explicit_dictionary_settings_remain_caller_owned_across_runs(monkeypatch, stream):
    model = ScriptedModel([[assistant_message("done")], [assistant_message("done")]])
    provider = MultiProvider()
    formatter = lambda args: "caller feedback"
    config = {"tracing_disabled": True, "model_provider": provider,
              "model_settings": {"temperature": 0.2}, "tool_error_formatter": formatter}
    original = dict(config)
    close = AsyncMock()
    monkeypatch.setattr(MultiProvider, "get_model", lambda self, name: model)
    monkeypatch.setattr(MultiProvider, "aclose", close)
    agent = Agent(name="shared", model="synthetic-model")
    for _ in range(2):
        result = await run_agent(LoggingRunner, agent, stream, run_config=config)
        assert result.final_output == "done"
    assert all(call.model_settings.temperature == 0.2 for call in model.calls)
    assert config == original
    assert config["model_provider"] is provider
    assert config["tool_error_formatter"] is formatter
    close.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", [Runner, LoggingRunner])
@pytest.mark.parametrize("stream", [False, True])
async def test_implicit_provider_cleanup_survives_cancellation(monkeypatch, runner, stream):
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def blocked_response(call):
        started.set()
        await asyncio.Event().wait()

    model = ScriptedModel([{"responder": blocked_response}])
    close = AsyncMock(side_effect=lambda: cleaned.set())
    monkeypatch.setattr(MultiProvider, "get_model", lambda self, name: model)
    monkeypatch.setattr(MultiProvider, "aclose", close)
    task = asyncio.create_task(run_agent(
        runner, Agent(name="cancelled", model="synthetic-model"), stream,
        run_config={"tracing_disabled": True},
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    # Streaming cancellation schedules provider cleanup on producer completion.
    await asyncio.wait_for(cleaned.wait(), timeout=3)
    close.assert_awaited_once()