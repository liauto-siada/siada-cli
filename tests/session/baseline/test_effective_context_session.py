"""Real offline Runner coverage for identity-aware effective-context admission."""

import asyncio
import copy

import pytest
from agents import Agent, RunConfig, Runner, function_tool

from siada.services.effective_context_session import EffectiveContextSession
from siada.services.file_session import FileSession
from siada.services.session_storage import ContextVersionConflict, SessionStorageError


@pytest.mark.asyncio
@pytest.mark.parametrize("processor_name,field", [
    ("TodoReminderProcessor", "pending_reminder_items"),
    ("ModelHallucinationSuppressionProcessor", "pending_hallucination_reminder_items"),
    ("RepeatedToolReminderProcessor", "pending_repeated_tool_reminder_items"),
])
async def test_bridge_end_hooks_preserve_uncommitted_reminders(baseline, monkeypatch, processor_name, field):
    import importlib
    from agents import RunContextWrapper

    modules = {
        "TodoReminderProcessor": "todo_reminder_processor",
        "ModelHallucinationSuppressionProcessor": "model_hallucination_suppression_processor",
        "RepeatedToolReminderProcessor": "repeated_tool_reminder_processor",
    }
    module = importlib.import_module(
        "siada.agent_hub.hooks.processors." + modules[processor_name]
    )
    session = baseline.session()
    context = baseline.context(session)
    context.runtime_session = EffectiveContextSession(session.openai_session)
    pending = [{"role": "user", "content": "[uncommitted reminder]"}]
    setattr(context, field, copy.deepcopy(pending))

    async def unexpected_write(*args):
        pytest.fail("The legacy end hook must not write during bridge admission")

    monkeypatch.setattr(module, "persist_pending_reminder_items", unexpected_write)
    processor = getattr(module, processor_name)()
    await processor.on_llm_end(RunContextWrapper(context), None, None)
    assert getattr(context, field) == pending
    assert await session.openai_session.get_history_items() == []


async def run_bridge(baseline, session, model, *, stream=False, input="continue",
                     admission_id=None, tools=None, config=None, context=None, hooks=None, agent_hooks=None):
    bridge = EffectiveContextSession(session.openai_session, admission_id=admission_id)
    context = context or baseline.context(session)
    agent = Agent(name="baseline-agent", model=model, instructions="# Context", tools=tools or [], hooks=agent_hooks)
    run_config = bridge.configure_run(config or RunConfig(tracing_disabled=True), agent=agent)
    kwargs = dict(input=input, context=context, session=bridge, run_config=run_config, max_turns=8, hooks=hooks)
    if stream:
        result = Runner.run_streamed(agent, **kwargs)
        async for _ in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, **kwargs)
    return result


@pytest.mark.asyncio
async def test_identified_append_survives_compaction_and_cross_instance_retry(baseline):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    items = [{"role": "user", "content": "continue"}]
    observed = []

    async def notify(items):
        observed.append(items)

    store.on_items_added = notify
    assert await store.append_context_items(items, message_ids=["turn-1"]) == items
    assert await store.replace_context_items([], expected_version=1) == 2
    second = FileSession.from_file(store.history_file)
    assert await second.append_context_items(items, message_ids=["turn-1"]) == []
    assert await store.get_context_items() == []
    assert await store.append_context_items(items, message_ids=["turn-2"]) == items
    assert await store.get_history_items() == items + items
    assert observed == [items, items]
    assert store.native_item_count == 2
    with pytest.raises(SessionStorageError, match="different content"):
        await store.append_context_items([{"role": "user", "content": "changed"}], message_ids=["turn-1"])
    assert await store.get_context_items() == items


@pytest.mark.asyncio
async def test_identified_append_rolls_back_both_views_and_receipt(baseline, monkeypatch):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    update = store._update_metadata

    def fail(*args):
        raise OSError("synthetic metadata failure")

    monkeypatch.setattr(store, "_update_metadata", fail)
    items = [{"role": "user", "content": "admitted"}]
    with pytest.raises(OSError):
        await store.append_context_items(items, message_ids=["turn-1"])
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    monkeypatch.setattr(store, "_update_metadata", update)
    assert await store.append_context_items(items, message_ids=["turn-1"]) == items


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("auto_compact", [False, True])
async def test_real_runner_distinct_identical_turns_are_not_content_deduplicated(baseline, stream, auto_compact):
    session = baseline.session()
    session.siada_config.auto_compact = auto_compact
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second")]])
    for index in range(2):
        await run_bridge(baseline, session, model, stream=stream, admission_id=f"turn-{index}")
    items = await session.openai_session.get_context_items()
    assert len(items) == 4
    assert items == await session.openai_session.get_history_items()
    assert items.count({"role": "user", "content": "continue"}) == 2
    assert model.requests[1]["input"] == items[:-1]
    assert not any(key.startswith("_siada") for item in items for key in item)
    assert await session.openai_session.get_api_messages() == (None, -1)
    assert session.task_message_state.get_messages() == []
    assert session.task_message_state.get_real_messages() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_real_runner_mid_tool_compaction_cannot_replay_sdk_old_input(baseline, stream):
    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    baseline.compact_at = 5

    @function_tool
    def echo(value: str) -> str:
        """Return a deterministic tool output."""
        return value

    model = baseline.model(session, [
        [baseline.call("call-1", "echo", {"value": "one"})],
        [baseline.call("call-2", "echo", {"value": "two"})],
        [baseline.call("call-3", "echo", {"value": "three"})],
        [baseline.text("final")],
        [baseline.text("next")],
    ])
    await run_bridge(baseline, session, model, stream=stream, tools=[echo])
    assert [len(request["input"]) for request in model.requests] == [1, 3, 1, 3]
    assert model.requests[3]["input"][0]["content"] == "[baseline compaction summary]"
    assert not any(item.get("call_id") in {"call-1", "call-2"} for item in model.requests[3]["input"])
    history = await session.openai_session.get_history_items()
    assert len(history) == 8
    assert len(await session.openai_session.get_context_items()) == 4
    await run_bridge(baseline, session, model, stream=stream, input="next turn")
    assert len(await session.openai_session.get_history_items()) == 10
    assert not any(item.get("content") == "continue" for item in model.requests[4]["input"])


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_real_runner_failure_retry_reuses_explicit_admission_identity(baseline, stream):
    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    model = baseline.model(session, [RuntimeError("synthetic model failure"), [baseline.text("recovered")]])
    with pytest.raises(RuntimeError):
        await run_bridge(baseline, session, model, stream=stream, admission_id="logical-turn")
    assert await session.openai_session.get_context_items() == [{"role": "user", "content": "continue"}]
    await run_bridge(baseline, session, model, stream=stream, admission_id="logical-turn")
    assert len(await session.openai_session.get_context_items()) == 2
    assert len(await session.openai_session.get_history_items()) == 2
    assert model.requests[1]["input"] == [{"role": "user", "content": "continue"}]


@pytest.mark.asyncio
async def test_compaction_conflict_aborts_before_model_instead_of_overwriting(baseline):
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)

    async def conflict(data):
        await store.append_context_items([{"role": "user", "content": "arrived"}], message_ids=["concurrent"])
        data.model_data.input = []
        return data.model_data

    model = baseline.model(session, [[baseline.text("must not run")]])
    with pytest.raises(ContextVersionConflict):
        await run_bridge(baseline, session, model, config=RunConfig(tracing_disabled=True, call_model_input_filter=conflict))
    assert model.requests == []
    assert [item["content"] for item in await store.get_context_items()] == ["continue", "arrived"]


@pytest.mark.asyncio
async def test_prepared_append_keeps_bridge_usable_without_rebuilding_ui_history(baseline):
    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    await session.openai_session.add_items([{"role": "user", "content": "legacy"}])
    model = baseline.model(session, [[baseline.text("answer")]])
    await run_bridge(baseline, session, model)
    assert model.requests[0]["input"] == [
        {"role": "user", "content": "legacy"}, {"role": "user", "content": "continue"},
    ]


@pytest.mark.asyncio
async def test_bridge_preserves_custom_run_config_and_detaches_filter_input(baseline):
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    received = []

    async def custom(data):
        received.append(copy.deepcopy(data.model_data.input))
        return data.model_data

    config = RunConfig(tracing_disabled=True, workflow_name="custom", call_model_input_filter=custom)
    model = baseline.model(session, [[baseline.text("answer")]])
    await run_bridge(baseline, session, model, config=config)
    assert config.call_model_input_filter is custom
    assert config.session_input_callback is None
    assert received == [[{"role": "user", "content": "continue"}]]
    bridge = EffectiveContextSession(store)
    with pytest.raises(ValueError, match="owns"):
        bridge.configure_run(RunConfig(session_input_callback=lambda history, new: history + new))


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_post_filter_notifications_are_durable_before_failed_model_and_retry(baseline, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks

    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    context.hook_pending_contexts = ["[synthetic background completion]"]
    notice = {"role": "system", "content": context.hook_pending_contexts[0]}
    model = baseline.model(session, [RuntimeError("synthetic failure"), [baseline.text("retry")]])
    hooks = SiadaRunHooks(processors=[])
    with pytest.raises(RuntimeError):
        await run_bridge(baseline, session, model, stream=stream, hooks=hooks, context=context)
    assert context.hook_pending_contexts == []
    assert (await session.openai_session.get_context_items()).count(notice) == 1
    assert (await session.openai_session.get_history_items()).count(notice) == 1
    await run_bridge(baseline, session, model, stream=stream, hooks=hooks, context=context, input=[])
    assert model.requests[1]["input"].count(notice) == 1
    assert (await session.openai_session.get_history_items()).count(notice) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_todo_post_filter_reminder_commits_once_and_usage_has_no_history_mirror(baseline, stream):
    from siada.agent_hub.hooks.agent_processors.context_track_processor import ContextTrackProcessor
    from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks
    from siada.agent_hub.hooks.processors.todo_reminder_processor import (
        TodoReminderProcessor, TURNS_BETWEEN_REMINDERS_THRESHOLD, TURNS_SINCE_WRITE_THRESHOLD,
    )
    from siada.tools.todo.models import TodoItem
    from siada.tools.todo.todo_write_tool import todo_write

    session = baseline.session()
    store = session.openai_session
    history = [{"role": "user", "content": "original"}]
    for index in range(TURNS_SINCE_WRITE_THRESHOLD):
        history.append({"role": "user", "content": f"step {index}"})
        history.append(baseline.text(f"progress {index}", f"progress-{index}").model_dump(exclude_none=True))
    store.add_items_sync(history)
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    context.todos = [TodoItem(content="Add tests", active_form="Adding tests", status="in_progress")]
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD
    model = baseline.model(session, [RuntimeError("synthetic failure"), [baseline.text("retry")]])
    hooks = SiadaAgentHooks(processors=[ContextTrackProcessor(), TodoReminderProcessor()])
    with pytest.raises(RuntimeError):
        await run_bridge(baseline, session, model, stream=stream, context=context, agent_hooks=hooks, tools=[todo_write])
    reminders = [item for item in model.requests[0]["input"] if "<system-reminder>" in str(item)]
    assert len(reminders) == 1
    assert (await store.get_history_items()).count(reminders[0]) == 1
    assert context.pending_reminder_items == []
    await run_bridge(baseline, session, model, stream=stream, context=context, agent_hooks=hooks, input=[], tools=[todo_write])
    assert model.requests[1]["input"].count(reminders[0]) == 1
    assert (await store.get_history_items()).count(reminders[0]) == 1
    assert session.task_message_state.get_messages() == []
    assert session.state.usage.total_tokens == 150


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_hook_storage_failure_retains_notice_and_prevents_model_call(baseline, monkeypatch, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks

    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    context.hook_pending_contexts = ["[do not lose]"]
    update = store._update_metadata

    def fail(items):
        if any(item.get("content") == "[do not lose]" for item in items):
            raise OSError("synthetic hook admission failure")
        update(items)

    monkeypatch.setattr(store, "_update_metadata", fail)
    model = baseline.model(session, [[baseline.text("retry")]])
    hooks = SiadaRunHooks(processors=[])
    with pytest.raises(OSError):
        await run_bridge(baseline, session, model, stream=stream, context=context, hooks=hooks)
    assert model.requests == []
    assert context.hook_pending_contexts == ["[do not lose]"]
    assert await store.get_context_items() == [{"role": "user", "content": "continue"}]
    monkeypatch.setattr(store, "_update_metadata", update)
    await run_bridge(baseline, session, model, stream=stream, context=context, hooks=hooks, input=[])
    assert context.hook_pending_contexts == []
    assert model.requests[0]["input"].count({"role": "system", "content": "[do not lose]"}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_queued_input_identity_and_commit_notification_survive_model_failure(baseline, monkeypatch, stream):
    from siada.io import stdin_interrupt_monitor as monitor

    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    pending = [("queue-1", "queued input", None)]
    events = []

    def drain():
        result = list(pending)
        pending.clear()
        return result

    monkeypatch.setattr(monitor, "drain_pending_injections", drain)
    monkeypatch.setattr(monitor, "_send_queue_notification", lambda *args: events.append(args))
    model = baseline.model(session, [RuntimeError("synthetic failure"), [baseline.text("retry")]])
    with pytest.raises(RuntimeError):
        await run_bridge(baseline, session, model, stream=stream)
    assert events == [("queue_item_consumed", {"id": "queue-1", "content": "queued input"})]
    queued = {"role": "user", "content": "<user_input>queued input</user_input>"}
    assert (await session.openai_session.get_context_items()).count(queued) == 1
    pending.append(("queue-1", "queued input", None))
    await run_bridge(baseline, session, model, stream=stream, input=[])
    assert model.requests[1]["input"].count(queued) == 1
    assert (await session.openai_session.get_history_items()).count(queued) == 1


@pytest.mark.asyncio
async def test_queue_storage_failure_restores_original_order_without_consume_ack(baseline, monkeypatch):
    from collections import deque
    from siada.io import stdin_interrupt_monitor as monitor

    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    queued = [("queue-1", "first queued", None), ("queue-2", "second queued", None)]
    monkeypatch.setattr(monitor, "_pending_injections", deque(queued))
    monkeypatch.setattr(monitor, "drain_pending_injections", lambda: [monitor._pending_injections.popleft() for _ in range(len(monitor._pending_injections))])
    events = []
    monkeypatch.setattr(monitor, "_send_queue_notification", lambda *args: events.append(args))
    update = store._update_metadata

    def fail(items):
        if any("queued" in str(item.get("content")) for item in items):
            monitor._pending_injections.append(("queue-3", "arrived later", None))
            raise OSError("synthetic queued admission failure")
        update(items)

    monkeypatch.setattr(store, "_update_metadata", fail)
    model = baseline.model(session, [[baseline.text("must not run")]])
    with pytest.raises(OSError):
        await run_bridge(baseline, session, model)
    assert model.requests == [] and events == []
    assert list(monitor._pending_injections) == queued + [("queue-3", "arrived later", None)]
    assert await store.get_history_items() == [{"role": "user", "content": "continue"}]


@pytest.mark.asyncio
async def test_final_hook_admission_retry_does_not_duplicate_already_committed_tail(baseline):
    from agents.run import CallModelData, ModelInputData

    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    bridge = EffectiveContextSession(session.openai_session)
    context = baseline.context(session)
    await bridge.session_input_callback([], [{"role": "user", "content": "continue"}])
    config = bridge.configure_run(RunConfig())
    data = CallModelData(model_data=ModelInputData(input=[], instructions=""), agent=Agent(name="test"), context=context)
    filtered = await config.call_model_input_filter(data)
    filtered.input.append({"role": "system", "content": "notice"})
    await bridge.finalize_request_input(filtered.input)
    await bridge.finalize_request_input(filtered.input)
    assert (await session.openai_session.get_context_items()).count({"role": "system", "content": "notice"}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", ["todo", "hallucination", "repeated_tool"])
async def test_uncommitted_processor_reminder_survives_storage_failure_and_retries(baseline, monkeypatch, stream, kind):
    from siada.agent_hub.hooks.processors.model_hallucination_suppression_processor import ModelHallucinationSuppressionProcessor
    from siada.agent_hub.hooks.processors.repeated_tool_reminder_processor import RepeatedToolReminderProcessor
    from siada.agent_hub.hooks.processors.todo_reminder_processor import TodoReminderProcessor
    from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks

    field, processor = {
        "todo": ("pending_reminder_items", TodoReminderProcessor()),
        "hallucination": ("pending_hallucination_reminder_items", ModelHallucinationSuppressionProcessor()),
        "repeated_tool": ("pending_repeated_tool_reminder_items", RepeatedToolReminderProcessor()),
    }[kind]
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    reminder = {"role": "user", "content": f"<system-reminder>uncommitted {kind}</system-reminder>"}
    setattr(context, field, [reminder])
    update = store._update_metadata

    def fail(items):
        if reminder in items:
            raise OSError("synthetic reminder storage failure")
        update(items)

    monkeypatch.setattr(store, "_update_metadata", fail)
    model = baseline.model(session, [[baseline.text("retry")]])
    hooks = SiadaAgentHooks(processors=[processor])
    with pytest.raises(OSError):
        await run_bridge(baseline, session, model, stream=stream, context=context, agent_hooks=hooks)
    assert model.requests == []
    assert getattr(context, field) == [reminder]
    monkeypatch.setattr(store, "_update_metadata", update)
    await run_bridge(baseline, session, model, stream=stream, context=context, agent_hooks=hooks, input=[])
    assert model.requests[0]["input"].count(reminder) == 1
    assert (await store.get_history_items()).count(reminder) == 1
    assert getattr(context, field) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_notice_arriving_after_filter_is_captured_but_later_notice_is_retained(baseline, stream):
    from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks

    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    context = baseline.context(session)
    notice = {"role": "system", "content": "arrived during filter"}

    async def add_notice(data):
        data.context.hook_pending_contexts.append(notice["content"])
        return data.model_data

    async def after_commit(items):
        if notice in items:
            context.hook_pending_contexts.append("arrived during admission")

    store.on_items_added = after_commit
    model = baseline.model(session, [[baseline.text("done")]])
    await run_bridge(
        baseline, session, model, stream=stream, context=context, hooks=SiadaRunHooks(processors=[]),
        config=RunConfig(tracing_disabled=True, call_model_input_filter=add_notice),
    )
    assert model.requests[0]["input"].count(notice) == 1
    assert context.hook_pending_contexts == ["arrived during admission"]
    assert (await store.get_history_items()).count(notice) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_post_filter_context_conflict_aborts_before_provider(baseline, stream):
    from agents import RunHooks

    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)

    class ConflictingHooks(RunHooks):
        async def on_llm_start(self, context, agent, system_prompt, input_items):
            snapshot = await store.get_context_snapshot()
            await store.replace_context_items([], expected_version=snapshot["context_version"])

    model = baseline.model(session, [[baseline.text("must not run")]])
    with pytest.raises(ContextVersionConflict):
        await run_bridge(baseline, session, model, stream=stream, hooks=ConflictingHooks())
    assert model.requests == []
    assert await store.get_context_items() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_caller_cancellation_preserves_admission_and_closes_model(baseline, monkeypatch, stream):
    session = baseline.session()
    await session.openai_session.migrate_legacy_context(allow_history_only=True)
    model = baseline.model(session, [])
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def waiting(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(model, "_next", waiting)
    task = asyncio.create_task(run_bridge(baseline, session, model, stream=stream))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(stopped.wait(), 2)
        assert await session.openai_session.get_context_items() == [{"role": "user", "content": "continue"}]
        assert await session.openai_session.get_history_items() == await session.openai_session.get_context_items()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)