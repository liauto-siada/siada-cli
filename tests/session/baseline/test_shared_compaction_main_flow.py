"""Regression coverage for shared compaction boundaries in prepared sessions."""

from unittest.mock import patch

import pytest
from agents import RunConfig

from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import (
    TurnPruneSummaryCompaction,
)
from tests.session.baseline.test_default_context_cutover import run_default


def _group(identity, width, native):
    calls = [
        {"type": "apply_patch_call" if native else "function_call",
         "call_id": f"{identity}-{index}", "name": "synthetic", "arguments": "{}",
         "operation": {"type": "update_file", "path": "synthetic.py", "diff": "@@"}}
        for index in range(width)
    ]
    results = [
        {"type": "apply_patch_call_output" if native else "function_call_output",
         "call_id": f"{identity}-{index}", "output": "synthetic result"}
        for index in reversed(range(width))
    ]
    return calls + results


@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("width", [1, 3])
def test_parallel_groups_and_kept_tail_repair(strategy_type, native, width):
    strategy = strategy_type()
    old = _group("old", width, native)
    latest = _group("latest", width, native)
    items = old + latest
    assert strategy._identify_tool_call_groups(items) == [
        (0, len(old)), (len(old), len(items))]
    with patch.object(strategy, "_count_tokens", side_effect=lambda messages, _: len(messages)):
        kept = strategy._trim_kept_history(items, None, len(latest))
    assert kept == latest
    assert strategy._repair_tool_pairs(latest, require_user_start=False) == latest
    assert strategy._repair_tool_pairs(latest) == []
    complete = [{"role": "user", "content": "header"}] + latest
    assert strategy._repair_tool_pairs(complete) == complete


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("width", [2, 4])
def test_end_boundary_retreats_before_entire_parallel_group(native, width):
    strategy = SummarizeWithHeaderCompaction()
    items = [{"role": "user", "content": "header"}] + _group("latest", width, native)
    assert strategy.adjust_compression_index_for_boundary_cases(items, len(items)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_main_prepared_session_commits_and_replays_repaired_tail(baseline, stream, native):
    session = baseline.session()
    store = session.openai_session
    strategy = SummarizeWithHeaderCompaction()
    header = [{"role": "user", "content": "header"}]
    old = _group("old", 2, native)
    latest = _group("latest", 2, native)
    await store.add_items(header + old + latest)
    await store.migrate_legacy_context(allow_history_only=True)
    snapshots = []

    async def compact(data):
        items = data.model_data.input
        # The main-session bridge owns admission and durable replacement.
        with patch.object(strategy, "_count_tokens", side_effect=lambda messages, _: len(messages)):
            tail = strategy._trim_kept_history(old + latest, None, len(latest))
        effective = strategy.create_compressed_message_history(header, "synthetic summary", tail)
        effective += items[-1:]
        snapshots.append(effective)
        return type(data.model_data)(input=effective, instructions=data.model_data.instructions)

    model = baseline.model(session, [[baseline.text("answer")]])
    config = RunConfig(tracing_disabled=True, call_model_input_filter=compact)
    await run_default(baseline, session, model, stream=stream, config=config)
    persisted = await store.get_items()
    assert persisted[:len(snapshots[0])] == snapshots[0]
    assert not any(item.get("call_id", "").startswith("old-") for item in persisted)
    assert sum(item.get("call_id", "").startswith("latest-") for item in persisted) == 4
    assert (await store.get_history_items())[:len(header + old + latest)] == header + old + latest