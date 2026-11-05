"""Simulate the public subtask entrypoint with real token counting and compaction."""

import asyncio
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import Agent, RunConfig, RunContextWrapper, Runner, function_tool
from agents.exceptions import MaxTurnsExceeded
from agents.items import ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall

from siada.agent_hub.context_filter import compaction_strategy as strategy_module
from siada.agent_hub.context_filter import compaction_threshold as threshold_module
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_run_config import ModelRunConfig
from siada.provider import provider_factory
from siada.provider.token_counting import TokenCountingInfo
from siada.services.file_session import FileSession
from siada.session.session_models import RunningSession
from siada.tools.agent import sub_agent_compaction_filter as compaction_module
from tests.tools.agent.test_sub_agent_compaction_e2e import (
    _ScriptedModel,
    _build_run_config,
    _run_agent,
    _text,
)


subtask_module = importlib.import_module("siada.tools.agent.run_subtask")
agent_module = importlib.import_module("siada.agent_hub.coder.sub_task_agent")


@pytest.fixture(autouse=True)
def synthetic_counting_provider(monkeypatch):
    provider = SimpleNamespace(get_token_counting_info=TokenCountingInfo)

    def resolve(provider_name):
        assert provider_name == "synthetic"
        return provider

    monkeypatch.setattr(provider_factory, "get_provider", resolve)


def _summary_response(text: str) -> ModelResponse:
    return ModelResponse(output=[_text(text)] if text else [], usage=Usage(), response_id="synthetic-summary")


def _assert_tool_pairs(items: list[dict]) -> set[str]:
    """Check identities and ordering, not just equal call/output counts."""
    calls = {}
    outputs = {}
    for index, item in enumerate(items):
        if item.get("type") in ("function_call", "apply_patch_call"):
            assert item["call_id"] not in calls, "Duplicate tool call"
            calls[item["call_id"]] = index
        elif item.get("type") in ("function_call_output", "apply_patch_call_output"):
            assert item["call_id"] not in outputs, "Duplicate tool output"
            outputs[item["call_id"]] = index
    assert calls.keys() == outputs.keys(), "Orphan tool item"
    assert all(calls[identity] < outputs[identity] for identity in calls)
    return set(calls)


async def _simulation_parent(tmp_path: Path, history: list[dict]):
    cfg = ModelRunConfig("claude-sonnet-4.6")
    cfg.model_name = "gpt-4o"
    cfg.context_window = 6000
    cfg.provider = "synthetic"
    config = RunningConfig(
        llm_config=cfg, io=MagicMock(), workspace=str(tmp_path),
        agent_name="synthetic-parent", tracing_disabled=True,
    )
    session = RunningSession(config, session_id="synthetic-parent")
    store = FileSession(
        session_id=session.session_id, sessions_dir=str(tmp_path / "sessions"),
        project_root=str(tmp_path), model_name=cfg.model_name,
    )
    session.state.openai_session = store
    await store.migrate_legacy_context(allow_history_only=True)
    if history:
        await store.append_context_items(history, message_ids=[f"old-{i}" for i in range(len(history))])
    context = CodeAgentContext(
        root_dir=str(tmp_path), session=session, provider="synthetic", web_tools_enabled=False,
    )
    return cfg, context, store


@pytest.mark.asyncio
@pytest.mark.parametrize("fork", [False, True], ids=["mid-run", "fork-first-call"])
async def test_run_subtask_real_compaction_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fork: bool,
) -> None:
    """Use synthetic tools and model responses without replacing compaction logic."""
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "1")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    logs = tmp_path / "logs"
    instruction = "Inspect the synthetic module and report its result."
    summary = "<context>synthetic-summary: Earlier inspection completed; continue the task.</context>"
    payload = "\n".join(
        f"def synthetic_{index:04d}(): return {index} * 7 + {index % 13}"
        for index in range(120)
    )
    tools_used = []

    @function_tool
    def synthetic_lookup(stage: int) -> str:
        """Return bounded synthetic source text without reading user files."""
        tools_used.append(stage)
        return f"synthetic source stage {stage}\n{payload}" if stage < 3 else "inspection finished"

    def call(call_id: str, stage: int) -> ResponseFunctionToolCall:
        return ResponseFunctionToolCall(
            id=call_id, call_id=call_id, name="synthetic_lookup",
            arguments=json.dumps({"stage": stage}), type="function_call",
        )

    cfg = ModelRunConfig("claude-sonnet-4.6")
    cfg.model_name = "gpt-4o"
    cfg.context_window = 64_200
    cfg.provider = "synthetic"
    parent_config = RunningConfig(
        llm_config=cfg, io=MagicMock(), workspace=str(tmp_path),
        agent_name="synthetic-parent", tracing_disabled=True,
    )
    parent_session = RunningSession(parent_config, session_id="synthetic-parent")
    store = FileSession(
        session_id=parent_session.session_id, sessions_dir=str(tmp_path / "sessions"),
        project_root=str(tmp_path), model_name=cfg.model_name,
    )
    parent_session.state.openai_session = store
    await store.migrate_legacy_context(allow_history_only=True)
    history = [
        {"role": "user", "content": "Previous synthetic inspection."},
        _text("Previous inspection started.", message_id="old-header").model_dump(),
        call("old-1", 1).model_dump(),
        {"type": "function_call_output", "call_id": "old-1", "output": payload},
        call("old-2", 2).model_dump(),
        {"type": "function_call_output", "call_id": "old-2", "output": payload},
    ] if fork else []
    if history:
        await store.append_context_items(history, message_ids=[f"old-{i}" for i in range(len(history))])
    parent_snapshot = await store.get_context_snapshot()
    context = CodeAgentContext(
        root_dir=str(tmp_path), session=parent_session, provider="synthetic", web_tools_enabled=False,
    )
    parent_agent = Agent(name="synthetic-parent", instructions="# Synthetic parent", tools=[synthetic_lookup])
    run_ctx = RunContextWrapper(context=context)
    run_ctx.agent = parent_agent

    sessions = []

    class ObservedSession(compaction_module.InMemorySession):
        def __init__(self):
            super().__init__()
            self.saves = []
            sessions.append(self)

        async def add_items(self, items: list) -> None:
            before = await self.get_items()
            await super().add_items(items)
            self.saves.append({
                "batch_items": len(items), "before_items": len(before),
                "after_items": len(await self.get_items()),
                "input_in_batch": {"role": "user", "content": instruction} in items,
            })

    requests = []

    class ObservedModel(_ScriptedModel):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            items = await sessions[0].get_items()
            assert input == items, "Model input and effective session diverged"
            requests.append({
                "model_turn": len(requests) + 1, "items": len(items),
                "tokens": compaction_module.calculate_tokens(cfg.model_name, items),
                "summary_present": {"role": "user", "content": summary} in items,
                "original_input_copies": items.count({"role": "user", "content": instruction}),
            })
            return await super().get_response(system_instructions, input, *args, **kwargs)

    steps = [[call("new-3", 3)], [_text("simulation completed")]] if fork else [
        [call("new-1", 1)], [call("new-2", 2)], [call("new-3", 3)],
        [_text("simulation completed")],
    ]
    model = ObservedModel(steps)
    client = SimpleNamespace(completion=AsyncMock(return_value=_summary_response(summary)))
    with patch.object(subtask_module, "InMemorySession", ObservedSession), \
         patch.object(agent_module, "_build_default_tools", return_value=[synthetic_lookup]), \
         patch.object(compaction_module, "get_log_directory", return_value=str(logs)), \
         patch.object(strategy_module, "one_shot_completion", client.completion), \
         patch.object(compaction_module._STRATEGY, "compact", wraps=compaction_module._STRATEGY.compact) as compact, \
         patch("siada.tools.agent.sub_agent_notifier._send_notification"):
        result = await subtask_module.run_subtask_impl(
            instruction, agent_context=context, run_config=RunConfig(model=model, tracing_disabled=True),
            fork=fork, run_ctx=run_ctx,
        )

    assert result == "simulation completed"
    compact.assert_awaited_once()
    client.completion.assert_awaited_once()
    final_items = await sessions[0].get_items()
    assert final_items.count({"role": "user", "content": instruction}) == 1
    assert requests[-1]["summary_present"]
    first_summary_turn = next(request["model_turn"] for request in requests if request["summary_present"])
    assert first_summary_turn == (1 if fork else 3)
    output_ids = [item["call_id"] for item in final_items if item.get("type") == "function_call_output"]
    assert output_ids[-1] == "new-3"
    assert all(request["original_input_copies"] == 1 for request in requests)
    assert tools_used == ([3] if fork else [1, 2, 3])
    assert context.sub_agent_items[-1].status == "completed"
    assert await store.get_context_snapshot() == parent_snapshot
    input_saves = [save for save in sessions[0].saves if save["input_in_batch"]]
    assert len(input_saves) == 1
    assert input_saves[0]["before_items"] == input_saves[0]["after_items"]

    dump_file = logs / "sub_agent_dumps" / f"{sessions[0].session_id}.jsonl"
    dumps = [json.loads(line) for line in dump_file.read_text().splitlines()]
    before = next(entry for entry in dumps if entry["label"] == "before-compaction")
    after = next(entry for entry in dumps if entry["label"] == "after-compaction")
    assert dumps[-1]["label"] == "subtask-finished"
    assert dumps[-1]["items"] == final_items
    before_tokens = compaction_module.calculate_tokens(cfg.model_name, before["items"])
    after_tokens = compaction_module.calculate_tokens(cfg.model_name, after["items"])
    assert before_tokens >= cfg.context_window - 60_000
    assert after_tokens < cfg.context_window - 60_000
    assert after_tokens < before_tokens
    assert after["item_count"] < before["item_count"]
    if fork:
        assert not any(item.get("call_id", "").startswith("old-") for item in after["items"])
    for items in [after["items"], *model.received_inputs, final_items]:
        calls = [item["call_id"] for item in items if item.get("type") == "function_call"]
        outputs = [item["call_id"] for item in items if item.get("type") == "function_call_output"]
        assert sorted(calls) == sorted(outputs), "Compaction produced an orphan tool item"
        assert len(calls) == len(set(calls)), "SDK re-added an old tool call"

    report = {
        "scenario": "fork-first-call" if fork else "mid-run",
        "threshold_tokens": cfg.context_window - 60_000,
        "before": {"items": before["item_count"], "tokens": before_tokens},
        "after": {"items": after["item_count"], "tokens": after_tokens},
        "requests": requests, "sdk_input_save": input_saves[0],
        "final_items": len(final_items), "tools_used": tools_used,
        "parent_context_unchanged": True, "status": "passed",
    }
    (tmp_path / "simulation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("SUBAGENT_SIMULATION " + json.dumps(report, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("lines", [80, 120, 160], ids=["small", "medium", "large"])
@pytest.mark.parametrize("width", [1, 3], ids=["serial", "parallel"])
@pytest.mark.parametrize("fork", [False, True], ids=["clean", "fork"])
@pytest.mark.parametrize("first_summary", ["ok", "empty", "error", "compaction-error"])
async def test_run_subtask_multicycle_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    lines: int, width: int, fork: bool, first_summary: str,
) -> None:
    """Grow and compact real subtask context repeatedly across tool schedules."""
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "1")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    instruction = "Inspect all synthetic modules and preserve each recent tool result."
    payload = "\n".join(
        f"def synthetic_{index:04d}(): return {index} * 7 + {index % 13}"
        for index in range(lines)
    )
    tools_used = []
    rounds = 24 if width == 1 else 12

    @function_tool
    async def synthetic_lookup(stage: int) -> str:
        """Return identical content with deterministic completion-order changes."""
        for _ in range(stage % 3):
            await asyncio.sleep(0)
        tools_used.append(stage)
        return payload

    def call(identity: str, stage: int) -> ResponseFunctionToolCall:
        return ResponseFunctionToolCall(
            id=identity, call_id=identity, name="synthetic_lookup",
            arguments=json.dumps({"stage": stage}), type="function_call",
        )

    # Repeated parent messages are distinct occurrences, not duplicate writes.
    history = [
        {"role": "user", "content": "Previous synthetic inspection."},
        _text("Repeated parent answer.", message_id="old-header").model_dump(),
        {"role": "user", "content": "Previous synthetic inspection."},
        _text("Repeated parent answer.", message_id="old-header-2").model_dump(),
    ] if fork else []
    if fork:
        for index in range(3):
            identity = f"old-tool-{index}"
            history.extend([
                call(identity, index).model_dump(),
                {"type": "function_call_output", "call_id": identity, "output": payload},
            ])
    cfg, context, store = await _simulation_parent(tmp_path, history)
    # The successful matrix budgets for one entire latest parallel group.
    # Smaller/uncompressible keep budgets are exercised separately.
    cfg.context_window *= width
    # Scale the fixed headroom with the synthetic window to retain the
    # tight keep budgets exercised by this long-chain matrix.
    monkeypatch.setattr(threshold_module, "COMPACTION_HEADROOM_TOKENS", 1800 * width)
    parent_snapshot = await store.get_context_snapshot()
    run_ctx = RunContextWrapper(context=context)
    run_ctx.agent = Agent(name="synthetic-parent", instructions="# Synthetic parent", tools=[synthetic_lookup])
    sessions = []
    requests = []
    compactions = []
    removed_ids = set()
    summaries = []
    input_summarized = False

    class ObservedSession(compaction_module.InMemorySession):
        def __init__(self):
            super().__init__()
            self.input_saves = []
            sessions.append(self)

        async def add_items(self, items: list) -> None:
            before = await self.get_items()
            await super().add_items(items)
            if {"role": "user", "content": instruction} in items:
                assert before == await self.get_items(), "SDK restored already admitted input"
                self.input_saves.append(len(items))

    class ObservedModel(_ScriptedModel):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            assert self._turn < len(self._scripted), "Unexpected extra model request"
            items = await sessions[0].get_items()
            assert input == items
            present = _assert_tool_pairs(items)
            assert not (present & removed_ids), "SDK resurrected a summarized tool group"
            # Fork's header belongs to the parent; the task input may later be
            # summarized. Its disappearance must be owned by compaction, and
            # the SDK must never resurrect it afterward.
            assert items.count({"role": "user", "content": instruction}) == int(not input_summarized)
            turn = len(requests)
            if turn:
                expected_latest = {f"new-{(turn - 1) * width + offset}" for offset in range(width)}
                assert expected_latest <= present, "Compaction lost the most recent tool group"
                assert all(
                    item["output"] == payload for item in items
                    if item.get("call_id") in expected_latest and item.get("type") == "function_call_output"
                )
            requests.append({
                "turn": turn + 1, "items": len(items),
                "tokens": compaction_module.calculate_tokens(cfg.model_name, items),
            })
            return await super().get_response(system_instructions, input, *args, **kwargs)

    async def summarize(input, **kwargs):
        if not summaries and first_summary != "ok":
            summaries.append(first_summary)
            if first_summary == "error":
                raise RuntimeError("synthetic summary service failure")
            if first_summary == "compaction-error":
                raise compaction_module.CompactionError("synthetic compaction failure")
            content = ""
        else:
            content = f"<context>synthetic-cycle-{len(summaries)}: {instruction}</context>"
            summaries.append(content)
        return _summary_response(content)

    actual_compact = compaction_module._STRATEGY.compact

    async def observe_compact(model_run_config, items, **kwargs):
        nonlocal input_summarized
        before = json.loads(json.dumps(items))
        try:
            result = await actual_compact(model_run_config, items, **kwargs)
        except Exception as exc:
            assert await sessions[0].get_items() == before
            compactions.append({"outcome": type(exc).__name__, "turn": len(requests) + 1})
            raise
        before_ids = _assert_tool_pairs(before)
        after_ids = _assert_tool_pairs(result.messages)
        if result.compacted:
            input_copies = result.messages.count({"role": "user", "content": instruction})
            assert input_copies <= 1
            if input_summarized:
                assert input_copies == 0
            elif input_copies == 0:
                assert result.summary and instruction in result.summary
                input_summarized = True
            removed_ids.update(before_ids - after_ids)
            before_tokens = compaction_module.calculate_tokens(cfg.model_name, before)
            after_tokens = compaction_module.calculate_tokens(cfg.model_name, result.messages)
            assert after_tokens < before_tokens
            assert after_tokens < threshold_module.get_compaction_token_threshold(cfg.context_window)
            compactions.append({
                "outcome": "compacted", "turn": len(requests) + 1,
                "before_tokens": before_tokens, "after_tokens": after_tokens,
                "removed_pairs": len(before_ids - after_ids),
            })
        else:
            assert result.messages == before
            compactions.append({"outcome": "noop", "turn": len(requests) + 1})
        return result

    script = [
        [call(f"new-{turn * width + offset}", turn * width + offset) for offset in range(width)]
        for turn in range(rounds)
    ] + [[_text("multicycle simulation completed")]]
    model = ObservedModel(script)
    logs = tmp_path / "logs"
    client = SimpleNamespace(completion=AsyncMock(side_effect=summarize))
    with patch.object(subtask_module, "InMemorySession", ObservedSession), \
         patch.object(agent_module, "_build_default_tools", return_value=[synthetic_lookup]), \
         patch.object(compaction_module, "get_log_directory", return_value=str(logs)), \
         patch.object(strategy_module, "one_shot_completion", client.completion), \
         patch.object(compaction_module._STRATEGY, "compact", side_effect=observe_compact), \
         patch("siada.tools.agent.sub_agent_notifier._send_notification"), \
         patch.object(subtask_module.settings, "MAX_TURNS", rounds + 2):
        result = await subtask_module.run_subtask_impl(
            instruction, agent_context=context, run_config=RunConfig(model=model, tracing_disabled=True),
            fork=fork, run_ctx=run_ctx,
        )

    final_items = await sessions[0].get_items()
    _assert_tool_pairs(final_items)
    assert result == "multicycle simulation completed"
    assert len(requests) == rounds + 1
    assert sorted(tools_used) == list(range(rounds * width))
    assert len(sessions[0].input_saves) == 1
    assert final_items.count({"role": "user", "content": instruction}) == int(not input_summarized)
    assert len([cycle for cycle in compactions if cycle["outcome"] == "compacted"]) >= 3
    assert removed_ids
    if first_summary != "ok":
        expected = {"empty": "noop", "error": "RuntimeError", "compaction-error": "CompactionError"}
        assert compactions[0]["outcome"] == expected[first_summary]
    assert context.sub_agent_items[-1].status == "completed"
    assert await store.get_context_snapshot() == parent_snapshot
    dumps = [json.loads(line) for line in (logs / "sub_agent_dumps" / f"{sessions[0].session_id}.jsonl").read_text().splitlines()]
    assert dumps[-1]["label"] == "subtask-finished"
    assert dumps[-1]["items"] == final_items
    for entry in dumps:
        if "items" in entry:
            _assert_tool_pairs(entry["items"])
    report = {
        "scenario": {"fork": fork, "width": width, "lines": lines, "first_summary": first_summary},
        "model_turns": len(requests), "tool_calls": len(tools_used),
        "compactions": compactions, "removed_tool_pairs": len(removed_ids),
        "input_summarized": input_summarized,
        "final_items": len(final_items), "status": "passed",
    }
    (tmp_path / "multicycle-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("SUBAGENT_MULTICYCLE " + json.dumps(report, sort_keys=True))


@pytest.mark.parametrize("width", [1, 3])
@pytest.mark.parametrize("leading_user", [False, True])
@pytest.mark.parametrize("native_patch", [False, True], ids=["function", "native-patch"])
def test_keep_budget_trimming_preserves_latest_complete_group(
    width: int, leading_user: bool, native_patch: bool,
) -> None:
    """Trim whole groups even when the kept tail starts with a function call."""
    from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction

    strategy = SummarizeWithHeaderCompaction()
    cfg = SimpleNamespace(model_name="gpt-4o")
    groups = []
    for turn in range(3):
        calls = [
            {"type": "function_call", "call_id": f"{turn}-{i}", "name": "lookup", "arguments": "{}"}
            for i in range(width)
        ]
        outputs = [
            {"type": "function_call_output", "call_id": f"{turn}-{i}", "output": "synthetic result " * 80}
            for i in reversed(range(width))
        ]
        if native_patch:
            for item in calls:
                item.update({"type": "apply_patch_call", "operation": {
                    "type": "update_file", "path": "synthetic.py", "diff": "@@",
                }})
                item.pop("name")
                item.pop("arguments")
            for item in outputs:
                item["type"] = "apply_patch_call_output"
        groups.append(calls + outputs)
    header = [{"role": "user", "content": "task"}] if leading_user else []
    latest = header + groups[-1]
    budget = strategy._count_tokens(latest, cfg) + 5
    messages = header + [item for group in groups for item in group]
    assert strategy._count_tokens(messages, cfg) > budget
    assert strategy._identify_tool_call_groups(messages) == [
        (len(header) + i * 2 * width, len(header) + (i + 1) * 2 * width) for i in range(3)
    ]
    trimmed = strategy._trim_kept_history(messages, cfg, budget)
    assert trimmed == latest
    assert _assert_tool_pairs(trimmed) == {f"2-{i}" for i in range(width)}


@pytest.mark.parametrize("width", [1, 3])
@pytest.mark.parametrize("reverse_outputs", [False, True])
@pytest.mark.parametrize("split_offset", [-1, 0], ids=["last-output", "end"])
@pytest.mark.parametrize("native_patch", [False, True], ids=["function", "native-patch"])
def test_end_boundary_retreats_before_complete_parallel_group(
    width: int, reverse_outputs: bool, split_offset: int, native_patch: bool,
) -> None:
    """A near-end fallback must retain all calls and outputs, not a lone output."""
    strategy = compaction_module._STRATEGY
    header = [{"role": "user", "content": "task"}]
    group = [{"type": "reasoning", "id": "reasoning", "summary": []}, _text("inspect").model_dump()]
    group.extend({
        "type": "function_call", "call_id": f"call-{i}", "name": "lookup", "arguments": "{}",
    } for i in range(width))
    order = list(range(width))
    if reverse_outputs:
        order.reverse()
    group.extend({"type": "function_call_output", "call_id": f"call-{i}", "output": "result"} for i in order)
    if native_patch:
        for item in group:
            if item.get("type") == "function_call":
                item.update({"type": "apply_patch_call", "operation": {
                    "type": "update_file", "path": "synthetic.py", "diff": "@@",
                }})
                item.pop("name")
                item.pop("arguments")
            elif item.get("type") == "function_call_output":
                item["type"] = "apply_patch_call_output"
    messages = header + group
    boundary = strategy.adjust_compression_index_for_boundary_cases(messages, len(messages) + split_offset)
    assert boundary == len(header)
    assert _assert_tool_pairs(messages[boundary:]) == {f"call-{i}" for i in range(width)}


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [1, 3], ids=["serial", "parallel"])
async def test_latest_tool_group_over_keep_budget_preserves_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int,
) -> None:
    """An unsatisfiable keep budget falls back without corrupting tool history.

    This characterizes the existing limitation, not a context-size guarantee:
    callers may still face provider overflow until tool output is bounded.
    """
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "0")
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    cfg, context, store = await _simulation_parent(tmp_path, [])
    cfg.context_window = 1800 * width
    original_parent = await store.get_context_snapshot()
    payload = "synthetic oversized tool result " * 500
    rounds = 6

    @function_tool
    def oversized_lookup() -> str:
        """Return a synthetic result larger than the latest-group keep budget."""
        return payload

    script = [[ResponseFunctionToolCall(
        id=f"call-{turn}-{offset}", call_id=f"call-{turn}-{offset}",
        name="oversized_lookup", arguments="{}", type="function_call",
    ) for offset in range(width)] for turn in range(rounds)] + [[_text("finished")]]
    sessions = []
    errors = []

    class ObservedSession(compaction_module.InMemorySession):
        def __init__(self):
            super().__init__()
            sessions.append(self)

    class ObservedModel(_ScriptedModel):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            assert input == await sessions[0].get_items()
            assert input.count({"role": "user", "content": "oversized task"}) == 1
            assert len(_assert_tool_pairs(input)) == self._turn * width
            return await super().get_response(system_instructions, input, *args, **kwargs)

    actual_compact = compaction_module._STRATEGY.compact

    async def observe_compact(model_run_config, items, **kwargs):
        try:
            return await actual_compact(model_run_config, items, **kwargs)
        except ValueError as exc:
            assert str(exc) == "No messages to keep after trimming"
            assert await sessions[0].get_items() == items
            errors.append(str(exc))
            raise

    model = ObservedModel(script)
    client = SimpleNamespace(completion=AsyncMock(return_value=_summary_response("<context>oversized summary</context>")))
    with patch.object(subtask_module, "InMemorySession", ObservedSession), \
         patch.object(agent_module, "_build_default_tools", return_value=[oversized_lookup]), \
         patch.object(strategy_module, "one_shot_completion", client.completion), \
         patch.object(compaction_module._STRATEGY, "compact", side_effect=observe_compact), \
         patch("siada.tools.agent.sub_agent_notifier._send_notification"), \
         patch.object(subtask_module.settings, "MAX_TURNS", rounds + 2):
        result = await subtask_module.run_subtask_impl(
            "oversized task", agent_context=context, run_config=RunConfig(model=model, tracing_disabled=True),
        )
    assert result == "finished"
    assert errors, "The synthetic latest group must exceed the keep budget"
    assert len(model.received_inputs) == rounds + 1
    assert len(_assert_tool_pairs(await sessions[0].get_items())) == rounds * width
    assert context.sub_agent_items[-1].status == "completed"
    assert await store.get_context_snapshot() == original_parent
    assert compaction_module.calculate_tokens(cfg.model_name, await sessions[0].get_items()) > cfg.context_window
    print("SUBAGENT_OVERSIZED " + json.dumps({
        "width": width, "tool_calls": rounds * width, "compaction_failures": len(errors),
        "context_over_window": True, "history_intact": True,
    }, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["below", "equal", "above"])
async def test_real_token_threshold_boundary(offset: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a real token count with thresholds immediately around it."""
    from agents.run_config import CallModelData, ModelInputData

    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "0")
    session = compaction_module.InMemorySession()
    items = [{"role": "user", "content": "synthetic text " * 100}]
    await session.add_items(items)
    tokens = compaction_module.calculate_tokens("gpt-4o", items)
    # This config is a threshold probe only, not a provider context-window claim.
    cfg = SimpleNamespace(model_name="gpt-4o", context_window=tokens - offset + 60_000)
    assert compaction_module._STRATEGY.should_compact(tokens, cfg) == (offset >= 0)
    data = CallModelData(model_data=ModelInputData(input=items, instructions="sys"), agent=Agent(name="boundary"), context=None)
    with patch.object(compaction_module._STRATEGY, "compact", wraps=compaction_module._STRATEGY.compact) as compact:
        result = await compaction_module.make_sub_agent_compaction_filter(cfg, session)(data)
    assert compact.await_count == int(offset >= 0)
    assert result.input == items
    assert result.instructions == "sys"
    assert await session.get_items() == items


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True], ids=["nonstreamed", "streamed"])
async def test_twelve_identical_inputs_across_new_runs(streamed: bool) -> None:
    """New input occurrences survive twelve runs even while outputs are identical."""
    session = compaction_module.InMemorySession()
    cfg = SimpleNamespace(model_name="gpt-4o", context_window=200_000)
    for index in range(12):
        model = _ScriptedModel([[_text("same answer", message_id=f"answer-{index}")]])
        config = _build_run_config(session, cfg)
        await _run_agent(Agent(name="repeat", model=model), session, config, streamed=streamed, input="same task")
        items = await session.get_items()
        assert items.count({"role": "user", "content": "same task"}) == index + 1
        assert len(items) == 2 * (index + 1)
        assert model.received_inputs[0] == items[:-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True], ids=["nonstreamed", "streamed"])
async def test_multicompaction_model_failure_and_retry(streamed: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure after several compactions keeps the admitted baseline on retry."""
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "0")
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    session = compaction_module.InMemorySession()
    cfg = SimpleNamespace(model_name="gpt-4o", context_window=6000, provider="synthetic")
    payload = "\n".join(f"def synthetic_{i:04d}(): return {i} * 7 + {i % 13}" for i in range(120))
    tools_used = []

    @function_tool
    def retry_lookup(stage: int) -> str:
        """Return synthetic data with an observable execution count."""
        tools_used.append(stage)
        return payload

    rounds = 8
    script = [[ResponseFunctionToolCall(
        id=f"retry-{i}", call_id=f"retry-{i}", name="retry_lookup",
        arguments=json.dumps({"stage": i}), type="function_call",
    )] for i in range(rounds)] + [RuntimeError("synthetic late model failure")]
    model = _ScriptedModel(script)
    config = _build_run_config(session, cfg)
    summary = "<context>synthetic retry summary: continue the retry task.</context>"
    client = SimpleNamespace(completion=AsyncMock(return_value=_summary_response(summary)))
    with patch.object(strategy_module, "one_shot_completion", client.completion):
        with pytest.raises(RuntimeError, match="synthetic late model failure"):
            await _run_agent(
                Agent(name="late-failure", model=model, tools=[retry_lookup]),
                session, config, streamed=streamed, input="retry task", max_turns=rounds + 2,
            )
        assert client.completion.await_count >= 3
        before_retry = await session.get_items()
        retained = _assert_tool_pairs(before_retry)
        assert f"retry-{rounds - 1}" in retained
        assert len(retained) < rounds
        assert before_retry.count({"role": "user", "content": "retry task"}) == 1
        assert tools_used == list(range(rounds))

        recovered_model = _ScriptedModel([[_text("recovered after multiple compactions")]])
        recovered = await _run_agent(Agent(name="recovered", model=recovered_model), session, config, streamed=streamed, input="retry task")
        assert recovered.final_output == "recovered after multiple compactions"
        assert recovered_model.received_inputs[0] == before_retry
        final_items = await session.get_items()
        assert _assert_tool_pairs(final_items) == retained
        assert final_items.count({"role": "user", "content": "retry task"}) == 1
        assert len(final_items) == len(before_retry) + 1
        assert tools_used == list(range(rounds)), "Retry must not replay completed tools"


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["summary", "model"])
async def test_stream_cancel_and_retry_after_admission(phase: str) -> None:
    """Cancel while summarizing or after admission, then retry the same input."""
    session = compaction_module.InMemorySession()
    payload = "synthetic old text " * 400
    history = [
        {"role": "user", "content": "initial task"},
        {"role": "assistant", "content": "initial answer"},
        {"role": "user", "content": payload},
        {"role": "assistant", "content": "old answer"},
    ]
    await session.add_items(history)
    cfg = SimpleNamespace(model_name="gpt-4o", context_window=1200, provider="synthetic")
    config = _build_run_config(session, cfg)
    entered = asyncio.Event()
    settled = asyncio.Event()
    request_items = []
    summary = "<context>synthetic cancellation summary</context>"

    async def summarize(input, **kwargs):
        if phase == "summary" and not entered.is_set():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                settled.set()
        return _summary_response(summary)

    class BlockingModel(_ScriptedModel):
        async def get_response(self, system_instructions, input, *args, **kwargs):
            request_items.append(input)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                settled.set()

    client = SimpleNamespace(completion=AsyncMock(side_effect=summarize))
    with patch.object(strategy_module, "one_shot_completion", client.completion):
        model = BlockingModel([[_text("unreachable")]]) if phase == "model" else _ScriptedModel([[_text("unreachable")]])
        result = Runner.run_streamed(Agent(name="cancel", model=model), input="new task", session=session, run_config=config)

        async def consume():
            async for _ in result.stream_events():
                pass

        consumer = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            before_cancel = await session.get_items()
            result.cancel()
            await asyncio.wait_for(consumer, timeout=5)
            await asyncio.wait_for(settled.wait(), timeout=5)
            assert await session.get_items() == before_cancel
            assert before_cancel.count({"role": "user", "content": "new task"}) == 1
            if phase == "summary":
                assert not request_items
                assert model.received_inputs == []
                assert before_cancel == history + [{"role": "user", "content": "new task"}]
            else:
                assert request_items == [before_cancel]
                assert {"role": "user", "content": summary} in before_cancel
            retry_model = _ScriptedModel([[_text("recovered")]])
            retry = await _run_agent(Agent(name="retry", model=retry_model), session, config, streamed=True, input="new task")
            assert retry.final_output == "recovered"
            final_items = await session.get_items()
            assert final_items.count({"role": "user", "content": "new task"}) == 1
            assert {"role": "user", "content": summary} in final_items
        finally:
            result.cancel()
            if not consumer.done():
                consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)


@pytest.mark.asyncio
async def test_subtask_max_turn_failure_preserves_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded runaway subtask reports failure after persisting the last tool result."""
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "0")
    cfg, context, store = await _simulation_parent(tmp_path, [])
    parent = await store.get_context_snapshot()
    sessions = []

    class ObservedSession(compaction_module.InMemorySession):
        def __init__(self):
            super().__init__()
            sessions.append(self)

    @function_tool
    def bounded_tool() -> str:
        """Return a deterministic result without side effects."""
        return "bounded result"

    script = [[ResponseFunctionToolCall(
        id=f"call-{i}", call_id=f"call-{i}", name="bounded_tool", arguments="{}", type="function_call",
    )] for i in range(3)]
    model = _ScriptedModel(script)
    with patch.object(subtask_module, "InMemorySession", ObservedSession), \
         patch.object(agent_module, "_build_default_tools", return_value=[bounded_tool]), \
         patch("siada.tools.agent.sub_agent_notifier._send_notification"), \
         patch.object(subtask_module.settings, "MAX_TURNS", 2):
        with pytest.raises(MaxTurnsExceeded):
            await subtask_module.run_subtask_impl(
                "bounded task", agent_context=context, run_config=RunConfig(model=model, tracing_disabled=True),
            )
    assert len(model.received_inputs) == 2
    assert context.sub_agent_items[-1].status == "failed"
    assert _assert_tool_pairs(await sessions[0].get_items()) == {"call-0", "call-1"}
    assert await store.get_context_snapshot() == parent


@pytest.mark.asyncio
@pytest.mark.parametrize("lines", [80, 120], ids=["small", "medium"])
async def test_concurrent_subtasks_keep_compaction_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: int,
) -> None:
    """Concurrent subtask runs share a strategy, not histories or admissions."""
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "1")
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    cfg, context, store = await _simulation_parent(tmp_path, [])
    parent = await store.get_context_snapshot()
    labels = ("alpha", "beta")
    instructions = {label: f"Concurrent {label} task." for label in labels}
    payloads = {
        label: "\n".join(
            f"def {label}_{index:04d}(): return {index} * 7 + {index % 13}"
            for index in range(lines)
        ) for label in labels
    }
    sessions = {}
    tools_used = {label: [] for label in labels}
    summary_counts = {label: 0 for label in labels}
    rounds = 12
    logs = tmp_path / "logs"

    class ObservedSession(compaction_module.InMemorySession):
        async def admit_input(self, admission_id: str, items: list) -> None:
            await super().admit_input(admission_id, items)
            label = next(label for label in labels if instructions[label] == items[0]["content"])
            sessions[label] = self

    @function_tool
    async def concurrent_lookup(label: str, stage: int) -> str:
        """Return task-specific synthetic data with cooperative scheduling."""
        await asyncio.sleep(0)
        tools_used[label].append(stage)
        return payloads[label]

    class ObservedModel(_ScriptedModel):
        def __init__(self, label: str):
            self.label = label
            script = [[ResponseFunctionToolCall(
                id=f"{label}-{i}", call_id=f"{label}-{i}", name="concurrent_lookup",
                arguments=json.dumps({"label": label, "stage": i}), type="function_call",
            )] for i in range(rounds)] + [[_text(f"{label} finished", message_id=f"{label}-final")]]
            super().__init__(script)

        async def get_response(self, system_instructions, input, *args, **kwargs):
            assert input == await sessions[self.label].get_items()
            assert input.count({"role": "user", "content": instructions[self.label]}) == 1
            other = next(label for label in labels if label != self.label)
            assert instructions[other] not in json.dumps(input)
            assert all(identity.startswith(self.label + "-") for identity in _assert_tool_pairs(input))
            assert all(
                item["output"] == payloads[self.label] for item in input
                if item.get("type") == "function_call_output"
            )
            return await super().get_response(system_instructions, input, *args, **kwargs)

    # Make the first two summary calls overlap to exercise shared strategy use.
    entered = set()
    both_entered = asyncio.Event()

    async def summarize(input, **kwargs):
        messages = json.dumps(input)
        owners = [label for label in labels if instructions[label] in messages]
        assert len(owners) == 1, "Summary request contains another subtask's input"
        label = owners[0]
        entered.add(label)
        if len(entered) == len(labels):
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=5)
        await asyncio.sleep(0)
        summary_counts[label] += 1
        summary = f"<context>{instructions[label]} summary-{summary_counts[label]}</context>"
        return _summary_response(summary)

    client = SimpleNamespace(completion=AsyncMock(side_effect=summarize))
    models = {label: ObservedModel(label) for label in labels}
    with patch.object(subtask_module, "InMemorySession", ObservedSession), \
         patch.object(agent_module, "_build_default_tools", return_value=[concurrent_lookup]), \
         patch.object(compaction_module, "get_log_directory", return_value=str(logs)), \
         patch.object(strategy_module, "one_shot_completion", client.completion), \
         patch("siada.tools.agent.sub_agent_notifier._send_notification"), \
         patch.object(subtask_module.settings, "MAX_TURNS", rounds + 2):
        results = await asyncio.wait_for(asyncio.gather(*(
            subtask_module.run_subtask_impl(
                instructions[label], agent_context=context,
                run_config=RunConfig(model=models[label], tracing_disabled=True),
            ) for label in labels
        )), timeout=15)

    assert results == [f"{label} finished" for label in labels]
    assert sessions["alpha"].session_id != sessions["beta"].session_id
    assert len(context.sub_agent_items) == len(labels)
    assert all(item.status == "completed" for item in context.sub_agent_items)
    assert await store.get_context_snapshot() == parent
    for label in labels:
        assert tools_used[label] == list(range(rounds))
        assert summary_counts[label] >= 3
        final_items = await sessions[label].get_items()
        assert len(models[label].received_inputs) == rounds + 1
        assert final_items.count({"role": "user", "content": instructions[label]}) == 1
        assert _assert_tool_pairs(final_items) < {f"{label}-{i}" for i in range(rounds)}
        path = logs / "sub_agent_dumps" / f"{sessions[label].session_id}.jsonl"
        dumps = [json.loads(line) for line in path.read_text().splitlines()]
        assert dumps[-1]["label"] == "subtask-finished"
        assert dumps[-1]["items"] == final_items
    print("SUBAGENT_CONCURRENT " + json.dumps({
        "lines": lines, "model_turns": 2 * (rounds + 1), "tool_calls": 2 * rounds,
        "summaries": summary_counts, "parent_unchanged": True, "status": "passed",
    }, sort_keys=True))
