"""Real offline Runner coverage for response-calibrated compaction triggers."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import Agent, ModelSettings, RunConfig, function_tool
from agents.usage import Usage

from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter
from siada.agent_hub.context_filter import api_message_transfer_filter as transfer
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult
from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.services.session_runtime_state import load_state, record_response, restore_response_usage
from siada.services.input_processor import process_input
from siada.provider.token_counting import TokenCountingInfo, token_counting_info_from_model
from siada.services.model_wrapper import ModelWrapper
from siada.services.session_storage import SessionStorageError
from siada.services.siada_runner import SiadaRunner
from siada.support.resume_service import ResumeService
from siada.support.usage_utils import serialize_usage
from tests.session.baseline.test_default_context_cutover import run_default


_REAL_TRY_COMPACT = ApiMessageTransferFilter._try_compact_real_api_messages


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("override", ["string", "object"])
async def test_resolved_model_and_fresh_wrappers_preserve_warm_budget(
    baseline, monkeypatch, stream, native, override,
):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(side_effect=[200, 10, 25])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    unused = baseline.model(session, [[baseline.text("must not be called")]])
    unused.model = "declared-agent-model"
    resolved = []

    def get_model(name):
        index = len(resolved)
        model = baseline.model(session, [[baseline.text(f"reply-{index}", f"reply-{index}")]])
        model.model = "glm-effective"
        model.supports_native_responses_items = native
        wrapper = ModelWrapper(model, input_processor=process_input)
        resolved.append((name, wrapper))
        return wrapper

    provider = SimpleNamespace(
        get_model=get_model,
        get_token_counting_info=lambda name: TokenCountingInfo("glm-effective", "responses" if native else "chat"),
    )
    for index, input in enumerate(["first", "continue"]):
        selected = f"configured-alias-{index}" if override == "string" else get_model(None)
        config = RunConfig(
            tracing_disabled=True, model=selected, model_provider=provider,
            model_settings=ModelSettings(temperature=0.5 + index * 0.1, max_tokens=1000 + index),
        )
        await run_default(baseline, session, unused, stream=stream, config=config, context=context, input=input)
        assert context.runtime_session.token_counting_info == token_counting_info_from_model(resolved[-1][1])
        assert config.model is selected
    assert unused.requests == []
    assert len(resolved) == 2
    assert resolved[0][1].wrapped_model is not resolved[1][1].wrapped_model
    assert all(len(value.wrapped_model.requests) == 1 for _, value in resolved)
    assert counter.call_count == 3
    assert all(call.args[0] == "glm-effective" for call in counter.call_args_list)
    assert counter.call_args_list[2].args[1] == [{"role": "user", "content": "continue"}]
    assert counter.call_args_list[2].kwargs == {"diagnostics": {}}
    saved = load_state(session.openai_session.session_folder, session.session_id)
    assert saved["context_token_baseline"]["session_id"] == session.session_id
    assert saved["context_token_baseline"]["format_version"] == 4
    assert session.state.context_token_baseline.to_dict() == saved["context_token_baseline"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_opaque_processor_keeps_usage_durable_without_unsafe_anchor(baseline, monkeypatch, stream):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    model = baseline.model(session, [[baseline.text("first", "first")], [baseline.text("second", "second")]])
    processed = []

    def processor(items):
        processed.append(copy.deepcopy(items))
        return items

    wrapped = ModelWrapper(model, input_processor=processor)
    for input in ["first", "continue"]:
        await run_default(baseline, session, wrapped, stream=stream, context=context, input=input)
        saved = load_state(session.openai_session.session_folder, session.session_id)
        assert saved["usage"] == serialize_usage(session.state.usage)
        assert saved["context_token_baseline"] is None
        assert session.state.context_token_baseline is None
    assert processed == [request["input"] for request in model.requests]
    assert counter.call_count == 4
    assert counter.call_args_list[2].args[1] == model.requests[1]["input"]


@pytest.mark.asyncio
async def test_recovery_checks_storage_owner_separately_from_saved_signature(baseline):
    session = baseline.session()
    await run_default(baseline, session, baseline.model(session, [[baseline.text("saved")]]), stream=False)
    saved = load_state(session.openai_session.session_folder, session.session_id)
    snapshot = session.openai_session.get_context_snapshot_sync()
    session.state.openai_session = baseline.session("another-session").openai_session
    restore_response_usage(session, saved, context_snapshot=snapshot)
    assert serialize_usage(session.state.usage) == saved["usage"]
    assert session.state.context_token_baseline is None


def test_response_commit_rejects_anchor_from_another_session(baseline):
    session = baseline.session()
    context = baseline.context(session)
    usage = baseline.usage(900, 100)
    response = SimpleNamespace(usage=usage, response_id="synthetic-response")
    record_response(context, response)
    before = load_state(session.openai_session.session_folder, session.session_id)
    anchor = estimator.RequestTokenBaseline.from_response("signature", [], usage, session_id="another-session")
    with pytest.raises(SessionStorageError, match="anchor belongs to another session"):
        record_response(context, response, baseline=anchor)
    assert load_state(session.openai_session.session_folder, session.session_id) == before
    assert session.state.usage is usage and session.state.context_token_baseline is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_server_usage_plus_delta_triggers_compaction_across_turns(baseline, monkeypatch, stream):
    session = baseline.session()
    session.siada_config.llm_config.context_window = 61_000
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    old = [{"role": "user", "content": "synthetic history " * 50}]
    await store.append_context_items(old, message_ids=["synthetic-history"])
    counter = Mock(side_effect=[200, 10, 30, 15])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    attempts = []
    summary = [{"role": "user", "content": "synthetic compacted summary"}]
    strategy = SummarizeWithHeaderCompaction()
    strategy.compact = AsyncMock(return_value=CompactionResult(messages=summary, compacted=True))
    monkeypatch.setattr(transfer, "get_compaction_strategy", lambda _: strategy)

    async def compact(_, **kwargs):
        attempts.append(kwargs["tokens_count"])
        assert kwargs["model_config"].context_window == 61_000
        return await _REAL_TRY_COMPACT(_, **kwargs)

    monkeypatch.setattr(ApiMessageTransferFilter, "_try_compact_real_api_messages", compact)
    model = baseline.model(session, [
        [baseline.text("first reply", "first")], [baseline.text("after compact", "second")],
        [baseline.text("continued", "third")],
    ], usages=[
        Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000),
        Usage(requests=1, input_tokens=50, output_tokens=10, total_tokens=60),
        Usage(requests=1, input_tokens=80, output_tokens=20, total_tokens=100),
    ])
    await run_default(baseline, session, model, stream=stream, input="first")
    assert session.state.context_token_baseline.input_tokens == 900
    assert session.state.context_token_baseline.response_tokens == 100
    assert session.state.context_token_baseline.context_tokens == 1000
    first_reply = baseline.text("first reply", "first").model_dump(exclude_none=True)
    assert session.state.context_token_baseline.items == model.requests[0]["input"] + [first_reply]
    await run_default(baseline, session, model, stream=stream, input="second")
    assert model.requests[1]["input"] == summary
    assert session.state.context_token_baseline.items == summary + [baseline.text("after compact", "second").model_dump(exclude_none=True)]
    await run_default(baseline, session, model, stream=stream, input="third")
    assert attempts == [210, 1030, 75]
    strategy.compact.assert_awaited_once()
    assert old[0] not in model.requests[2]["input"]
    # Warm calls tokenize only new input, never response items or old schemas.
    assert counter.call_count == 4
    assert counter.call_args_list[2].args[1] == [{"role": "user", "content": "second"}]
    assert counter.call_args_list[2].kwargs == {"diagnostics": {}}
    assert counter.call_args_list[3].args[1] == [{"role": "user", "content": "third"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_failed_request_preserves_anchor_and_retry_estimate(baseline, monkeypatch, stream):
    session = baseline.session()
    counter = Mock(side_effect=[200, 10, 20, 20])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    budgets = []

    async def compact(_, **kwargs):
        budgets.append(kwargs["tokens_count"])
        return kwargs["real_api_messages"]

    monkeypatch.setattr(ApiMessageTransferFilter, "_try_compact_real_api_messages", compact)
    model = baseline.model(session, [
        [baseline.text("first", "first")], RuntimeError("synthetic failure"), [baseline.text("retried", "retried")],
    ], usages=[Usage(requests=1, input_tokens=900, output_tokens=100, total_tokens=1000),
               Usage(requests=1), Usage(requests=1, input_tokens=930, output_tokens=10, total_tokens=940)])
    await run_default(baseline, session, model, stream=stream, input="first")
    baseline_before_failure = session.state.context_token_baseline
    with pytest.raises(RuntimeError, match="synthetic failure"):
        await run_default(baseline, session, model, stream=stream, input="second")
    assert session.state.context_token_baseline is baseline_before_failure
    await run_default(baseline, session, model, stream=stream, input=[])
    assert budgets == [210, 1020, 1020]
    assert model.requests[1]["input"] == model.requests[2]["input"]
    assert counter.call_args_list[2].args[1] == counter.call_args_list[3].args[1] == [{"role": "user", "content": "second"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_post_filter_notice_belongs_to_usage_anchor_not_next_delta(baseline, monkeypatch, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks

    session = baseline.session()
    context = baseline.context(session)
    context.hook_pending_contexts = ["synthetic admitted notice"]
    notice = {"role": "system", "content": context.hook_pending_contexts[0]}
    counter = Mock(side_effect=[200, 10, 25])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    model = baseline.model(session, [[baseline.text("first", "first")], [baseline.text("second", "second")]])
    await run_default(baseline, session, model, stream=stream, context=context,
                      hooks=SiadaRunHooks(processors=[]), input="first")
    assert notice in session.state.context_token_baseline.items
    assert session.state.context_token_baseline.items == model.requests[0]["input"] + [baseline.text("first", "first").model_dump(exclude_none=True)]
    await run_default(baseline, session, model, stream=stream, context=context, input="second")
    assert counter.call_count == 3
    assert counter.call_args_list[-1].args[1] == [{"role": "user", "content": "second"}]
    assert model.requests[1]["input"].count(notice) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("compacted", [False, True])
async def test_resume_restores_usage_and_warm_request_anchor(baseline, monkeypatch, stream, compacted):
    original = baseline.session("original")
    counter = Mock(side_effect=[200, 10, 25])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    baseline.compact_at = 1 if compacted else None
    usage = baseline.usage(900, 100)
    first_reply = baseline.text("reply before resume", "before-resume")
    first_model = baseline.model(original, [[first_reply]], usages=[usage])
    await run_default(baseline, original, first_model, stream=stream, input="first")
    saved = load_state(original.openai_session.session_folder, original.session_id)
    saved_anchor = saved["context_token_baseline"]
    assert saved["usage"] == serialize_usage(usage)
    assert saved_anchor == original.state.context_token_baseline.to_dict()
    assert "items" not in saved_anchor
    assert "reply before resume" not in json.dumps(saved_anchor)
    baseline.compact_at = None

    fresh = baseline.session("fresh")
    fresh.state.usage = baseline.usage(9999, 10)
    old_store = fresh.openai_session
    resume = ResumeService(original.siada_config.workspace)
    data = resume.session_manager.load_session(original.session_id, original.openai_session.session_folder)
    resume.restore_to_running_session(data, fresh)
    assert fresh.openai_session is not old_store
    assert serialize_usage(fresh.state.usage) == serialize_usage(usage)
    assert fresh.state.context_token_baseline == original.state.context_token_baseline
    assert fresh.state.context_token_baseline is not original.state.context_token_baseline
    context = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert fresh.state.context_token_baseline.to_dict() == saved_anchor
    # Preserve the scripted provider's response-ID sequence across reconnecting.
    second_model = baseline.model(fresh, [[baseline.text("resumed reply", "after-resume")]])
    second_model.requests.extend(first_model.requests)
    await run_default(baseline, fresh, second_model, stream=stream, context=context, input="continue")
    assert counter.call_count == 3
    assert counter.call_args_list[2].args[1] == [{"role": "user", "content": "continue"}]
    assert counter.call_args_list[2].kwargs == {"diagnostics": {}}
    assert second_model.requests[-1]["input"][:-2] == first_model.requests[0]["input"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing_anchor", "invalid_anchor", "old_anchor", "old_response_anchor",
                                  "old_estimated_response_anchor", "owner", "missing_owner", "prefix", "restore", "model"])
async def test_resume_falls_back_only_for_unusable_anchor(baseline, monkeypatch, change):
    session = baseline.session()
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    model = baseline.model(session, [[baseline.text("reply")]])
    await run_default(baseline, session, model, stream=False, input="first")
    saved = load_state(session.openai_session.session_folder, session.session_id)
    snapshot = session.openai_session.get_context_snapshot_sync()
    if change == "missing_anchor":
        saved.pop("context_token_baseline")
    elif change == "invalid_anchor":
        saved["context_token_baseline"] = {"format_version": "bad"}
    elif change == "old_anchor":
        saved["context_token_baseline"]["format_version"] = 1
        saved["context_token_baseline"].pop("response_tokens")
    elif change == "old_response_anchor":
        saved["context_token_baseline"]["format_version"] = 2
    elif change == "old_estimated_response_anchor":
        saved["context_token_baseline"]["format_version"] = 3
        saved["context_token_baseline"]["response_tokens"] = 10
    elif change == "owner":
        saved["context_token_baseline"]["session_id"] = "another-session"
    elif change == "missing_owner":
        saved["context_token_baseline"].pop("session_id")
    elif change == "prefix":
        snapshot["items"][0]["content"] = "rewritten prefix"
    elif change == "restore":
        snapshot["restore_generation"] = 1
    elif change == "model":
        session.siada_config.llm_config.model_name = "changed-model"
    restore_response_usage(session, saved, context_snapshot=snapshot)
    assert serialize_usage(session.state.usage) == saved["usage"]
    if change != "model":
        assert session.state.context_token_baseline is None
    counter.reset_mock()
    context = baseline.context(session)
    context.runtime_session = SimpleNamespace(_restore_generation=0, token_counting_info=token_counting_info_from_model(model))
    agent = Agent(name="default-boundary", model=model)
    estimator.estimate_request_tokens(context, agent, snapshot["items"], "# Test")
    assert counter.call_count == 2


def test_resume_without_runtime_usage_clears_previous_session_anchor(baseline):
    session = baseline.session()
    session.state.usage = baseline.usage()
    session.state.context_token_baseline = object()
    restore_response_usage(session, None)
    assert session.state.usage is None
    assert session.state.context_token_baseline is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_tool_result_and_mid_run_user_input_are_post_response_delta(baseline, monkeypatch, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
    from siada.services.steering import SteeringQueue, current_steering

    session = baseline.session()
    context = baseline.context(session)
    queue = SteeringQueue(session.session_id)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    observed = []
    notice = {"role": "system", "content": "synthetic tool notification"}

    @function_tool
    def accept_correction() -> str:
        """Inspect hook timing and simulate user input during tool execution."""
        saved = load_state(session.openai_session.session_folder, session.session_id)
        # Raw usage is durable, but the SDK has not saved the response yet.
        assert saved["usage"] == serialize_usage(baseline.usage(900, 6000))
        assert saved["context_token_baseline"] is None
        assert session.state.context_token_baseline is None
        observed.extend(session.openai_session.get_context_snapshot_sync()["items"])
        queue.append("use the correction", "synthetic-correction")
        context.hook_pending_contexts.append(notice["content"])
        return "synthetic tool result"

    call = baseline.call("correction-call", "accept_correction", {})
    model = baseline.model(session, [[call], [baseline.text("corrected", "corrected")], [baseline.text("next", "next")]],
                           usages=[baseline.usage(900, 6000), baseline.usage(950, 100), baseline.usage(1000, 100)])
    token = current_steering.set(queue)
    try:
        await run_default(baseline, session, model, stream=stream, context=context, input="start",
                          tools=[accept_correction], hooks=SiadaRunHooks(processors=[]))
    finally:
        current_steering.reset(token)
    assert observed == model.requests[0]["input"]
    delta = counter.call_args_list[2].args[1]
    assert [item.get("type", item.get("role")) for item in delta] == ["function_call_output", "user"]
    assert delta[0]["output"] == "synthetic tool result"
    assert delta[1]["content"] == "<user_input>use the correction</user_input>"
    assert call.model_dump(exclude_none=True) not in delta
    assert notice in session.state.context_token_baseline.items
    assert model.requests[1]["input"].count(notice) == 1
    assert session.state.context_token_baseline.context_tokens == 1050
    counter.reset_mock()
    await run_default(baseline, session, model, stream=stream, context=context, input="continue",
                      tools=[accept_correction], hooks=SiadaRunHooks(processors=[]))
    assert counter.call_args_list[0].args[1] == [{"role": "user", "content": "continue"}]
    assert counter.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("failure", ["messages", "anchor"])
async def test_response_admission_failure_rolls_back_and_retries_without_duplicate_output(
    baseline, monkeypatch, stream, failure,
):
    from siada.services import session_runtime_state as state

    session = baseline.session()
    context = baseline.context(session)
    store = session.openai_session
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    reply = baseline.text("durable answer", "durable-answer")
    native_reply = reply.model_dump(exclude_none=True)
    usage = baseline.usage(900, 6000)
    model = baseline.model(session, [[reply]], usages=[usage])
    writer = state.write_json
    update = store._update_metadata

    def fail_messages(items):
        update(items)
        if native_reply in items:
            raise OSError("synthetic response admission failure")

    def fail_anchor(path, data):
        writer(path, data)
        if data.get("context_token_baseline") is not None:
            raise OSError("synthetic response admission failure")

    if failure == "messages":
        monkeypatch.setattr(store, "_update_metadata", fail_messages)
    else:
        monkeypatch.setattr(state, "write_json", fail_anchor)
    with pytest.raises(OSError, match="response admission failure"):
        await run_default(baseline, session, model, stream=stream, context=context, input="start")
    bridge = context.runtime_session
    pending = bridge._pending_response
    saved = load_state(store.session_folder, session.session_id)
    snapshot = store.get_context_snapshot_sync()
    assert saved["usage"] == serialize_usage(usage)
    assert saved["context_token_baseline"] is None
    assert session.state.usage == usage
    assert session.state.context_token_baseline is None
    assert snapshot["items"] == [{"role": "user", "content": "start"}]
    assert await store.get_history_items() == snapshot["items"]
    assert not any(":output:" in identity for identity in snapshot["message_receipts"])
    assert pending is not None
    monkeypatch.setattr(store, "_update_metadata", update)
    monkeypatch.setattr(state, "write_json", writer)
    await bridge.add_items([native_reply])
    assert bridge._pending_response is None
    assert session.state.context_token_baseline.items == snapshot["items"] + [native_reply]
    assert session.state.context_token_baseline.context_tokens == usage.total_tokens
    assert load_state(store.session_folder, session.session_id)["context_token_baseline"] == session.state.context_token_baseline.to_dict()
    counter.reset_mock()
    await bridge.add_items([native_reply])
    counter.assert_not_called()
    assert (await store.get_items()).count(native_reply) == (await store.get_history_items()).count(native_reply) == 1
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("reasoning_ids", ["preserve", "omit"])
@pytest.mark.parametrize("origin", ["same", "other"])
@pytest.mark.parametrize("model_name,native", [("glm-5.1", False), ("kimi-k3", False),
                                             ("kivy-qwen-3.8-max", False), ("gpt-5", True)])
async def test_post_response_anchor_uses_server_total_without_tokenizing_reasoning(
    baseline, monkeypatch, stream, reasoning_ids, origin, model_name, native,
):
    from openai.types.responses import ResponseReasoningItem

    session = baseline.session()
    session.siada_config.llm_config.model_name = model_name
    context = baseline.context(session)
    counter = Mock(side_effect=[10, 10])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    reasoning = ResponseReasoningItem(
        id="reasoning-synthetic", type="reasoning",
        summary=[{"type": "summary_text", "text": "synthetic reasoning"}],
        encrypted_content="synthetic-opaque-reasoning-state" if native else None,
        provider_data={"model": model_name if origin == "same" else "unrelated-model"},
    )
    reply = baseline.text("synthetic final answer", "reasoning-answer")
    usage = baseline.usage(900, 6000)
    usage.output_tokens_details.reasoning_tokens = 5900
    model = baseline.model(session, [[reasoning, reply]], usages=[usage])
    model.model = model_name
    model.supports_native_responses_items = native
    await run_default(baseline, session, model, stream=stream, context=context, input="start",
                      config=RunConfig(tracing_disabled=True, reasoning_item_id_policy=reasoning_ids))
    assert counter.call_count == 2
    anchor = session.state.context_token_baseline
    assert anchor is not None
    assert anchor.input_tokens == 900
    assert anchor.response_tokens == 6000
    assert anchor.context_tokens == usage.total_tokens
    assert anchor.items == await session.openai_session.get_items()
    assert ("id" in anchor.items[-2]) == (reasoning_ids == "preserve")
    saved = load_state(session.openai_session.session_folder, session.session_id)
    restore_response_usage(session, saved)
    assert session.state.context_token_baseline == anchor
    counter = Mock()
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    agent = Agent(name="default-boundary", model=model, instructions="# Test")
    assert estimator.estimate_request_tokens(context, agent, anchor.items, "# Test") == anchor.context_tokens
    counter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_empty_response_preserves_server_total_on_admitted_input(baseline, monkeypatch, stream):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    usage = baseline.usage(900, 6000)
    model = baseline.model(session, [[]], usages=[usage])
    await run_default(baseline, session, model, stream=stream, context=context, input="start")
    anchor = session.state.context_token_baseline
    assert anchor is not None
    assert anchor.items == model.requests[0]["input"]
    assert anchor.context_tokens == usage.total_tokens
    assert anchor.response_tokens == usage.output_tokens
    assert context.runtime_session._pending_response is None
    assert counter.call_count == 2
    counter.reset_mock()
    agent = Agent(name="default-boundary", model=model, instructions="# Test")
    assert estimator.estimate_request_tokens(context, agent, anchor.items, "# Test") == usage.total_tokens
    counter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_context_rewrite_before_response_save_discards_anchor_then_recalibrates(baseline, monkeypatch, stream):
    session = baseline.session()
    store = session.openai_session
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    summary = [{"role": "user", "content": "synthetic mid-tool summary"}]

    @function_tool
    async def rewrite_context() -> str:
        """Simulate compaction after response usage but before SDK message saving."""
        snapshot = await store.get_context_snapshot()
        await store.replace_context_items(summary, expected_version=snapshot["context_version"])
        return "rewritten"

    call = baseline.call("rewrite-call", "rewrite_context", {})
    reply = baseline.text("after rewrite", "after-rewrite")
    model = baseline.model(session, [[call], [reply]], usages=[baseline.usage(900, 100), baseline.usage(50, 100)])
    await run_default(baseline, session, model, stream=stream, context=context, input="start", tools=[rewrite_context])
    # The old request prefix cannot anchor the rewritten context. The next call
    # recounts that context, then its durable response establishes a fresh anchor.
    assert counter.call_count == 4
    assert counter.call_args_list[2].args[1] == model.requests[1]["input"]
    assert counter.call_args_list[2].kwargs == {"tools": [rewrite_context], "diagnostics": {}}
    assert counter.call_args_list[3].args[1] == "# Test"
    assert model.requests[1]["input"][0] == summary[0]
    assert {"role": "user", "content": "start"} not in model.requests[1]["input"]
    assert session.state.context_token_baseline.input_tokens == 50
    assert session.state.context_token_baseline.context_tokens == 150
    assert session.state.context_token_baseline.items == await store.get_items()


@pytest.mark.asyncio
async def test_usage_anchor_write_failure_keeps_disk_and_memory_pair(baseline, monkeypatch):
    from siada.services import session_runtime_state as state

    session = baseline.session()
    context = baseline.context(session)
    monkeypatch.setattr(estimator, "calculate_tokens", lambda *args, **kwargs: 10)
    first_model = baseline.model(session, [[baseline.text("first")]])
    await run_default(baseline, session, first_model, stream=False, context=context, input="first")
    previous = copy.deepcopy(load_state(session.openai_session.session_folder, session.session_id))
    previous_usage = session.state.usage
    previous_anchor = session.state.context_token_baseline
    response = SimpleNamespace(usage=baseline.usage(250, 50), response_id="synthetic-next-response")
    writer = state.write_json

    def fail(*args, **kwargs):
        writer(*args, **kwargs)
        raise OSError("synthetic usage commit failure")

    monkeypatch.setattr(state, "write_json", fail)
    with pytest.raises(OSError, match="usage commit failure"):
        state.record_response(context, response)
    assert load_state(session.openai_session.session_folder, session.session_id) == previous
    assert session.state.usage is previous_usage
    assert session.state.context_token_baseline is previous_anchor
    monkeypatch.setattr(state, "write_json", writer)
    state.record_response(context, response)
    updated = load_state(session.openai_session.session_folder, session.session_id)
    assert updated["usage"] == serialize_usage(response.usage)
    # Hook usage without a durable response admission cannot publish an anchor.
    assert updated["context_token_baseline"] is None
    assert session.state.context_token_baseline is None