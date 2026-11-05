"""Offline request/response diagnostics and protocol-specific budget regressions."""

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents.usage import InputTokensDetails, Usage

from siada.agent_hub.context_filter import api_message_transfer_filter as transfer
from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult, CompactionStrategy
from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.services.effective_context_session import EffectiveContextSession
from tests.session.baseline.test_default_context_cutover import run_default


_REAL_TRY_COMPACT = transfer.ApiMessageTransferFilter._try_compact_real_api_messages


@pytest.fixture(autouse=True)
def budget_logs(baseline, monkeypatch, caplog):
    logger = logging.getLogger(__name__)
    caplog.set_level(logging.INFO, logger=logger.name)
    for module in (estimator, transfer, importlib.import_module("siada.services.effective_context_session"),
                   importlib.import_module("siada.agent_hub.context_filter.compaction_strategy")):
        monkeypatch.setattr(module, "logger", logger)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
async def test_full_responses_buffer_crosses_shared_threshold_but_usage_and_delta_do_not(
    baseline, monkeypatch, caplog, stream, native, strategy_type,
):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(side_effect=[506_019, 10, 10])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    strategy = strategy_type()
    summary = [{"role": "user", "content": "synthetic compacted summary"}]
    implementation = AsyncMock(return_value=CompactionResult(messages=summary, summary="synthetic summary", compacted=True))
    monkeypatch.setattr(strategy, "_compact_impl", implementation)
    monkeypatch.setattr(transfer, "get_compaction_strategy", lambda _: strategy)
    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", _REAL_TRY_COMPACT)
    monkeypatch.setattr(CompactionStrategy, "calculate_fixed_overhead", lambda *args, **kwargs: 0)
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second", "second")]], usages=[
        Usage(requests=1, input_tokens=100, output_tokens=20, total_tokens=220,
              input_tokens_details=InputTokensDetails(cached_tokens=100, cache_write_tokens=0)),
        baseline.usage(80, 20),
    ])
    model.model = "glm-effective"
    model.supports_native_responses_items = native
    await run_default(baseline, session, model, stream=stream, context=context, input="synthetic sensitive input")
    assert implementation.await_count == int(native)
    assert session.state.context_token_baseline.input_tokens == 200
    assert session.state.context_token_baseline.context_tokens == 220
    if native:
        assert model.requests[0]["input"] == summary
        assert "tokens=759043 context_window=1000000 threshold=750000 remaining=240957 action=compact" in caplog.text
        assert "comparison=unavailable reason=admitted_input_changed" in caplog.text
    else:
        assert "tokens=506029 context_window=1000000 threshold=750000 remaining=493971 action=skip" in caplog.text
    await run_default(baseline, session, model, stream=stream, context=context, input="continue")
    assert counter.call_count == 3
    assert implementation.await_count == int(native)
    assert "delta_count=1 delta_tokens=10 total=230" in caplog.text
    assert "token_mode=delta_only" in caplog.text
    assert "request_budget_tokens=230 server_input_tokens=80" in caplog.text
    assert "comparison=overestimate" in caplog.text
    assert "synthetic sensitive input" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("pre_buffer", [20, 200, 220])
async def test_response_comparison_uses_cache_inclusive_usage_without_recounting(
    baseline, monkeypatch, caplog, stream, native, pre_buffer,
):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(side_effect=[pre_buffer, 0])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    model = baseline.model(session, [[baseline.text("synthetic sensitive reply")]], usages=[
        Usage(requests=1, input_tokens=100, output_tokens=20, total_tokens=220,
              input_tokens_details=InputTokensDetails(cached_tokens=100, cache_write_tokens=0)),
    ])
    model.model = "glm-effective"
    model.supports_native_responses_items = native
    await run_default(baseline, session, model, stream=stream, context=context)
    effective_budget = pre_buffer * 3 // 2 if native else pre_buffer
    assert counter.call_count == 2
    assert f"request_budget_tokens={effective_budget} server_input_tokens=200" in caplog.text
    assert "reported_input_tokens=100 cached_tokens=100" in caplog.text
    expected = "matched" if effective_budget == 200 else "underestimate" if effective_budget < 200 else "overestimate"
    assert f"comparison={expected}" in caplog.text
    assert f"budget_minus_server_tokens={effective_budget - 200}" in caplog.text
    assert "synthetic sensitive reply" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
@pytest.mark.parametrize("outcome", ["no_compressible_history", "empty_summary", "failed", "cancelled"])
async def test_compaction_outcome_logs_preserve_original_input(baseline, monkeypatch, caplog, strategy_type, outcome):
    import asyncio

    strategy = strategy_type()
    model_config = baseline.session().siada_config.llm_config
    messages = [{"role": "user", "content": "synthetic sensitive input"}]
    if outcome != "no_compressible_history":
        for index in range(20):
            messages.extend([
                {"role": "user", "content": f"old turn {index}"},
                {"role": "assistant", "content": "synthetic answer"},
            ])
    monkeypatch.setattr(strategy, "_count_tokens", lambda *args: 0)
    error = RuntimeError("synthetic sensitive failure") if outcome == "failed" else asyncio.CancelledError()
    summary = AsyncMock(return_value=None, side_effect=error if outcome in {"failed", "cancelled"} else None)
    monkeypatch.setattr(strategy, "call_llm_to_compact", summary)
    original = list(messages)
    if outcome in {"failed", "cancelled"}:
        with pytest.raises(type(error)):
            await strategy.compact(model_config, messages)
        assert f"status={outcome}" in caplog.text
    else:
        result = await strategy.compact(model_config, messages)
        assert not result.compacted and result.messages is messages
        assert result.reason == outcome
        assert f"reason={outcome}" in caplog.text
    assert messages == original
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_hook_changed_input_disables_comparison_without_leaking_budget_to_next_request(
    baseline, monkeypatch, caplog, stream, native,
):
    from agents import RunHooks

    class AdditionalInput(RunHooks):
        async def on_llm_start(self, context, agent, system_prompt, input_items):
            input_items.append({"role": "user", "content": "synthetic sensitive hook"})

    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(side_effect=[10, 0, 10])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second", "second")]])
    model.model = "glm-effective"
    model.supports_native_responses_items = native
    await run_default(baseline, session, model, stream=stream, context=context, hooks=AdditionalInput())
    assert "comparison=unavailable reason=admitted_input_changed budget_minus_server_tokens=unavailable" in caplog.text
    caplog.clear()
    await run_default(baseline, session, model, stream=stream, context=context)
    assert counter.call_count == 3
    assert "request_budget_tokens=160 server_input_tokens=120" in caplog.text
    assert "input_matches=True comparison=overestimate" in caplog.text
    assert context.runtime_session._request_budget is None
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.parametrize("damage", ["missing", "invalid_counts", "invalid_details"])
def test_response_diagnostics_reject_invalid_usage_without_logging_objects(baseline, caplog, damage):
    bridge = EffectiveContextSession(baseline.session().openai_session)
    items = [{"role": "user", "content": "synthetic sensitive input"}]
    bridge.record_request_budget(100, "recount_all", "responses", items, "# Test")
    bridge._request_input = items
    bridge._request_instructions = "# Test"
    usage = SimpleNamespace(requests=1, input_tokens=100, output_tokens=20, total_tokens=120,
                            input_tokens_details=SimpleNamespace(cached_tokens="synthetic sensitive details"))
    if damage == "missing":
        usage = None
    elif damage == "invalid_counts":
        usage.input_tokens = "synthetic sensitive counts"
    bridge._log_response_budget(SimpleNamespace(usage=usage))
    assert "synthetic sensitive" not in caplog.text
    assert "cached_tokens=unavailable" in caplog.text
    assert f"comparison={'matched' if damage == 'invalid_details' else 'unavailable'}" in caplog.text
    assert bridge._request_budget is None
