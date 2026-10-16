"""Exercise the public execution boundary and prepared command consumers offline."""

import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from agents import Agent, RunConfig, RunContextWrapper, RunHooks, function_tool

from siada.agent_hub.hooks.agent_processors.context_track_processor import ContextTrackProcessor
from siada.agent_hub.siada_agent import SiadaAgent
from siada.services.session_management import SessionManager
from siada.services.session_storage import SessionStorageError
from siada.support.resume_service import ResumeService
from siada.support.slash_commands import SlashCommands


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("operation", ["resume", "model", "resume_then_model", "reset_before_resume"])
async def test_legacy_commands_preserve_boundary_until_default_migration(baseline, monkeypatch, stream, operation):
    session = baseline.session("source")
    store = session.openai_session
    history = [
        {"role": "user", "content": "discarded original"},
        {"role": "assistant", "content": "pending reply"},
    ]
    await store.add_items(history)
    summary = [{"role": "user", "content": "saved summary"}]
    from siada.services.session_signature import compute_last_item_signature

    items = summary + history[:1] if operation == "reset_before_resume" else summary
    SessionManager.sync_api_messages(
        store.session_folder, store.session_id, items,
        last_index=-1 if operation == "reset_before_resume" else 0,
        last_signature="" if operation == "reset_before_resume" else compute_last_item_signature(history[:1]),
    )
    legacy_file = store.session_folder / "api_messages.json"
    before = legacy_file.read_bytes()
    if operation != "model":
        resume = ResumeService(session.siada_config.workspace)
        data = resume.session_manager.load_session(session.session_id, store.session_folder)
        target = baseline.session("target")
        resume.restore_to_running_session(data, target)
        session = target
        assert session.openai_session.session_folder == store.session_folder
    if operation in ("model", "resume_then_model"):
        from siada.models.model_base_config import ModelBaseConfig

        commands = SlashCommands(io=MagicMock())
        monkeypatch.setattr(commands, "_persist_model_to_conf", lambda _: None)
        monkeypatch.setattr("siada.support.slash_commands.ModelInfoService.is_model_supported", lambda _: True)
        monkeypatch.setattr(
            "siada.models.model_run_config.get_model_config",
            lambda name: ModelBaseConfig(model_name=name, context_window=1_000_000),
        )
        session.siada_config.llm_config.provider = "default"
        event = commands.cmd_model(session, "migration-test-model")
        assert event is not None
        assert session.siada_config.llm_config.model_name == "migration-test-model"
    assert not store.context_file.exists()
    assert legacy_file.read_bytes() == before
    model = baseline.model(session, [[baseline.text("resumed answer")]])
    await run_default(baseline, session, model, stream=stream, input="continue")
    assert model.requests[0]["input"] == items + history[1:] + [{"role": "user", "content": "continue"}]
    assert (await store.get_history_items())[:2] == history
    assert legacy_file.read_bytes() == before


async def run_default(baseline, session, model, *, stream, config=None, input="new turn",
                      context=None, hooks=None, tools=None):
    agent = Agent(name="default-boundary", model=model, instructions="# Test",
                  hooks=ContextTrackProcessor(), tools=tools or [])
    driver = SimpleNamespace(_attach_plugin_guardrails=lambda value: value)
    method = SiadaAgent.run_streamed_impl if stream else SiadaAgent.run_impl
    result = await method(
        driver, agent, input, context=context or baseline.context(session), openai_session=session.openai_session,
        run_config=config or RunConfig(tracing_disabled=True), hooks=hooks or RunHooks(),
    )
    if stream:
        async for _ in result.stream_events():
            pass
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "only summary"}]])
async def test_default_entry_uses_prepared_context_and_preserves_ui_history(baseline, stream, items):
    session = baseline.session()
    store = session.openai_session
    history = [{"role": "user", "content": "discarded original"}]
    await store.add_items(history)
    await store.migrate_legacy_context(allow_history_only=True)
    await store.replace_context_items(items, expected_version=0)
    observed = []

    async def custom(data):
        observed.append(copy.deepcopy(data.model_data.input))
        return data.model_data

    config = RunConfig(tracing_disabled=True, workflow_name="custom", call_model_input_filter=custom)
    model = baseline.model(session, [[baseline.text("answer")], [baseline.text("second answer", "second")]])
    await run_default(baseline, session, model, stream=stream, config=config)
    first_context = await store.get_items()
    await run_default(baseline, session, model, stream=stream, config=config)
    assert model.requests[0]["input"] == items + [{"role": "user", "content": "new turn"}]
    assert model.requests[1]["input"] == first_context + [{"role": "user", "content": "new turn"}]
    assert observed == [request["input"] for request in model.requests]
    assert model.requests[0]["history"][:1] == history
    assert (await store.get_history_items())[:1] == history
    assert config.call_model_input_filter is custom and config.session_input_callback is None
    assert session.task_message_state.get_messages() == []
    assert session.task_message_state.get_real_messages() == []
    assert not (store.session_folder / "api_messages.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_default_tool_loop_compaction_keeps_results_and_never_rebuilds_history(baseline, stream):
    session = baseline.session()
    store = session.openai_session
    baseline.compact_at = 5

    @function_tool
    def echo(value: str) -> str:
        """Return a deterministic result for the default Runner boundary."""
        return value

    model = baseline.model(session, [
        [baseline.call("default-call-1", "echo", {"value": "one"})],
        [baseline.call("default-call-2", "echo", {"value": "two"})],
        [baseline.text("done")],
        [baseline.text("continued", "continued")],
    ])
    await run_default(baseline, session, model, stream=stream, tools=[echo])
    history = await store.get_history_items()
    summary = [{"role": "user", "content": "[baseline compaction summary]"}]
    assert [len(request["input"]) for request in model.requests] == [1, 3, 1]
    assert model.requests[2]["input"] == summary
    assert len(baseline.compactions) == 1
    assert [item.get("output") for item in history if item.get("type") == "function_call_output"] == ["one", "two"]
    assert len(history) == 6 and summary[0] not in history
    assert await store.get_items() == summary + history[-1:]
    await run_default(baseline, session, model, stream=stream, input="continue", tools=[echo])
    assert model.requests[3]["input"] == summary + history[-1:] + [{"role": "user", "content": "continue"}]
    assert len(await store.get_history_items()) == 8
    assert session.task_message_state.get_messages() == session.task_message_state.get_real_messages() == []
    assert not (store.session_folder / "api_messages.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_default_failed_request_retries_durable_notice_without_duplicate_admission(baseline, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
    from siada.services.session_runtime_state import load_state, notification_identity

    session = baseline.session()
    store = session.openai_session
    context = baseline.context(session)
    context.hook_pending_contexts = ["[synthetic default completion]"]
    notice = {"role": "system", "content": context.hook_pending_contexts[0]}
    model = baseline.model(session, [RuntimeError("synthetic failure"), [baseline.text("retried")]])
    hooks = SiadaRunHooks(processors=[])
    with pytest.raises(RuntimeError, match="synthetic failure"):
        await run_default(baseline, session, model, stream=stream, context=context, hooks=hooks)
    assert context.hook_pending_contexts == []
    assert (await store.get_items()).count(notice) == (await store.get_history_items()).count(notice) == 1
    state = load_state(store.session_folder, session.session_id)
    assert notification_identity(notice["content"]) in state["delivered_notifications"]
    await run_default(baseline, session, model, stream=stream, input=[], hooks=hooks)
    assert model.requests[1]["input"] == model.requests[0]["input"]
    assert (await store.get_history_items()).count(notice) == 1
    assert len(await store.get_items()) == len(await store.get_history_items()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("legacy", ["empty", "valid", "unknown", "corrupt"])
async def test_default_preparation_validates_legacy_boundary(baseline, stream, legacy):
    session = baseline.session()
    store = session.openai_session
    if legacy != "empty":
        await store.add_items([{"role": "user", "content": "old"}])
    summary = [{"role": "user", "content": "migrated summary"}]
    if legacy == "valid":
        SessionManager.sync_api_messages(
            store.session_folder, store.session_id, summary, last_index=0, last_signature=store.last_signature,
        )
    elif legacy == "corrupt":
        (store.session_folder / "api_messages.json").write_text("not json", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    model = baseline.model(session, [[baseline.text("answer")]])
    if legacy in ("unknown", "corrupt"):
        with pytest.raises(SessionStorageError):
            await run_default(baseline, session, model, stream=stream)
        assert model.requests == []
        assert not store.context_file.exists()
        assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    else:
        await run_default(baseline, session, model, stream=stream)
        assert store.has_prepared_context
        assert model.requests[0]["input"] == (summary if legacy == "valid" else []) + [
            {"role": "user", "content": "new turn"},
        ]


@pytest.mark.asyncio
async def test_obsolete_tracking_write_preserves_prepared_storage(baseline):
    store = baseline.session().openai_session
    SessionManager.sync_api_messages(store.session_folder, store.session_id, [])
    await store.migrate_legacy_context(allow_history_only=True)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    with pytest.raises(SessionStorageError, match="legacy snapshot"):
        SessionManager.update_api_messages_tracking(store.session_folder, -1, "")
    assert await store.get_items() == []
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt", [False, True])
async def test_fork_reads_detached_effective_context_and_propagates_corruption(baseline, corrupt):
    from siada.tools.agent.run_subtask import _build_fork_materials

    session = baseline.session()
    store = session.openai_session
    await store.add_items([{"role": "user", "content": "discarded"}])
    await store.migrate_legacy_context(allow_history_only=True)
    items = [{"role": "user", "content": "summary"}]
    await store.replace_context_items(items, expected_version=0)
    run_context = RunContextWrapper(context=baseline.context(session))
    if corrupt:
        store.context_file.write_text("{}", encoding="utf-8")
        with pytest.raises(SessionStorageError):
            await _build_fork_materials(run_context)
    else:
        _, _, fork = await _build_fork_materials(run_context)
        assert fork == items
        fork[0]["content"] = "changed fork"
        assert await store.get_items() == items


@pytest.mark.asyncio
@pytest.mark.parametrize("interfere", [False, True])
async def test_manual_compact_commits_only_effective_view_with_version_check(baseline, monkeypatch, interfere):
    from siada.services.siada_runner import SiadaRunner
    from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

    session = baseline.session()
    store = session.openai_session
    history = [{"role": "user", "content": "full history"}]
    await store.add_items(history)
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    context.task_message_state.reset_message_history([{"role": "user", "content": "stale mirror"}])
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
    monkeypatch.setattr(CompactionStrategy, "calculate_fixed_overhead", lambda _: 0)
    seen = []
    summary = [{"role": "user", "content": "summary"}]

    async def compact(**kwargs):
        seen.append(kwargs["real_api_messages"])
        if interfere:
            store.append_context_items_sync([{"role": "user", "content": "concurrent"}], message_ids=["concurrent"])
        return SimpleNamespace(compacted=True, messages=summary)

    monkeypatch.setattr(
        "siada.agent_hub.context_filter.compaction_strategy.get_compaction_strategy",
        lambda _: SimpleNamespace(compact=compact),
    )
    io = MagicMock()
    SlashCommands(io=io).cmd_compact(session, "")
    assert seen == [history]
    assert await store.get_items() == (history + [{"role": "user", "content": "concurrent"}] if interfere else summary)
    assert (await store.get_history_items())[:1] == history
    assert not (store.session_folder / "api_messages.json").exists()
    assert io.print_error.called is interfere


@pytest.mark.asyncio
async def test_prepared_clear_fences_existing_run_and_can_accept_fresh_messages(baseline):
    from siada.services.effective_context_session import EffectiveContextSession

    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    await store.add_items([{"role": "user", "content": "old"}])
    store.inject_items([{"role": "user", "content": "route", "message_id": "route-id"}], "source")
    bridge = EffectiveContextSession(store)
    await bridge.get_items()
    await store.clear_session()
    assert await store.get_items() == await store.get_all_items() == await store.get_history_items() == []
    assert store.native_item_count == 0 and store.get_inject_info() is None
    with pytest.raises(SessionStorageError):
        await bridge.get_items()
    await store.add_items([{"role": "user", "content": "fresh"}])
    assert await store.get_items() == await store.get_history_items() == [{"role": "user", "content": "fresh"}]