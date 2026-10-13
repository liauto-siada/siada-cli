"""Real file checkpoint capture and slash-command restore, without Git effects."""

import asyncio
import copy
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
from siada.services.goal import goal_storage
from siada.services.goal.models import Goal
from siada.services.session_management import SessionManager
from siada.session.task_message_state import RealApiMessage
from siada.support.checkpoint_tracker import CheckPointData, CheckPointTracker
from siada.support.slash_commands import SlashCommands
from siada.support.usage_utils import serialize_usage
from siada.tools.todo.models import TodoItem


def checkpoint(baseline):
    history = [
        {"role": "user", "content": "checkpoint request"},
        {"type": "function_call", "call_id": "edit-1", "name": "edit_file",
         "arguments": '{"command": "create", "path": "synthetic.py"}'},
        {"type": "function_call_output", "call_id": "edit-1", "output": "saved"},
    ]
    return CheckPointData(
        timestamp=datetime(2026, 1, 1), last_commit_hash="synthetic-commit", history=history,
        use_tool_name="edit_file", modified_file_names=["synthetic.py"],
        real_api_message=RealApiMessage(history[:-1], 1, "synthetic-signature").to_dict(),
        usage=serialize_usage(baseline.usage()),
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_checkpoint_json_round_trip_and_missing_optional_fields(baseline, legacy):
    expected = checkpoint(baseline)
    payload = expected.to_dict()
    if legacy:
        payload.pop("usage")
        payload.pop("real_api_message")
        payload.pop("data")
    restored = CheckPointData.from_dict(json.loads(json.dumps(payload)))
    assert restored.history == expected.history
    assert restored.last_commit_hash == expected.last_commit_hash
    assert restored.use_tool_name == "edit_file"
    assert restored.usage == (None if legacy else expected.usage)
    assert restored.real_api_message == (None if legacy else expected.real_api_message)


def test_checkpoint_capture_contains_tool_result_and_actual_usage(baseline):
    session = baseline.session()
    expected = checkpoint(baseline)
    session.task_message_state.reset_message_history(copy.deepcopy(expected.history))
    session.task_message_state.set_real_messages(RealApiMessage.from_dict(expected.real_api_message))
    session.state.usage = baseline.usage()
    tracker = CheckPointTracker(session.siada_config.workspace, session.session_id)
    tracker.git_service = MagicMock()
    tracker.git_service.get_modified_files.return_value = ["synthetic.py"]
    tracker.git_service.create_snapshot.return_value = "synthetic-commit"
    tracker.save_checkpoints(session.session_id, session.task_message_state, session.state.usage)
    files = list(Path(tracker.checkpoint_dir).glob("*.json"))
    assert len(files) == 1
    restored = tracker.get_checkpoint_data_by_file_name(files[0].name)
    assert restored.history == expected.history
    assert restored.history[-1]["output"] == "saved"
    assert restored.real_api_message == expected.real_api_message
    assert restored.usage == expected.usage
    # Saving uses a snapshot, not references into later-mutated task state.
    session.task_message_state.add_message({"role": "user", "content": "later"})
    assert tracker.get_checkpoint_data_by_file_name(files[0].name).history == expected.history


@pytest.mark.asyncio
async def test_real_runner_checkpoint_includes_tool_call_and_result(baseline, monkeypatch):
    from agents import function_tool

    session = baseline.session()
    tracker = CheckPointTracker(session.siada_config.workspace, session.session_id)
    tracker.git_service = MagicMock()
    tracker.git_service.get_modified_files.return_value = ["synthetic.py"]
    tracker.git_service.create_snapshot.return_value = "synthetic-commit"
    session.checkpoint_tracker = tracker
    writes = []
    original_write = tracker._write_checkpoint_and_cleanup_async

    async def observe_write(path, data):
        await original_write(path, data)
        writes.append(path)

    monkeypatch.setattr(tracker, "_write_checkpoint_and_cleanup_async", observe_write)

    @function_tool
    def edit_file(command: str, path: str) -> str:
        """Simulate a file edit without touching the workspace."""
        return "synthetic edit result"

    model = baseline.model(session, [
        [baseline.call("edit-1", "edit_file", {"command": "create", "path": "synthetic.py"})],
        [baseline.text("finished")],
    ])
    await baseline.run(session, model, tools=[edit_file], hooks=SiadaRunHooks())
    # Await the production fire-and-forget checkpoint tasks explicitly.
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()
             and task.get_coro().__qualname__.endswith("observe_write")]
    if tasks:
        await asyncio.gather(*tasks)
    assert len(writes) == 1
    restored = tracker.get_checkpoint_data_by_file_name(writes[0].name)
    assert [item.get("type", item.get("role")) for item in restored.history] == [
        "user", "function_call", "function_call_output",
    ]
    assert restored.history[-1]["output"] == "synthetic edit result"
    assert restored.usage == serialize_usage(baseline.usage())


@pytest.mark.parametrize("failure", [None, "git", "snapshot_io"])
@pytest.mark.parametrize("existing_snapshot", [False, True])
def test_real_file_checkpoint_restore_and_failure_compensation(baseline, monkeypatch, failure, existing_snapshot):
    session = baseline.session()
    store = session.openai_session
    store.add_items_sync([{"role": "user", "content": "live request"}])
    session.state.usage = baseline.usage(400, 50)
    session.task_message_state.set_real_messages(RealApiMessage(
        [{"role": "user", "content": "live effective"}], 0, "live-signature",
    ))
    session.checkpoint_tracker = MagicMock()
    api_file = store.session_folder / "api_messages.json"
    if existing_snapshot:
        api_file.write_text('{"api_messages": [{"role": "user", "content": "live effective"}]}', encoding="utf-8")
    before_history = store.session_file.read_bytes()
    before_snapshot = api_file.read_bytes() if existing_snapshot else None
    before_usage = serialize_usage(session.state.usage)
    before_real = session.task_message_state._real_messages.to_dict()
    git_restore = session.checkpoint_tracker.git_service.restore_project_from_snapshot
    if failure == "git":
        git_restore.side_effect = RuntimeError("synthetic Git failure")
    if failure == "snapshot_io":
        def fail_sync(*args, **kwargs):
            raise OSError("synthetic snapshot write failure")
        monkeypatch.setattr(SessionManager, "sync_api_messages", fail_sync)
    saved = checkpoint(baseline)
    commands = SlashCommands(io=MagicMock())
    ok = commands._manage_session_and_restore(session, saved.last_commit_hash, saved.history, saved)
    if failure:
        assert ok is False
        assert store.session_file.read_bytes() == before_history
        assert serialize_usage(session.state.usage) == before_usage
        assert session.task_message_state._real_messages.to_dict() == before_real
        assert (api_file.read_bytes() if api_file.exists() else None) == before_snapshot
        if failure == "snapshot_io":
            git_restore.assert_not_called()
    else:
        assert ok is True
        git_restore.assert_called_once_with("synthetic-commit")
        assert asyncio.run(store.get_items()) == saved.history
        assert serialize_usage(session.state.usage) == saved.usage
        assert json.loads(api_file.read_text())["api_messages"] == saved.history[:-1]


def test_checkpoint_captures_complete_structured_session_state(baseline):
    session = baseline.session()
    context = baseline.context(session)
    context.goal = Goal.create("checkpoint goal")
    context.todos = [TodoItem(content="Checkpoint task", active_form="Checkpointing task", status="in_progress")]
    goal_storage.save_goal(session.openai_session.session_folder, context.goal)
    context.todo_turns_since_write = 9
    context.hook_pending_contexts = ["checkpoint notification"]
    saved = checkpoint(baseline)
    session.task_message_state.reset_message_history(saved.history)
    tracker = CheckPointTracker(session.siada_config.workspace, session.session_id)
    tracker.git_service = MagicMock()
    tracker.git_service.get_modified_files.return_value = ["synthetic.py"]
    tracker.git_service.create_snapshot.return_value = "synthetic-commit"
    session.checkpoint_tracker = tracker
    context.save_checkpoints()
    path = next(Path(tracker.checkpoint_dir).glob("*.json"))
    restored = tracker.get_checkpoint_data_by_file_name(path.name)
    assert restored.data is not None
    assert restored.data["goal"] == context.goal.model_dump()
    assert restored.data["todos"] == [todo.model_dump() for todo in context.todos]
    assert restored.data["todo_turns_since_write"] == 9
    assert restored.data["pending_notifications"] == ["checkpoint notification"]