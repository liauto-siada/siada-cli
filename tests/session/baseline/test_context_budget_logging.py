"""Budget/compaction diagnostics describe durable boundaries without content."""

import asyncio
import importlib
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import RunConfig, function_tool
from agents.usage import Usage

from siada.agent_hub.context_filter import api_message_transfer_filter as transfer
from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult, CompactionStrategy
from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.provider.token_counting import TokenCountingInfo, token_counting_info_from_model
from siada.services import session_runtime_state as state
from siada.services.session_storage import SessionStorageError

from tests.session.baseline.test_default_context_cutover import run_default


_REAL_TRY_COMPACT = transfer.ApiMessageTransferFilter._try_compact_real_api_messages


@pytest.fixture(autouse=True)
def trace_logs(baseline, monkeypatch, caplog):
    logger = logging.getLogger(__name__)
    caplog.set_level(logging.DEBUG, logger=logger.name)
    for name in (
        "siada.foundation.logging", "siada.services.effective_context_session", "siada.services.model_wrapper",
        "siada.agent_hub.context_filter.request_token_estimator",
        "siada.agent_hub.context_filter.api_message_transfer_filter",
        "siada.agent_hub.context_filter.effective_context_filter",
        "siada.agent_hub.context_filter.compaction_strategy",
    ):
        monkeypatch.setattr(importlib.import_module(name), "logger", logger)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_route_signature_and_actual_model_logs_are_correlated(baseline, monkeypatch, caplog, stream, native):
    session = baseline.session()
    context = baseline.context(session)
    monkeypatch.setattr(estimator, "calculate_tokens", Mock(return_value=10))
    model = baseline.model(session, [[baseline.text("synthetic sensitive answer")]])
    model.model = "glm-effective"
    model.supports_native_responses_items = native
    info = token_counting_info_from_model(model)
    provider = SimpleNamespace(
        get_model=Mock(return_value=model), get_token_counting_info=Mock(return_value=info),
    )
    config = RunConfig(tracing_disabled=True, model="configured-alias", model_provider=provider)

    await run_default(
        baseline, session, "unused-model", stream=stream, config=config, context=context,
        input="synthetic sensitive input",
    )

    request = context.runtime_session.admission_id + ":request:0"
    for marker in ("[CTX-BUILD][route]", "status=route_selected", "[CTX-BUILD][model]"):
        records = [record for record in caplog.records if marker in record.getMessage()]
        assert records
        assert all(record.levelno == logging.DEBUG for record in records)
        assert all(f"session={session.session_id} request={request}" in record.getMessage() for record in records)
    assert "source=provider_route configured_model=configured-alias provider_type=SimpleNamespace" in caplog.text
    assert f"source=runtime_session protocol={info.protocol} native={native} info={info}" in caplog.text
    assert f"status=matched model_type=ScriptedModel expected_info={info} actual_info={info}" in caplog.text
    provider.get_token_counting_info.assert_called_once_with("configured-alias")
    provider.get_model.assert_called_once_with("configured-alias")
    assert len(model.requests) == 1
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_model_mismatch_logs_expected_and_actual_info_without_sending(baseline, monkeypatch, caplog, stream):
    session = baseline.session()
    monkeypatch.setattr(estimator, "calculate_tokens", Mock(return_value=10))
    model = baseline.model(session, [[baseline.text("synthetic sensitive answer")]])
    model.model = "glm-effective"
    model.supports_native_responses_items = True
    expected = TokenCountingInfo("glm-effective")
    actual = token_counting_info_from_model(model)
    provider = SimpleNamespace(
        get_model=Mock(return_value=model), get_token_counting_info=Mock(return_value=expected),
    )
    config = RunConfig(tracing_disabled=True, model="configured-alias", model_provider=provider)

    with pytest.raises(SessionStorageError, match="counting semantics changed"):
        await run_default(
            baseline, session, "unused-model", stream=stream, config=config,
            input="synthetic sensitive input",
        )

    assert f"status=counting_mismatch model_type=ScriptedModel expected_info={expected} actual_info={actual}" in caplog.text
    assert model.requests == []
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_budget_compaction_and_resume_trace_preserves_counting(baseline, monkeypatch, caplog, stream):
    session = baseline.session()
    session.siada_config.llm_config.context_window = 61_000
    context = baseline.context(session)
    counter = Mock(side_effect=[200, 10, 10, 100])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    signature = Mock(wraps=estimator.request_token_signature)
    monkeypatch.setattr(estimator, "request_token_signature", signature)
    strategy = SummarizeWithHeaderCompaction()
    summary = [{"role": "user", "content": "synthetic sensitive summary"}]
    implementation = AsyncMock(return_value=CompactionResult(messages=summary, summary=summary[0]["content"], compacted=True))
    monkeypatch.setattr(strategy, "_compact_impl", implementation)
    monkeypatch.setattr(transfer, "get_compaction_strategy", lambda _: strategy)
    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", _REAL_TRY_COMPACT)
    monkeypatch.setattr(CompactionStrategy, "calculate_fixed_overhead", lambda *args, **kwargs: 0)
    model = baseline.model(session, [
        [baseline.text("synthetic sensitive answer", "first")],
        [baseline.text("second answer", "second")], [baseline.text("third answer", "third")],
    ], usages=[baseline.usage(900, 100), baseline.usage(50, 10), baseline.usage(80, 20)])

    for input in ("synthetic sensitive input", "continue"):
        await run_default(baseline, session, model, stream=stream, context=context, input=input)
    saved = state.load_state(session.openai_session.session_folder, session.session_id)
    state.restore_response_usage(session, saved)
    await run_default(baseline, session, model, stream=stream, context=context, input="resume")

    implementation.assert_awaited_once()
    assert counter.call_count == 4
    assert signature.call_count == 6  # Estimate and final admission, not filter commit.
    assert model.requests[1]["input"] == summary
    assert "tokens=1010 context_window=61000 threshold=1000 remaining=59990 action=compact" in caplog.text
    assert "baseline_source=server_usage" in caplog.text
    assert "anchor=restored" in caplog.text
    messages = [record.getMessage() for record in caplog.records]
    cursor = 0
    for fragment in (
        "token_mode=recount_all", "stage=filter_committed", "stage=hooks_pending",
        "stage=hooks_committed", "stage=response_staged", "stage=response_committed",
        "token_mode=delta_only", "action=compact", "[CTX-COMPACT][strategy] stage=start",
        "[CTX-COMPACT][strategy] stage=complete", "[CTX-COMPACT][filter]", "stage=filter_committed",
        "stage=response_committed", "anchor=restored", "token_mode=delta_only",
    ):
        cursor = next(index for index in range(cursor, len(messages)) if fragment in messages[index]) + 1
    assert "synthetic sensitive input" not in caplog.text
    assert "synthetic sensitive answer" not in caplog.text
    assert "synthetic sensitive summary" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_info_logs_pair_tool_loop_and_resumed_budgets(baseline, monkeypatch, caplog, stream, native):
    caplog.set_level(logging.INFO, logger=__name__)
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(side_effect=[200, 10, 25, 15])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)

    @function_tool
    def echo(value: str) -> str:
        """Return a synthetic tool result without accessing external services."""
        return value

    model = baseline.model(session, [
        [baseline.call("info-call", "echo", {"value": "synthetic sensitive tool result"})],
        [baseline.text("synthetic sensitive answer", "first")],
        [baseline.text("synthetic sensitive resumed answer", "second")],
    ], usages=[
        Usage(requests=1, input_tokens=100, output_tokens=100, total_tokens=1000),
        baseline.usage(180, 20), baseline.usage(190, 30),
    ])
    model.model = "glm-effective"
    model.supports_native_responses_items = native

    await run_default(
        baseline, session, model, stream=stream, context=context, tools=[echo],
        input="synthetic sensitive input",
    )
    first_admission = context.runtime_session.admission_id
    saved = state.load_state(session.openai_session.session_folder, session.session_id)
    fingerprints = saved["context_token_baseline"]["signature_components"]
    assert set(fingerprints) == estimator._SIGNATURE_COMPONENTS
    state.restore_response_usage(session, saved)
    assert session.state.context_token_baseline.signature_components == fingerprints
    await run_default(
        baseline, session, model, stream=stream, context=context, tools=[echo],
        input="synthetic sensitive resume input",
    )
    requests = [
        f"{first_admission}:request:0", f"{first_admission}:request:1",
        f"{context.runtime_session.admission_id}:request:0",
    ]
    effective = [record for record in caplog.records if "[CTX-BUILD][effective]" in record.getMessage()]
    committed = [record for record in caplog.records if "stage=response_committed" in record.getMessage()]
    assert len(effective) == len(committed) == len(model.requests) == 3
    assert counter.call_count == 4
    for request, budget, anchor in zip(requests, effective, committed):
        assert budget.levelno == anchor.levelno == logging.INFO
        assert f"session={session.session_id} request={request}" in budget.getMessage()
        assert f"session={session.session_id} request={request}" in anchor.getMessage()
        assert "anchored=True baseline_source=server_usage restore_generation=0" in anchor.getMessage()
    assert "token_mode=recount_all reason=no_baseline" in effective[0].getMessage()
    assert "total=210" in effective[0].getMessage()
    assert "prefix_items=2 input_tokens=900 response_tokens=100 baseline_tokens=1000" in committed[0].getMessage()
    assert "token_mode=delta_only baseline_source=server_usage" in effective[1].getMessage()
    assert "baseline_count=2 input_tokens=900 response_tokens=100 baseline_tokens=1000 delta_count=1 delta_tokens=25 total=1025" in effective[1].getMessage()
    assert "prefix_items=4 input_tokens=180 response_tokens=20 baseline_tokens=200" in committed[1].getMessage()
    assert "token_mode=delta_only baseline_source=server_usage" in effective[2].getMessage()
    assert "baseline_count=4 input_tokens=180 response_tokens=20 baseline_tokens=200 delta_count=1 delta_tokens=15 total=215" in effective[2].getMessage()
    restored = [record for record in caplog.records if "anchor=restored" in record.getMessage()]
    assert len(restored) == 1 and restored[0].levelno == logging.INFO
    assert "baseline_tokens=200" in restored[0].getMessage()
    records = caplog.records
    assert records.index(committed[0]) < records.index(effective[1]) < records.index(committed[1])
    assert records.index(committed[1]) < records.index(restored[0]) < records.index(effective[2])
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_info_logs_distinguish_saved_usage_without_anchor(baseline, monkeypatch, caplog, stream):
    caplog.set_level(logging.INFO, logger=__name__)
    session = baseline.session()
    monkeypatch.setattr(estimator, "calculate_tokens", lambda *args, **kwargs: 10)
    model = baseline.model(session, [[baseline.text("synthetic sensitive answer")]])
    monkeypatch.setattr(estimator, "request_token_signature", lambda *args, **kwargs: None)

    await run_default(baseline, session, model, stream=stream)

    committed = [record for record in caplog.records if "stage=response_committed" in record.getMessage()]
    assert len(committed) == 1 and committed[0].levelno == logging.INFO
    assert "anchored=False baseline_source=unavailable" in committed[0].getMessage()
    assert "prefix_items=0 input_tokens=0 response_tokens=0 baseline_tokens=0" in committed[0].getMessage()
    assert "token_mode=recount_all reason=signature_unavailable" in caplog.text
    assert "token_mode=delta_only" not in caplog.text
    assert session.state.context_token_baseline is None
    saved = state.load_state(session.openai_session.session_folder, session.session_id)
    assert saved["usage"] is not None and saved["context_token_baseline"] is None
    assert "synthetic sensitive" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("boundary", ["hooks", "response"])
async def test_failed_admission_never_logs_success_or_content(baseline, monkeypatch, caplog, stream, boundary):
    if boundary == "response":
        caplog.set_level(logging.INFO, logger=__name__)
    session = baseline.session()
    context = baseline.context(session)
    monkeypatch.setattr(estimator, "calculate_tokens", lambda *args, **kwargs: 10)
    model = baseline.model(session, [[baseline.text("synthetic sensitive answer")]])
    error = OSError("synthetic sensitive failure")
    if boundary == "hooks":
        monkeypatch.setattr(state, "commit_request_state", Mock(side_effect=error))
    else:
        writer = state.write_json

        def fail_anchor(path, data):
            writer(path, data)
            if data.get("context_token_baseline") is not None:
                raise error

        monkeypatch.setattr(state, "write_json", fail_anchor)
    with pytest.raises(OSError, match="sensitive failure"):
        await run_default(baseline, session, model, stream=stream, context=context)
    assert f"stage={boundary}_commit_failed error_type=OSError" in caplog.text
    assert f"stage={boundary}_committed" not in caplog.text
    if boundary == "response":
        failures = [record for record in caplog.records if "stage=response_commit_failed" in record.getMessage()]
        assert len(failures) == 1 and failures[0].levelno == logging.INFO
        request = f"{context.runtime_session.admission_id}:request:0"
        assert f"session={session.session_id} request={request}" in failures[0].getMessage()
    assert session.state.context_token_baseline is None
    assert len(model.requests) == (0 if boundary == "hooks" else 1)
    assert "synthetic sensitive failure" not in caplog.text
    assert "synthetic sensitive answer" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["noop", "failure", "cancelled"])
async def test_strategy_trace_preserves_noop_and_error_contract(baseline, monkeypatch, caplog, outcome):
    session = baseline.session()
    original = [{"role": "user", "content": "synthetic sensitive history"}]
    strategy = SummarizeWithHeaderCompaction()
    if outcome == "noop":
        monkeypatch.setattr(strategy, "_compact_impl", AsyncMock(return_value=CompactionResult(messages=[])))
        result = await strategy.compact(session.siada_config.llm_config, original)
        assert result.messages is original
        assert "compacted=False before_items=1 after_items=1" in caplog.text
    else:
        error = asyncio.CancelledError("synthetic sensitive failure") if outcome == "cancelled" else RuntimeError("synthetic sensitive failure")
        monkeypatch.setattr(strategy, "_compact_impl", AsyncMock(side_effect=error))
        with pytest.raises(type(error)) as caught:
            await strategy.compact(session.siada_config.llm_config, original)
        assert caught.value is error
        assert f"error_type={type(error).__name__}" in caplog.text
        assert "stage=aborted" in caplog.text and "stage=complete" not in caplog.text
    assert "synthetic sensitive history" not in caplog.text
    assert "synthetic sensitive failure" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("damage, reason", [
    ("missing", "anchor=missing"), ("owner", "reason=storage_owner_mismatch"),
    ("prefix", "reason=invalid_metadata_or_prefix"),
])
async def test_resume_logs_missing_or_rejected_anchor(baseline, monkeypatch, caplog, damage, reason):
    caplog.set_level(logging.INFO, logger=__name__)
    session = baseline.session()
    monkeypatch.setattr(estimator, "calculate_tokens", lambda *args, **kwargs: 10)
    await run_default(baseline, session, baseline.model(session, [[baseline.text("synthetic sensitive answer")]]), stream=False)
    saved = state.load_state(session.openai_session.session_folder, session.session_id)
    snapshot = session.openai_session.get_context_snapshot_sync()
    if damage == "missing":
        saved["context_token_baseline"] = None
    elif damage == "owner":
        session.state.openai_session = baseline.session("another-session").openai_session
    else:
        snapshot["items"][0]["content"] = "synthetic sensitive rewrite"
    caplog.clear()
    state.restore_response_usage(session, saved, context_snapshot=snapshot)
    assert reason in caplog.text
    assert len(caplog.records) == 1 and caplog.records[0].levelno == logging.INFO
    assert session.state.usage is not None and session.state.context_token_baseline is None
    assert "synthetic sensitive" not in caplog.text