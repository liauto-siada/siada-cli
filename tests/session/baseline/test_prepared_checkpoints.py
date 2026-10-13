"""Persistence-aware checkpoint capture and dual-view restore in explicit runs."""

import copy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agents import function_tool

from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
from siada.services.effective_context_session import EffectiveContextSession
from siada.services import session_storage
from siada.services.session_storage import ContextVersionConflict, SessionStorageError
from siada.session.task_message_state import RealApiMessage
from siada.support.checkpoint_tracker import CheckPointTracker
from siada.support.slash_commands import SlashCommands
from siada.support.usage_utils import serialize_usage

from test_checkpoints import checkpoint
from test_effective_context_session import run_bridge


def tracker_for(session):
    tracker = CheckPointTracker(session.siada_config.workspace, session.session_id)
    tracker.git_service = MagicMock()
    tracker.git_service.get_modified_files.return_value = ["synthetic.py"]
    tracker.git_service.create_snapshot.return_value = "synthetic-commit"
    session.checkpoint_tracker = tracker
    return tracker


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("parallel", [False, True])
async def test_checkpoint_captures_durable_batch_after_tool_end(baseline, monkeypatch, stream, parallel):
    session = baseline.session()
    store = session.openai_session
    old_history = [{"role": "user", "content": "full discarded history"}]
    await store.add_items(old_history)
    await store.migrate_legacy_context(allow_history_only=True)
    await store.replace_context_items([], expected_version=0)
    session.task_message_state.reset_message_history([{"role": "user", "content": "stale capture mirror"}])
    tracker = tracker_for(session)
    observed = []
    save = tracker.save_checkpoints

    def capture(*args, **kwargs):
        snapshot = kwargs["file_snapshot"]
        assert snapshot == store.get_checkpoint_snapshot_sync()
        assert args[1] is None
        save(*args, **kwargs)
        observed.append(copy.deepcopy(snapshot))

    monkeypatch.setattr(tracker, "save_checkpoints", capture)

    @function_tool
    def edit_file(command: str, path: str) -> str:
        """Return a synthetic result without modifying the workspace."""
        assert not any(item.get("type") == "function_call_output" for item in store.get_history_items_sync())
        return f"saved {path}"

    calls = [baseline.call("edit-1", "edit_file", {"command": "create", "path": "synthetic.py"})]
    if parallel:
        calls.append(baseline.call("edit-2", "edit_file", {"command": "create", "path": "second.py"}))
    model = baseline.model(session, [calls, [baseline.text("finished")]])
    await run_bridge(baseline, session, model, stream=stream, tools=[edit_file], hooks=SiadaRunHooks())
    assert len(observed) == len(calls)
    captured = observed[0]
    assert captured["history_items"][0] == old_history[0]
    assert not any(item.get("content") == "full discarded history" for item in captured["context_snapshot"]["items"])
    outputs = [item for item in captured["context_snapshot"]["items"] if item.get("type") == "function_call_output"]
    assert {item["call_id"] for item in outputs} == {call.call_id for call in calls}
    assert session.task_message_state.get_messages() == [{"role": "user", "content": "stale capture mirror"}]
    files = list(Path(tracker.checkpoint_dir).glob("*.json"))
    assert len(files) == len(calls)
    saved = tracker.get_checkpoint_data_by_file_name(files[0].name)
    assert saved.history == captured["history_items"]
    assert saved.context_snapshot == captured["context_snapshot"]
    assert saved.real_api_message is None
    assert saved.usage == serialize_usage(session.state.usage)


def prepared_checkpoint(baseline, items):
    session = baseline.session()
    store = session.openai_session
    saved = checkpoint(baseline)
    from siada.services.session_runtime_state import capture_context

    saved.data = capture_context(baseline.context(session))
    saved.data["usage"] = saved.usage
    store.add_items_sync(saved.history)
    store.migrate_legacy_context_sync(allow_history_only=True)
    store.replace_context_items_sync(items, expected_version=0)
    saved.context_snapshot = store.get_context_snapshot_sync()
    store.append_context_items_sync([{"role": "user", "content": "abandoned later turn"}], message_ids=["later-turn"])
    session.task_message_state.reset_message_history([{"role": "user", "content": "live mirror"}])
    session.task_message_state.set_real_messages(RealApiMessage([{"role": "user", "content": "live real"}]))
    session.state.usage = baseline.usage(400, 50)
    tracker_for(session)
    return session, store, saved


@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "summary only"}]])
@pytest.mark.parametrize("undo", [False, True])
def test_prepared_restore_keeps_empty_context_and_monotonic_receipts(baseline, items, undo):
    session, store, saved = prepared_checkpoint(baseline, items)
    version = store.get_context_snapshot_sync()["context_version"]
    commands = SlashCommands(io=MagicMock())
    history = commands._process_checkpoint_history(saved, "undo" if undo else "restore")
    before_notifications = []
    store.on_items_added = before_notifications.append
    assert commands._manage_session_and_restore(session, "synthetic-commit", history, saved) is True, commands.io.print_error.call_args
    assert store.get_history_items_sync() == history
    snapshot = store.get_context_snapshot_sync()
    extra = history[len(saved.history):]
    assert snapshot["items"] == items + extra
    assert snapshot["context_version"] == version + 1
    assert "later-turn" in snapshot["message_receipts"]
    assert store.append_context_items_sync(
        [{"role": "user", "content": "abandoned later turn"}], message_ids=["later-turn"],
    ) == []
    assert store.get_context_snapshot_sync()["items"] == items + extra
    assert session.task_message_state.get_messages() == []
    assert session.task_message_state.get_real_messages() == []
    assert serialize_usage(session.state.usage) == saved.usage
    assert not (store.session_folder / "api_messages.json").exists()
    assert before_notifications == []
    session.checkpoint_tracker.git_service.restore_project_from_snapshot.assert_called_once_with("synthetic-commit")


@pytest.mark.parametrize("failure", ["git", "storage", "legacy", "corrupt", "wrong_session"])
def test_prepared_restore_failure_preserves_files_and_live_state(baseline, monkeypatch, failure):
    session, store, saved = prepared_checkpoint(baseline, [])
    git = session.checkpoint_tracker.git_service.restore_project_from_snapshot
    if failure == "git":
        git.side_effect = [RuntimeError("synthetic Git failure"), None]
    elif failure == "storage":
        monkeypatch.setattr(store, "_update_metadata", MagicMock(side_effect=OSError("synthetic metadata failure")))
    elif failure == "legacy":
        saved.context_snapshot = None
    elif failure == "corrupt":
        saved.context_snapshot = {}
    else:
        saved.context_snapshot["session_id"] = "other-session"
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    before_state = copy.deepcopy(session.task_message_state)
    before_usage = serialize_usage(session.state.usage)
    commands = SlashCommands(io=MagicMock())
    assert commands._manage_session_and_restore(session, saved.last_commit_hash, saved.history, saved) is False
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    assert session.task_message_state == before_state
    assert serialize_usage(session.state.usage) == before_usage
    if failure != "git":
        git.assert_not_called()
        session.checkpoint_tracker.git_service.create_snapshot.assert_not_called()
    else:
        assert git.call_count == 2


def test_prepared_restore_version_conflict_precedes_project_restore(baseline):
    session, store, saved = prepared_checkpoint(baseline, [])
    old_version = store.get_context_snapshot_sync()["context_version"]
    store.replace_context_items_sync([{"role": "user", "content": "concurrent context"}], expected_version=old_version)
    callback = MagicMock()
    with pytest.raises(ContextVersionConflict):
        store.restore_checkpoint_sync(saved.history, saved.context_snapshot,
                                      expected_version=old_version, before_commit=callback)
    callback.assert_not_called()
    assert store.get_context_snapshot_sync()["items"] == [{"role": "user", "content": "concurrent context"}]


def test_undo_notice_resolves_matching_call_in_parallel_batch(baseline):
    saved = checkpoint(baseline)
    saved.history.insert(2, {"type": "function_call", "call_id": "run-2", "name": "run_cmd", "arguments": "{}"})
    saved.history.insert(3, {"type": "function_call_output", "call_id": "run-2", "output": "done"})
    commands = SlashCommands(io=MagicMock())
    restored = commands._process_checkpoint_history(saved, "undo")
    assert restored[-1]["content"] == "The user reverted the changes made by the edit_file tool"


@pytest.mark.asyncio
async def test_checkpoint_capture_failure_does_not_resurrect_mirrors(baseline):
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    store.history_file.write_text("not json", encoding="utf-8")
    with pytest.raises(SessionStorageError):
        store.get_checkpoint_snapshot_sync()


@pytest.mark.parametrize("failure", ["partial_git", "commit_flush", "post_commit_flush"])
def test_prepared_restore_compensates_project_after_partial_failure(baseline, monkeypatch, failure):
    session, store, saved = prepared_checkpoint(baseline, [])
    project_file = baseline.root / "synthetic-project.txt"
    project_file.write_text("live uncommitted work", encoding="utf-8")
    git_service = session.checkpoint_tracker.git_service
    git_service.create_snapshot.return_value = "rollback-commit"
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    state = copy.deepcopy(session.task_message_state)
    usage = serialize_usage(session.state.usage)
    sync_directory = session_storage.sync_directory
    fail_flush = 0

    def restore(commit):
        nonlocal fail_flush
        if commit == "rollback-commit":
            project_file.write_text("live uncommitted work", encoding="utf-8")
        else:
            project_file.write_text("restored checkpoint", encoding="utf-8")
            if failure == "partial_git":
                raise RuntimeError("synthetic partial Git restore")
            fail_flush = 2 if failure == "post_commit_flush" else 1

    def flush(folder):
        nonlocal fail_flush
        if fail_flush:
            fail_flush -= 1
            if not fail_flush:
                raise OSError("synthetic commit flush failure")
        sync_directory(folder)

    git_service.restore_project_from_snapshot.side_effect = restore
    monkeypatch.setattr(session_storage, "sync_directory", flush)
    commands = SlashCommands(io=MagicMock())
    assert commands._manage_session_and_restore(session, saved.last_commit_hash, saved.history, saved) is False
    assert project_file.read_text() == "live uncommitted work"
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    assert session.task_message_state == state
    assert serialize_usage(session.state.usage) == usage
    assert [call.args[0] for call in git_service.restore_project_from_snapshot.call_args_list] == [
        "synthetic-commit", "rollback-commit",
    ]


def test_prepared_restore_reports_project_compensation_failure(baseline):
    session, store, saved = prepared_checkpoint(baseline, [])
    git = session.checkpoint_tracker.git_service
    git.restore_project_from_snapshot.side_effect = [
        RuntimeError("synthetic partial restore"), RuntimeError("synthetic rollback failure"),
    ]
    commands = SlashCommands(io=MagicMock())
    assert commands._manage_session_and_restore(session, saved.last_commit_hash, saved.history, saved) is False
    assert "project rollback failed" in commands.io.print_error.call_args.args[0]
    assert git.restore_project_from_snapshot.call_count == 2


@pytest.mark.asyncio
async def test_prepared_restore_fences_existing_bridge_but_allows_fresh_run(baseline):
    session, store, saved = prepared_checkpoint(baseline, [])
    bridge = EffectiveContextSession(store)
    await bridge.get_items()
    assert SlashCommands(io=MagicMock())._manage_session_and_restore(
        session, saved.last_commit_hash, saved.history, saved,
    ) is True
    before = store.get_checkpoint_snapshot_sync()
    with pytest.raises(ContextVersionConflict, match="restored"):
        await bridge.get_items()
    with pytest.raises(ContextVersionConflict, match="restored"):
        await bridge.add_items([{"type": "function_call_output", "call_id": "late", "output": "late"}])
    with pytest.raises(ContextVersionConflict, match="restored"):
        store.append_context_items_sync(
            [{"role": "assistant", "content": "late"}], message_ids=["late"],
            expected_restore_generation=0,
        )
    assert store.get_checkpoint_snapshot_sync() == before
    assert await EffectiveContextSession(store).get_items() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_prepared_restore_during_model_response_rejects_late_sdk_save(baseline, monkeypatch, stream):
    session, store, saved = prepared_checkpoint(baseline, [])
    model = baseline.model(session, [[baseline.text("late abandoned response")]])
    next_response = model._next
    restored = []

    async def response(*args):
        result = await next_response(*args)
        assert SlashCommands(io=MagicMock())._manage_session_and_restore(
            session, saved.last_commit_hash, saved.history, saved,
        ) is True
        restored.append(store.get_checkpoint_snapshot_sync())
        return result

    monkeypatch.setattr(model, "_next", response)
    with pytest.raises(ContextVersionConflict, match="restored"):
        await run_bridge(baseline, session, model, stream=stream)
    assert len(model.requests) == 1
    assert store.get_checkpoint_snapshot_sync() == restored[0]


@pytest.mark.parametrize("generation", [True, -1, "0", None])
def test_prepared_context_rejects_invalid_restore_generation(baseline, generation):
    session, store, saved = prepared_checkpoint(baseline, [])
    saved.context_snapshot["restore_generation"] = generation
    callback = MagicMock()
    with pytest.raises(SessionStorageError):
        store.restore_checkpoint_sync(
            saved.history, saved.context_snapshot,
            expected_version=store.get_context_snapshot_sync()["context_version"], before_commit=callback,
        )
    callback.assert_not_called()


def test_prepared_repeated_restore_advances_live_generation(baseline):
    session, store, saved = prepared_checkpoint(baseline, [])
    commands = SlashCommands(io=MagicMock())
    for generation in (1, 2):
        assert commands._manage_session_and_restore(session, saved.last_commit_hash, saved.history, saved) is True
        assert store.get_context_snapshot_sync()["restore_generation"] == generation