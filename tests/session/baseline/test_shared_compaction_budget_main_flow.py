"""Validate shared compaction helpers through prepared main-session entrypoints."""

import copy
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import ModelResponse, function_tool
from agents.usage import Usage
from agents.models.chatcmpl_converter import Converter

from siada.agent_hub.context_filter import api_message_transfer_filter as transfer
from siada.agent_hub.context_filter import compaction_strategy as shared
from siada.agent_hub.context_filter import compaction_threshold as threshold_module
from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.services.siada_runner import SiadaRunner
from siada.session.ownership import SessionOwner, SessionOwnershipManager
from siada.support.chat_compat_items import to_chat_compatible_items
from siada.support.slash_commands import SlashCommands
from tests.session.baseline.conftest import ScriptedModel
from tests.session.baseline.test_default_context_cutover import run_default


# Capture the public method before the baseline fixture replaces compaction.
_REAL_TRY_COMPACT = transfer.ApiMessageTransferFilter._try_compact_real_api_messages
estimator = importlib.import_module("siada.agent_hub.context_filter.request_token_estimator")


class PreparedContextModel(ScriptedModel):
    """Observe committed effective context before the provider proxy conversion."""

    async def _next(self, instructions, input):
        snapshot = await self.session.get_context_snapshot()
        expected = snapshot["items"] if getattr(self, "supports_native_responses_items", False) else to_chat_compatible_items(snapshot["items"])
        assert input == expected
        result = await super()._next(instructions, input)
        self.requests[-1]["effective_snapshot"] = copy.deepcopy(snapshot)
        # Server usage must describe this request, not the harness's tiny fixed
        # default, now that warm requests use usage-calibrated budgets.
        input_tokens = shared.calculate_tokens("gpt-4o", input) + shared.calculate_tokens("gpt-4o", instructions or "")
        return result[0], Usage(requests=1, input_tokens=input_tokens, output_tokens=30, total_tokens=input_tokens + 30)


def _group(identity: str, width: int, *, native: bool, payload: str) -> list[dict]:
    calls = []
    for index in range(width):
        call = {"type": "function_call", "call_id": f"{identity}-{index}", "name": "synthetic", "arguments": "{}"}
        if native:
            call = {
                "type": "apply_patch_call", "call_id": f"{identity}-{index}", "status": "completed",
                "operation": {"type": "update_file", "path": "synthetic.py", "diff": "@@"},
            }
        calls.append(call)
    outputs = [
        {"type": "apply_patch_call_output" if native else "function_call_output",
         "call_id": f"{identity}-{index}", "output": payload}
        for index in reversed(range(width))
    ]
    return calls + outputs


def _paired_ids(items: list[dict]) -> set[str]:
    calls = [item["call_id"] for item in items if item.get("type") in ("function_call", "apply_patch_call")]
    outputs = [item["call_id"] for item in items if item.get("type") in ("function_call_output", "apply_patch_call_output")]
    assert sorted(calls) == sorted(outputs), "Compaction created orphan tool items"
    assert len(calls) == len(set(calls)), "A discarded tool call was replayed"
    positions = {item["call_id"]: index for index, item in enumerate(items) if item.get("type") in ("function_call", "apply_patch_call")}
    assert all(positions[item["call_id"]] < index for index, item in enumerate(items)
               if item.get("type") in ("function_call_output", "apply_patch_call_output"))
    return set(calls)


def _history(baseline, width: int, native: bool) -> list[dict]:
    items = [{"role": "user", "content": "Original main task."}, baseline.text("Original answer", "header").model_dump()]
    for turn in range(8):
        items.extend([
            {"role": "user", "content": f"Old turn {turn}: " + "x" * (1800 * width)},
            baseline.text(f"Old answer {turn}", f"old-{turn}").model_dump(),
        ])
    items.append({"role": "user", "content": "Continue the current main task."})
    payload = "\n".join(f"def synthetic_{i:04d}(): return {i} * 7 + {i % 13}" for i in range(40))
    for turn in range(3):
        items.extend(_group(f"old-tool-{turn}", width, native=native, payload=payload))
    return items


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["nonstreamed", "streamed"])
@pytest.mark.parametrize("manual", [False, True], ids=["automatic", "manual"])
@pytest.mark.parametrize("width", [1, 3], ids=["serial", "parallel"])
@pytest.mark.parametrize("native", [False, True], ids=["function", "native-patch"])
@pytest.mark.parametrize("budget", ["normal", "trim", "trim-no-user", "oversized", "oversized-no-user"])
@pytest.mark.parametrize("native_wire", [False, True], ids=["chat-wire", "responses-wire"])
async def test_main_real_strategy_commits_and_replays_safely(baseline, monkeypatch, stream, manual, width, native, budget, native_wire):
    """Real strategy/tokenizer results reach the model and disk without history replay."""
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", _REAL_TRY_COMPACT)
    monkeypatch.setattr(transfer, "calculate_tokens", shared.calculate_tokens)
    monkeypatch.setattr(estimator, "calculate_tokens", shared.calculate_tokens)
    session = baseline.session()
    cfg = session.siada_config.llm_config
    cfg.model_name = "gpt-4o"
    cfg.provider = "synthetic"
    cfg.context_window = {"normal": 4500, "trim": 2000, "trim-no-user": 2000, "oversized": 600, "oversized-no-user": 600}[budget] * width
    # Keep this budget-stress matrix small while exercising the fixed-headroom
    # trigger. Default 60k boundaries are covered by the strategy threshold tests.
    monkeypatch.setattr(threshold_module, "COMPACTION_HEADROOM_TOKENS", int(cfg.context_window * 0.3))
    store = session.openai_session
    history = _history(baseline, width, native)
    if budget in ("trim-no-user", "oversized-no-user"):
        # Exercise assistant-leading tails with a fitting or oversized latest group.
        del history[18]
    original = copy.deepcopy(history)
    await store.add_items(history)
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    session.siada_config.auto_compact = not manual
    session.siada_config.compaction_strategy = "header_summary"
    context.task_message_state.reset_message_history([{"role": "user", "content": "stale mirror"}])
    strategy = SummarizeWithHeaderCompaction()
    monkeypatch.setattr(transfer, "get_compaction_strategy", lambda _: strategy)
    monkeypatch.setattr(shared, "get_compaction_strategy", lambda _: strategy)
    summary = "<context>Synthetic main summary; continue the task.</context>"
    client = SimpleNamespace(completion=AsyncMock(return_value=ModelResponse(
        output=[baseline.text(summary)], usage=baseline.usage(), response_id="summary",
    )))

    @function_tool
    def next_step() -> str:
        """Return a small deterministic result without touching user files."""
        return "new main tool result"

    io = MagicMock()
    observed_results = []
    observed_attempts = []
    real_compact = strategy.compact

    async def observe_compact(*args, **kwargs):
        try:
            result = await real_compact(*args, **kwargs)
        except Exception as exc:
            observed_attempts.append({"error": type(exc).__name__})
            raise
        observed_attempts.append({"compacted": result.compacted})
        observed_results.append(copy.deepcopy(result.messages))
        return result

    with patch.object(shared, "one_shot_completion", client.completion), \
         patch.object(strategy, "compact", side_effect=observe_compact), \
         patch.object(strategy, "_trim_kept_history", wraps=strategy._trim_kept_history) as trim:
        if manual:
            monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
            SlashCommands(io=io).cmd_compact(session, "")
            compacted = await store.get_items()
            assert io.print_error.called == (budget == "oversized-no-user")
            assert await store.get_history_items() == original
        model = PreparedContextModel(store, [
            [baseline.call("new-main", "next_step", {})], [baseline.text("main finished", "new-final")],
        ])
        model.supports_native_responses_items = native_wire
        result = await run_default(baseline, session, model, stream=stream, context=context, tools=[next_step], input=[])
        assert result.final_output == "main finished"
        assert trim.called == (budget != "normal")

    assert history == original, "The strategy mutated its caller's history"
    first = model.requests[0]["effective_snapshot"]["items"]
    final = await store.get_items()
    for request in model.requests:
        expected = request["effective_snapshot"]["items"]
        assert request["input"] == (expected if native_wire else to_chat_compatible_items(expected))
    assert store.get_context_snapshot_sync()["items"] == final
    assert not (store.session_folder / "api_messages.json").exists()
    assert (await store.get_history_items())[:len(original)] == original
    assert first[0] == original[0]
    assert {"role": "user", "content": "stale mirror"} not in final
    if budget == "oversized-no-user":
        assert first == original
        assert observed_attempts[0] == {"error": "ValueError"}
        # Automatic compaction retries per request; the new small tool group
        # allows a later successful compaction without reviving old groups.
        if manual:
            assert not observed_results
        else:
            assert observed_attempts[1] == {"compacted": True}
            assert len(observed_results) == 1
            assert model.requests[1]["effective_snapshot"]["items"] == observed_results[0]
            assert "new-main" in _paired_ids(observed_results[-1])
            assert not (_paired_ids(observed_results[-1]) & _paired_ids(original))
    else:
        assert observed_results
        assert {"role": "user", "content": summary} in first
        if manual:
            assert first == compacted
        dropped = _paired_ids(original) - _paired_ids(first)
        for request in model.requests:
            assert not (_paired_ids(request["input"]) & dropped)
        assert not (_paired_ids(final) & dropped)
        if budget in ("trim", "trim-no-user"):
            assert _paired_ids(first) == {f"old-tool-2-{i}" for i in range(width)}
        elif budget == "oversized":
            # A retained user allows a successful result even if no tool group fits.
            assert not _paired_ids(first)
            assert {"role": "user", "content": "Continue the current main task."} in first
        else:
            assert _paired_ids(first) == _paired_ids(original)
    assert "new-main" in _paired_ids(model.requests[1]["effective_snapshot"]["items"])
    assert "new-main" in _paired_ids(final)
    for items in [first, model.requests[1]["input"], final]:
        # Real chat conversion rejects incompatible native structures unless proxied.
        assert Converter.items_to_messages(to_chat_compatible_items(items))[0]["role"] == "user"


@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("width", [1, 3])
def test_shared_repair_default_preserves_complete_context_contract(strategy_type, native, width):
    """Default and IM repair still strip leading non-user items and remove orphans."""
    strategy = strategy_type()
    group = _group("valid", width, native=native, payload="ok")
    orphan_output = {"type": "function_call_output", "call_id": "orphan-output", "output": "invalid"}
    orphan_call = {"type": "function_call", "call_id": "orphan-call", "name": "synthetic", "arguments": "{}"}
    messages = group + [{"role": "user", "content": "task"}] + group + [orphan_output, orphan_call]
    expected = [{"role": "user", "content": "task"}] + group
    original = copy.deepcopy(messages)
    assert strategy._repair_tool_pairs(messages) == expected
    assert messages == original
    assert strategy._repair_tool_pairs(group) == []
    assert strategy._repair_tool_pairs(group, require_user_start=False) == group
    assert _paired_ids(strategy._repair_tool_pairs([orphan_output] + group + [orphan_call], require_user_start=False)) == {
        f"valid-{i}" for i in range(width)
    }


@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("width", [1, 3])
def test_summary_pruning_retains_user_start_and_complete_groups(strategy_type, native, width):
    """The shared kept-tail opt-out never applies to summary-input pruning."""
    strategy = strategy_type()
    cfg = SimpleNamespace(model_name="gpt-4o")
    latest = [{"role": "user", "content": "latest task"}] + _group("latest", width, native=native, payload="ok")
    history = [{"role": "user", "content": "old text " * 1000}] + _group("old", width, native=native, payload="ok") + latest
    original = copy.deepcopy(history)
    budget = strategy._count_tokens(latest, cfg)
    assert strategy._prune_messages_to_token_budget(history, budget, cfg) == latest
    assert strategy._prune_messages_to_token_budget(_group("no-user", width, native=native, payload="large " * 100), 1, cfg) == []
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["nonstreamed", "streamed"])
@pytest.mark.parametrize("manual", [False, True], ids=["automatic", "manual"])
@pytest.mark.parametrize("width", [1, 3], ids=["serial", "parallel"])
@pytest.mark.parametrize("native", [False, True], ids=["function", "native-patch"])
async def test_im_main_real_strategy_preserves_recent_groups(baseline, monkeypatch, stream, manual, width, native):
    """IM's factory-selected turn-prune strategy keeps its full-context contract."""
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", _REAL_TRY_COMPACT)
    monkeypatch.setattr(transfer, "calculate_tokens", shared.calculate_tokens)
    monkeypatch.setattr(estimator, "calculate_tokens", shared.calculate_tokens)
    session = baseline.session()
    cfg = session.siada_config.llm_config
    cfg.model_name, cfg.provider, cfg.context_window = "gpt-4o", "synthetic", 3000 * width
    session.siada_config.auto_compact = not manual
    session.siada_config.compaction_strategy = None
    SessionOwnershipManager.set_session_source(session.openai_session.session_folder, SessionOwner.LARK)
    context = baseline.context(session)
    assert context.im_mode
    assert isinstance(shared.get_compaction_strategy(context), TurnPruneSummaryCompaction)
    original = _history(baseline, width, native)
    # The oldest eligible turns must exceed the summary-input budget so this
    # exercises the unchanged user-boundary pruning, not just IM assembly.
    for index in range(5):
        original[2 + 2 * index]["content"] = f"Old turn {index}: " + "historical source token " * (800 * width)
    store = session.openai_session
    await store.add_items(original)
    await store.migrate_legacy_context(allow_history_only=True)
    recent, to_summarize = TurnPruneSummaryCompaction()._split_recent_turns(original)
    assert shared.calculate_tokens(cfg.model_name, to_summarize) > int(cfg.context_window * 0.9)
    summary = "<context>Synthetic IM summary</context>"
    client = SimpleNamespace(completion=AsyncMock(return_value=ModelResponse(
        output=[baseline.text(summary)], usage=baseline.usage(), response_id="summary",
    )))
    model = PreparedContextModel(store, [[baseline.text("IM completed")]])
    io = MagicMock()
    with patch.object(shared, "one_shot_completion", client.completion), \
         patch.object(shared.CompactionStrategy, "_trim_kept_history", side_effect=AssertionError("IM must not use kept-tail trimming")), \
         patch.object(shared.CompactionStrategy, "_prune_messages_to_token_budget", autospec=True,
                      side_effect=shared.CompactionStrategy._prune_messages_to_token_budget) as prune:
        if manual:
            monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
            SlashCommands(io=io).cmd_compact(session, "")
            assert not io.print_error.called
            assert await store.get_history_items() == original
        await run_default(baseline, session, model, stream=stream, context=context, input=[])
    client.completion.assert_awaited_once()
    prune.assert_called()
    first = model.requests[0]["effective_snapshot"]["items"]
    expected = TurnPruneSummaryCompaction()._assemble_compacted(summary, recent)
    assert first == expected
    assert first[0] == {"role": "user", "content": summary}
    assert _paired_ids(first) == _paired_ids(recent)
    assert (await store.get_history_items())[:-1] == original
    assert (await store.get_items())[:-1] == first
    assert not (store.session_folder / "api_messages.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["nonstreamed", "streamed"])
@pytest.mark.parametrize("manual", [False, True], ids=["automatic", "manual"])
@pytest.mark.parametrize("failure", ["empty", "exception", "compaction-error"])
async def test_main_compaction_failure_keeps_input_and_recovers(baseline, monkeypatch, stream, manual, failure):
    """A failed summary leaves history and effective input intact; retry can compact."""
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", _REAL_TRY_COMPACT)
    monkeypatch.setattr(transfer, "calculate_tokens", shared.calculate_tokens)
    monkeypatch.setattr(estimator, "calculate_tokens", shared.calculate_tokens)
    session = baseline.session()
    cfg = session.siada_config.llm_config
    cfg.model_name, cfg.provider, cfg.context_window = "gpt-4o", "synthetic", 2000
    session.siada_config.auto_compact = not manual
    session.siada_config.compaction_strategy = "header_summary"
    context = baseline.context(session)
    store = session.openai_session
    original = _history(baseline, 3, True)
    await store.add_items(original)
    await store.migrate_legacy_context(allow_history_only=True)
    summary = "<context>Synthetic recovery summary</context>"
    success = ModelResponse(output=[baseline.text(summary)], usage=baseline.usage(), response_id="summary")
    failed = ModelResponse(output=[], usage=baseline.usage(), response_id="empty-summary") if failure == "empty" else (
        shared.CompactionError("synthetic summary failure") if failure == "compaction-error" else RuntimeError("synthetic summary failure")
    )
    client = SimpleNamespace(completion=AsyncMock(side_effect=[failed, success]))
    model = PreparedContextModel(store, [[baseline.text("after failure", "failed-pass")], [baseline.text("recovered", "recovery")]])
    io = MagicMock()
    with patch.object(shared, "one_shot_completion", client.completion):
        if manual:
            monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
            before = await store.get_context_snapshot()
            SlashCommands(io=io).cmd_compact(session, "")
            assert await store.get_context_snapshot() == before
            assert io.print_error.called == (failure != "empty")
        await run_default(baseline, session, model, stream=stream, context=context, input=[])
        assert model.requests[0]["effective_snapshot"]["items"] == original
        assert (await store.get_history_items())[:-1] == original
        if manual:
            SlashCommands(io=io).cmd_compact(session, "")
        await run_default(baseline, session, model, stream=stream, context=context, input=[])
    assert client.completion.await_count == 2
    retry = model.requests[1]["effective_snapshot"]["items"]
    assert {"role": "user", "content": summary} in retry
    assert _paired_ids(retry) <= _paired_ids(original)
    assert (await store.get_history_items())[:len(original)] == original
    assert not (store.session_folder / "api_messages.json").exists()
