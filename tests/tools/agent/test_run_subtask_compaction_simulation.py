"""Offline regressions for run-scoped input admission and SDK compaction."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest
from agents.run_config import CallModelData, ModelInputData

import siada.tools.agent.sub_agent_compaction_filter as mod
from agents import Agent
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult
from siada.tools.agent.sub_agent_compaction_filter import InMemorySession
from tests.tools.agent.test_sub_agent_compaction_e2e import (
    _ScriptedModel, _build_run_config, _make_model_run_config,
    _run_agent, _text, _tool_call, record_tool,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("fork", [False, True])
async def test_first_compaction_does_not_restore_original_input(streamed, fork):
    session = InMemorySession()
    history = [{"role": "user", "content": "repeat"},
               {"role": "assistant", "content": "answer"}] * 2
    if fork:
        await session.add_items(history)
    model = _ScriptedModel([[_tool_call("c1", "n1")], [_text("done")]])
    agent = Agent(name="synthetic", model=model, tools=[record_tool])
    config = _build_run_config(session, _make_model_run_config())
    summary = [{"role": "user", "content": "[[SUMMARY]]"}]
    with patch.object(mod, "calculate_tokens", side_effect=[900, 10]), \
         patch.object(mod._STRATEGY, "compact", new=AsyncMock(
             return_value=CompactionResult(messages=summary, compacted=True))):
        result = await _run_agent(agent, session, config, streamed=streamed)
    assert result.final_output == "done"
    assert model.received_inputs[0] == summary
    for items in [*model.received_inputs, await session.get_items()]:
        assert {"role": "user", "content": "start"} not in items
    items = await session.get_items()
    assert len(items) == 4
    assert items[1]["call_id"] == items[2]["call_id"] == "c1"


@pytest.mark.parametrize("streamed", [False, True])
async def test_repeated_fork_history_and_twelve_new_inputs_are_preserved(streamed):
    session = InMemorySession()
    history = [{"role": "user", "content": "repeat"},
               {"role": "assistant", "content": "answer"}] * 2
    await session.add_items(history)
    for index in range(12):
        model = _ScriptedModel([[_text("done", f"msg-{index}")]])
        agent = Agent(name="synthetic", model=model)
        config = _build_run_config(session, _make_model_run_config())
        with patch.object(mod, "calculate_tokens", return_value=10):
            await _run_agent(agent, session, config, streamed=streamed, input="repeat")
        assert model.received_inputs[0][:4] == history
    items = await session.get_items()
    assert len(items) == 28
    assert sum(item.get("content") == "repeat" for item in items) == 14


@pytest.mark.parametrize("streamed", [False, True])
async def test_model_failure_after_compaction_retry_keeps_summary(streamed):
    session = InMemorySession()
    config = _build_run_config(session, _make_model_run_config())
    summary = [{"role": "user", "content": "[[SUMMARY]]"}]
    failed = Agent(name="synthetic", model=_ScriptedModel([RuntimeError("synthetic failure")]))
    with patch.object(mod, "calculate_tokens", return_value=900), \
         patch.object(mod._STRATEGY, "compact", new=AsyncMock(
             return_value=CompactionResult(messages=summary, compacted=True))):
        with pytest.raises(RuntimeError, match="synthetic failure"):
            await _run_agent(failed, session, config, streamed=streamed)
    assert await session.get_items() == summary
    model = _ScriptedModel([[_text("recovered")]])
    with patch.object(mod, "calculate_tokens", return_value=10):
        result = await _run_agent(Agent(name="retry", model=model), session, config,
                                  streamed=streamed)
    assert result.final_output == "recovered"
    assert model.received_inputs == [summary]


@pytest.mark.parametrize("width", [1, 3])
async def test_real_token_compaction_preserves_latest_parallel_group(width):
    strategy = mod._STRATEGY
    config = SimpleNamespace(model_name="gpt-4o", context_window=6000)
    old = [{"role": role, "content": f"old {index} " * 80}
           for index in range(20) for role in ("user", "assistant")]
    old += [{"role": "user", "content": "recent task"}]
    calls = [{"type": "function_call", "call_id": f"c{index}",
              "name": "synthetic", "arguments": "{}"} for index in range(width)]
    outputs = [{"type": "function_call_output", "call_id": f"c{index}",
                "output": "recent result"} for index in reversed(range(width))]
    items = old + calls + outputs
    with patch.object(strategy, "call_llm_to_compact", new=AsyncMock(
            return_value="synthetic summary")):
        result = await strategy.compact(config, items)
    assert result.compacted
    assert result.messages[-len(calls + outputs):] == calls + outputs


async def test_oversized_latest_group_failure_preserves_session():
    session = InMemorySession()
    callback = mod.make_sub_agent_session_input_callback(session)
    new = [{"role": "user", "content": "task"}]
    await callback([], new)
    config = _make_model_run_config()
    data = CallModelData(
        model_data=ModelInputData(input=new, instructions="test"),
        agent=MagicMock(), context=MagicMock(),
    )
    with patch.object(mod, "calculate_tokens", return_value=900), \
         patch.object(mod._STRATEGY, "compact", new=AsyncMock(
             side_effect=ValueError("No messages to keep after trimming"))):
        filtered = await mod.make_sub_agent_compaction_filter(config, session)(data)
    assert filtered.input == new
    assert await session.get_items() == new
    await session.add_items(new)
    assert await session.get_items() == new


async def test_cancelled_compaction_can_retry_without_duplicate_admission():
    session = InMemorySession()
    callback = mod.make_sub_agent_session_input_callback(session)
    new = [{"role": "user", "content": "task"}]
    await callback([], new)
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    data = CallModelData(
        model_data=ModelInputData(input=new, instructions="test"),
        agent=MagicMock(), context=MagicMock(),
    )
    config = _make_model_run_config()
    filtered = mod.make_sub_agent_compaction_filter(config, session)
    with patch.object(mod, "calculate_tokens", return_value=900), \
         patch.object(mod._STRATEGY, "compact", side_effect=blocked):
        task = asyncio.create_task(filtered(data))
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert await session.get_items() == new
    await callback(new, new)
    await session.add_items(new)
    assert await session.get_items() == new


@pytest.mark.parametrize("streamed", [False, True])
async def test_concurrent_sessions_and_multiple_replacements_remain_isolated(streamed):
    async def execute(identity):
        session = InMemorySession()
        for index in range(3):
            config = _build_run_config(session, _make_model_run_config())
            summary = [{"role": "user", "content": f"summary-{identity}-{index}"}]
            await config.session_input_callback([], [{"role": "user", "content": identity}])
            await session.replace_context_items(summary)
            # Simulate the SDK's original-input save after replacement.
            await session.add_items([{"role": "user", "content": identity}])
            assert await session.get_items() == summary
        model = _ScriptedModel([[_text(f"done-{identity}")]])
        config = _build_run_config(session, _make_model_run_config())
        await _run_agent(Agent(name=identity, model=model), session, config,
                         streamed=streamed, input=f"continue-{identity}")
        return identity, await session.get_items()

    with patch.object(mod, "calculate_tokens", return_value=10):
        results = await asyncio.gather(execute("alpha"), execute("beta"))
    for identity, items in results:
        assert items[0]["content"] == f"summary-{identity}-2"
        assert items[1]["content"] == f"continue-{identity}"
        assert len(items) == 3