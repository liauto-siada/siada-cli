"""Offline regression coverage for independent conversation forks."""

import json
import threading
from unittest.mock import MagicMock

import pytest
from agents import Agent, RunConfig, Runner

from siada.services.effective_context_session import EffectiveContextSession
from siada.services.goal.models import Goal
from siada.services.goal.goal_storage import save_goal
from siada.services.file_session import FileSession
from siada.services.session_management import SessionManager
from siada.services.session_runtime_state import empty_state
from siada.services.session_storage import SessionStorageError, write_json
from siada.support.resume_service import ResumeService
from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.entrypoint.interaction.controller import Controller
from siada.services.session_signature import compute_last_item_signature


def manager_for(session):
    manager = SessionManager(session.siada_config.workspace)
    manager.sessions_dir = session.openai_session.sessions_dir
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("prepared", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_fork_preserves_views_and_continues_independently(baseline, prepared, stream):
    source = baseline.session()
    store = source.openai_session
    await store.add_items([{"role": "user", "content": "original question"}])
    summary = [{"role": "user", "content": "compacted context"}]
    if prepared:
        await store.migrate_legacy_context(allow_history_only=True)
        await store.replace_context_items(summary, expected_version=0)
    else:
        SessionManager.sync_api_messages(
            store.session_folder, source.session_id, summary, 41,
            last_index=0, last_signature=compute_last_item_signature(await store.get_history_items()),
        )
    metadata = json.loads(store.metadata_file.read_bytes())
    metadata.update(active_owner="lark", session_source="lark", title="Source title")
    write_json(store.metadata_file, metadata)
    state = empty_state(source.session_id)
    state["todos"] = [{"content": "Continue work", "active_form": "Continuing work", "status": "pending"}]
    write_json(store.session_folder / "runtime_state.json", state)
    assert save_goal(store.session_folder, Goal(objective="Continue the source goal"))
    write_json(store.session_folder / "inject_info.json", {"source_session_id": "other", "content": "IPC"})
    before = {p.name: p.read_bytes() for p in store.session_folder.glob("*.json")}

    manager = manager_for(source)
    data = manager.fork_session(source.session_id)
    assert data.session_id != source.session_id
    assert data.metadata["parent_session_id"] == source.session_id
    assert data.metadata["title"] == "Source title"
    assert "active_owner" not in data.metadata
    assert "session_source" not in data.metadata
    assert not (data.session_path / "inject_info.json").exists()
    assert data.runtime_state["session_id"] == data.session_id
    assert data.items == await store.get_history_items()
    assert data.context_snapshot["items"] == summary
    fork = baseline.session(session_id="placeholder")
    ResumeService(source.siada_config.workspace).restore_to_running_session(data, fork)
    assert fork.state.pending_todos[0].content == "Continue work"
    assert fork.state.pending_goal.objective == "Continue the source goal"
    assert fork.openai_session.session_id == data.session_id
    assert fork.openai_session.native_item_count == 1
    model = baseline.model(fork, [[baseline.text("fork reply")]])
    bridge = EffectiveContextSession(fork.openai_session)
    agent = Agent(name="fork-agent", instructions="# Context", model=model)
    config = bridge.configure_run(RunConfig(tracing_disabled=True), agent=agent)
    kwargs = dict(input="new direction", session=bridge, context=baseline.context(fork), run_config=config)
    if stream:
        result = Runner.run_streamed(agent, **kwargs)
        async for _ in result.stream_events():
            pass
    else:
        await Runner.run(agent, **kwargs)
    assert summary[0] in model.requests[0]["input"]
    assert "new direction" in str(model.requests[0]["input"])
    assert before == {p.name: p.read_bytes() for p in store.session_folder.glob("*.json")}
    reloaded = manager.load_session(data.session_id)
    assert "fork reply" in str(reloaded.items)


@pytest.mark.asyncio
async def test_fork_keeps_explicit_empty_context_and_receipts(baseline):
    source = baseline.session()
    store = source.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    item = {"role": "user", "content": "old"}
    await store.append_context_items([item], message_ids=["admitted-turn"])
    await store.replace_context_items([], expected_version=1)
    data = manager_for(source).fork_session(source.session_id)
    fork_store = FileSession.from_file(data.session_path / "api_history.json")
    assert await fork_store.get_context_items() == []
    assert await fork_store.get_history_items() == [item]
    assert await fork_store.append_context_items([item], message_ids=["admitted-turn"]) == []
    assert await fork_store.append_context_items([item], message_ids=["new-turn"]) == [item]
    assert await store.get_context_items() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["write", "invalid_context", "workspace", "invalid_goal", "invalid_legacy"])
async def test_failed_fork_leaves_no_discoverable_session(baseline, monkeypatch, failure):
    source = baseline.session()
    store = source.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    manager = manager_for(source)
    if failure == "write":
        def fail(*args):
            raise OSError("synthetic write failure")
        monkeypatch.setattr("siada.services.session_management.write_json", fail)
    elif failure == "invalid_context":
        context = json.loads(store.context_file.read_bytes())
        context["session_id"] = "wrong"
        write_json(store.context_file, context)
    elif failure == "workspace":
        metadata = json.loads(store.metadata_file.read_bytes())
        metadata["project_root"] = str(baseline.workspace() / "different")
        write_json(store.metadata_file, metadata)
    elif failure == "invalid_goal":
        write_json(store.session_folder / "goal.json", {"broken": True})
    else:
        store.context_file.unlink()
        await store.add_items([{"role": "user", "content": "history"}])
        SessionManager.sync_api_messages(
            store.session_folder, source.session_id,
            [{"role": "user", "content": "summary without a boundary"}],
        )
    before = {p.name: p.read_bytes() for p in store.session_folder.glob("*.json")}
    with pytest.raises((OSError, ValueError, SessionStorageError)):
        manager.fork_session(source.session_id)
    assert [s.session_id for s in manager.list_sessions()] == [source.session_id]
    assert before == {p.name: p.read_bytes() for p in store.session_folder.glob("*.json")}
    assert not list(manager.sessions_dir.parent.glob(".session-fork-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_command_and_controller_switch_all_session_bindings(baseline, explicit):
    source = baseline.session()
    await source.openai_session.add_items([{"role": "user", "content": "source"}])
    commands = SlashCommands.__new__(SlashCommands)
    commands.io = MagicMock()
    commands._send_history_to_ui = MagicMock()
    commands._push_resumed_goal_state_to_ui = MagicMock()
    event = commands.cmd_fork(source, source.session_id if explicit else "")
    assert isinstance(event, SwitchEvent)
    assert source.session_id != event.kwargs["fork_data"].session_id

    controller = Controller.__new__(Controller)
    controller.config = source.siada_config
    controller.config.io = commands.io
    controller.config.completer = MagicMock()
    controller.session = source
    controller.slash_commands = commands
    controller.ui = MagicMock()
    controller.show_announcements = MagicMock()
    controller._bg_wakeup_event = threading.Event()
    controller._bg_wakeup_event.set()
    controller._unregister_background_wakeups = MagicMock()
    controller._register_background_wakeup = MagicMock()
    controller._release_cli_ownership = MagicMock()
    if controller.config.checkpointing_config:
        controller.config.checkpointing_config.enable = False
    controller._handle_switch_event(event)
    fresh = controller.session
    assert fresh is not source
    assert fresh.session_id == event.kwargs["fork_data"].session_id
    assert controller.config.completer.session_id == fresh.session_id
    assert not controller._bg_wakeup_event.is_set()
    controller._register_background_wakeup.assert_called_once_with(fresh)
    controller.ui.reset_history_state.assert_called_once()
    controller.show_announcements.assert_called_once()
    commands._send_history_to_ui.assert_called_once_with(event.kwargs["fork_data"].items)
    commands._push_resumed_goal_state_to_ui.assert_called_once_with(fresh)


@pytest.mark.asyncio
async def test_headless_fork_does_not_create_or_switch_session():
    from siada.acp_server.runtime import SiadaTurnRunner

    runner = SiadaTurnRunner.__new__(SiadaTurnRunner)
    # No runtime session or dispatcher: the unsupported entry must return
    # before touching either, even if a client types an unadvertised command.
    updates = [item async for item in runner.run_slash_command("session", "/fork source")]
    assert len(updates) == 1
    assert "terminal CLI" in str(updates)