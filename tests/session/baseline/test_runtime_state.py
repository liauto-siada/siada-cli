"""Business-state commits and repeated recovery must not replay delivered work."""

import copy
from types import SimpleNamespace

import pytest
from agents.run import CallModelData, ModelInputData
from agents import Agent, RunConfig

from siada.services.effective_context_session import EffectiveContextSession
from siada.services.goal.models import Goal
from siada.services.session_runtime_state import (
    apply_state, capture_context, load_state, notification_identity,
    record_response, restore_state, save_context,
)
from siada.services.session_storage import ContextVersionConflict, SessionStorageError, storage_transaction
from siada.support.usage_utils import serialize_usage
from siada.tools.todo.models import TodoItem


@pytest.mark.asyncio
async def test_request_commit_acknowledges_notices_with_messages_and_counters(baseline, monkeypatch):
    session = baseline.session()
    store = session.openai_session
    store.migrate_legacy_context_sync(allow_history_only=True)
    context = baseline.context(session)
    context.hook_pending_contexts = ["synthetic task notice"]
    context.todo_turns_since_write = 7
    context.todo_turns_since_reminder = 3
    save_context(context)
    bridge = EffectiveContextSession(store, admission_id="synthetic-request")
    await bridge.session_input_callback([], [{"role": "user", "content": "continue"}])
    config = bridge.configure_run(RunConfig(model=baseline.model(session, [])))
    model_data = await config.call_model_input_filter(CallModelData(
        model_data=ModelInputData(input=[], instructions=""), agent=Agent(name="test"), context=context,
    ))
    bridge.capture_pending_contexts(context.hook_pending_contexts)
    notice = {"role": "system", "content": context.hook_pending_contexts[0]}
    before = store.get_checkpoint_snapshot_sync()
    from siada.services import session_runtime_state as state

    writer = state.write_json
    monkeypatch.setattr(state, "write_json", lambda *args: (_ for _ in ()).throw(OSError("synthetic state failure")))
    with pytest.raises(OSError, match="state failure"):
        await bridge.finalize_request_input(model_data.input + [notice])
    assert store.get_checkpoint_snapshot_sync() == before
    assert context.hook_pending_contexts == [notice["content"]]
    monkeypatch.setattr(state, "write_json", writer)
    await bridge.finalize_request_input(model_data.input + [notice])
    saved = load_state(store.session_folder, session.session_id)
    assert saved["pending_notifications"] == []
    assert saved["delivered_notifications"] == [notification_identity(notice["content"])]
    assert saved["request_counters"]["synthetic-request:request:0"] == {
        "todo_turns_since_write": 7, "todo_turns_since_reminder": 3,
    }
    assert context.hook_pending_contexts == []
    assert store.get_context_snapshot_sync()["items"].count(notice) == 1
    fresh_context = baseline.context(session)
    apply_state(fresh_context, saved)
    assert fresh_context.hook_pending_contexts == []
    assert fresh_context.todo_turns_since_write == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["append", "restore"])
async def test_pending_request_recovery_keeps_context_and_restore_version_fences(baseline, monkeypatch, conflict):
    from siada.services import session_runtime_state as state

    session = baseline.session()
    store = session.openai_session
    store.migrate_legacy_context_sync(allow_history_only=True)
    context = baseline.context(session)
    context.hook_pending_contexts = ["synthetic pending notice"]
    save_context(context)
    bridge = EffectiveContextSession(store)
    config = bridge.configure_run(RunConfig(model=baseline.model(session, [])))
    data = CallModelData(
        model_data=ModelInputData(input=[], instructions=""), agent=Agent(name="test"), context=context,
    )
    model_data = await config.call_model_input_filter(data)
    bridge.capture_pending_contexts(context.hook_pending_contexts)
    notice = {"role": "system", "content": context.hook_pending_contexts[0]}
    writer = state.write_json

    def fail_state(*args):
        raise OSError("synthetic state failure")

    monkeypatch.setattr(state, "write_json", fail_state)
    with pytest.raises(OSError, match="state failure"):
        await bridge.finalize_request_input(model_data.input + [notice])
    monkeypatch.setattr(state, "write_json", writer)
    pending = copy.deepcopy(bridge._pending_finalization)
    snapshot = store.get_context_snapshot_sync()
    if conflict == "append":
        await store.append_context_items([{"role": "user", "content": "concurrent input"}], message_ids=["concurrent"])
    else:
        store.restore_checkpoint_sync(
            store.get_history_items_sync(), snapshot, expected_version=snapshot["context_version"], before_commit=lambda: None,
        )
    before = store.get_checkpoint_snapshot_sync()
    with pytest.raises(ContextVersionConflict):
        await config.call_model_input_filter(data)
    assert store.get_checkpoint_snapshot_sync() == before
    assert notice not in store.get_history_items_sync()
    assert context.hook_pending_contexts == [notice["content"]]
    assert bridge._pending_finalization == pending


@pytest.mark.asyncio
async def test_empty_hook_tail_recovery_still_commits_runtime_state(baseline, monkeypatch):
    from siada.services import session_runtime_state as state

    session = baseline.session()
    store = session.openai_session
    store.migrate_legacy_context_sync(allow_history_only=True)
    context = baseline.context(session)
    context.todo_turns_since_write = 7
    bridge = EffectiveContextSession(store, admission_id="empty-tail")
    config = bridge.configure_run(RunConfig(model=baseline.model(session, [])))
    data = CallModelData(
        model_data=ModelInputData(input=[], instructions=""), agent=Agent(name="test"), context=context,
    )
    model_data = await config.call_model_input_filter(data)
    writer = state.write_json

    def fail_state(*args):
        raise OSError("synthetic state failure")

    monkeypatch.setattr(state, "write_json", fail_state)
    with pytest.raises(OSError, match="state failure"):
        await bridge.finalize_request_input(model_data.input)
    monkeypatch.setattr(state, "write_json", writer)

    async def fail_filter(data):
        raise RuntimeError("synthetic interruption after recovery")

    config = bridge.configure_run(RunConfig(model=baseline.model(session, []), call_model_input_filter=fail_filter))
    with pytest.raises(RuntimeError, match="interruption after recovery"):
        await config.call_model_input_filter(data)
    saved = load_state(store.session_folder, session.session_id)
    assert saved is not None
    assert saved["request_counters"]["empty-tail:request:0"]["todo_turns_since_write"] == 7
    assert bridge._pending_finalization is None
    assert store.get_history_items_sync() == []


def test_repeated_state_restore_keeps_usage_receipts_and_legal_empty_values(baseline):
    session = baseline.session()
    store = session.openai_session
    context = baseline.context(session)
    snapshot = capture_context(context)
    snapshot["pending_notifications"] = ["already delivered task"]
    context.todos = [TodoItem(content="later task", active_form="Doing later task", status="pending")]
    context.goal = Goal.create("later goal")
    context.todo_turns_since_write = 9
    save_context(context)
    response = SimpleNamespace(usage=baseline.usage(120, 30), response_id="synthetic-response")
    record_response(context, response)
    record_response(context, response)
    current = load_state(store.session_folder, session.session_id)
    current["delivered_notifications"] = [notification_identity("already delivered task")]
    from siada.services.session_storage import write_json

    write_json(store.session_folder / "runtime_state.json", current)
    for version in (current["state_version"] + 1, current["state_version"] + 2):
        with storage_transaction(store.session_folder):
            restored = restore_state(store.session_folder, session.session_id, snapshot)
        apply_state(context, restored)
        assert restored["state_version"] == version
        assert restored["usage_records"] == {"synthetic-response": serialize_usage(response.usage)}
        assert restored["pending_notifications"] == []
        assert context.todos == [] and context.todo_turns_since_write == 0
        assert not (store.session_folder / "goal.json").exists()
    assert snapshot["pending_notifications"] == ["already delivered task"]
    assert snapshot["usage_records"] == {}


def test_response_identity_cannot_silently_change_actual_usage(baseline):
    context = baseline.context(baseline.session())
    record_response(context, SimpleNamespace(usage=baseline.usage(10, 3), response_id="response-id"))
    before = load_state(context.session.openai_session.session_folder, context.session.session_id)
    with pytest.raises(SessionStorageError, match="different usage"):
        record_response(context, SimpleNamespace(usage=baseline.usage(11, 3), response_id="response-id"))
    assert load_state(context.session.openai_session.session_folder, context.session.session_id) == before