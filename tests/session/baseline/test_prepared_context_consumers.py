"""Prepared runtime reads and resume never reconstruct input from UI history."""

import copy
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.services.goal.models import Goal
from siada.services.goal.verifier import build_verifier_input
from siada.services.memory.memory_service import MemoryService
from siada.services.session_management import SessionManager
from siada.services.session_storage import ContextVersionConflict, SessionStorageError
from siada.services import side_question
from siada.session.task_message_state import RealApiMessage
from siada.support.resume_service import ResumeService

from test_effective_context_session import run_bridge


async def prepare(session, items):
    store = session.openai_session
    await store.add_items([{"role": "user", "content": "discarded full history"}])
    await store.migrate_legacy_context(allow_history_only=True)
    await store.replace_context_items(items, expected_version=0)
    session.task_message_state.reset_message_history([{"role": "user", "content": "stale mirror"}])
    session.task_message_state.set_real_messages(RealApiMessage([
        {"role": "user", "content": "stale real mirror"},
    ]))
    return store


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "only summary"}]])
async def test_prepared_readers_trust_empty_or_summary_context(baseline, monkeypatch, items):
    session = baseline.session()
    store = await prepare(session, items)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    assert store.has_prepared_context is True
    assert await store.get_runtime_items() == items
    fork = await build_verifier_input(store, Goal.create("synthetic objective"), baseline.context(session))
    assert fork[:-1] == items
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    assert await memory._fetch_effective_items(store) == items
    runner = AsyncMock(return_value="side answer")
    monkeypatch.setattr(side_question, "_run_async", runner)
    assert side_question.run_side_question(session, "what happened?") == "side answer"
    assert runner.await_args.args[0] == items
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    assert (await store.get_history_items())[0]["content"] == "discarded full history"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["not json", "[]", "{}", "invalidated"])
async def test_prepared_reader_failures_never_fall_back(baseline, monkeypatch, damage):
    session = baseline.session()
    store = await prepare(session, [])
    if damage == "invalidated":
        snapshot = await store.get_context_snapshot()
        snapshot["preparation_invalidated"] = True
        store.context_file.write_text(json.dumps(snapshot), encoding="utf-8")
    else:
        store.context_file.write_text(damage, encoding="utf-8")
    expected_error = ContextVersionConflict if damage == "invalidated" else SessionStorageError
    legacy = AsyncMock(side_effect=AssertionError("History fallback must not run"))
    monkeypatch.setattr(store, "get_effective_messages", legacy)
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    side = AsyncMock()
    monkeypatch.setattr(side_question, "_run_async", side)
    with pytest.raises(expected_error):
        await store.get_runtime_items()
    with pytest.raises(expected_error):
        await build_verifier_input(store, Goal.create("objective"), baseline.context(session))
    with pytest.raises(expected_error):
        await memory._fetch_effective_items(store)
    with pytest.raises(expected_error):
        side_question.run_side_question(session, "question")
    legacy.assert_not_called()
    side.assert_not_called()


@pytest.mark.asyncio
async def test_unprepared_consumers_keep_legacy_reads_and_memory_snapshot_adapter(baseline, monkeypatch):
    from siada.services.memory.memory_update.snapshot_view import _SnapshotSessionView

    session = baseline.session()
    store = session.openai_session
    items = [{"role": "user", "content": "legacy view"}]
    await store.add_items(items)
    assert store.has_prepared_context is False
    assert await store.get_runtime_items() == items
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    view = _SnapshotSessionView("snapshot", None, items)
    assert await memory._fetch_effective_items(view) == items
    assert (await build_verifier_input(store, Goal.create("objective"), baseline.context(session)))[:-1] == items
    session.task_message_state.reset_message_history(items)
    side = AsyncMock(return_value="answer")
    monkeypatch.setattr(side_question, "_run_async", side)
    assert side_question.run_side_question(session, "question") == "answer"
    assert side.await_args.args[0] == items
    assert not store.context_file.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "only summary"}]])
async def test_prepared_resume_preserves_context_and_bypasses_legacy_tracking(baseline, monkeypatch, stream, items):
    source = baseline.session("source")
    store = await prepare(source, items)
    legacy_file = store.session_folder / "api_messages.json"
    legacy_file.write_text("malformed obsolete snapshot", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    resume = ResumeService(source.siada_config.workspace)
    data = resume.session_manager.load_session(source.session_id, store.session_folder)
    assert data.items == await store.get_history_items()
    assert data.context_snapshot["items"] == items
    assert data.api_messages is None and data.last_index == -1 and data.last_signature == ""
    target = baseline.session("target")
    target.task_message_state.reset_message_history([{"role": "user", "content": "old target mirror"}])
    target.task_message_state.set_real_messages(RealApiMessage([{"role": "user", "content": "old target real"}]))
    tracking = MagicMock(side_effect=AssertionError("Prepared resume must not write legacy tracking"))
    monkeypatch.setattr(SessionManager, "update_api_messages_tracking", tracking)
    resume.restore_to_running_session(data, target)
    assert target.session_id == source.session_id
    assert target.openai_session.session_folder == store.session_folder
    assert target.task_message_state.get_messages() == []
    assert target.task_message_state.get_real_messages() == []
    assert await target.openai_session.get_context_items() == items
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    tracking.assert_not_called()
    model = baseline.model(target, [[baseline.text("resumed answer")]])
    await run_bridge(baseline, target, model, stream=stream, input="new turn")
    assert model.requests[0]["input"] == items + [{"role": "user", "content": "new turn"}]
    assert model.requests[0]["history"][0]["content"] == "discarded full history"
    assert legacy_file.read_text() == "malformed obsolete snapshot"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["corrupt", "invalidated", "removed"])
async def test_resume_revalidates_before_mutating_live_session(baseline, damage):
    source = baseline.session("source")
    store = await prepare(source, [])
    resume = ResumeService(source.siada_config.workspace)
    data = resume.session_manager.load_session(source.session_id, store.session_folder)
    if damage == "corrupt":
        store.context_file.write_text("not json", encoding="utf-8")
    elif damage == "invalidated":
        snapshot = await store.get_context_snapshot()
        snapshot["preparation_invalidated"] = True
        store.context_file.write_text(json.dumps(snapshot), encoding="utf-8")
    else:
        store.context_file.unlink()
    target = baseline.session("target")
    original_store = target.openai_session
    target.task_message_state.reset_message_history([{"role": "user", "content": "live mirror"}])
    before = copy.deepcopy(target.task_message_state)
    with pytest.raises(SessionStorageError):
        resume.restore_to_running_session(data, target)
    assert target.session_id == "target"
    assert target.openai_session is original_store
    assert target.task_message_state == before
    if damage != "removed":
        with pytest.raises(SessionStorageError):
            resume.session_manager.load_session(source.session_id, store.session_folder)


@pytest.mark.asyncio
async def test_prepared_resume_rejects_mismatched_identity_before_live_mutation(baseline):
    source = baseline.session("source")
    store = await prepare(source, [])
    resume = ResumeService(source.siada_config.workspace)
    data = resume.session_manager.load_session(source.session_id, store.session_folder)
    data.session_id = "other-session"
    target = baseline.session("target")
    original_store = target.openai_session
    with pytest.raises(SessionStorageError, match="identity"):
        resume.restore_to_running_session(data, target)
    assert target.session_id == "target"
    assert target.openai_session is original_store
    assert not (store.session_folder.parent / "other-session").exists()