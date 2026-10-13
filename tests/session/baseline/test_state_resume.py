"""Session-state round trips and executable known gaps in the current code."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from siada.foundation.code_agent_context import RuntimeSource
from siada.models.agent_lifecycle import AgentMessage, MessageEventType
from siada.services.goal import goal_storage
from siada.services.goal.models import Goal
from siada.services.siada_runner import SiadaRunner
from siada.session.message_state_tracker import MessageState, MessageStateTracker
from siada.session.ownership import OwnershipError, SessionOwner, SessionOwnershipManager
from siada.support.resume_service import ResumeService
from siada.support.usage_utils import deserialize_usage, serialize_usage
from siada.tools.agent import subagent_async, subagent_persistence
from siada.tools.todo.models import TodoItem
from siada.tools.todo.todo_write_tool import todo_write, todo_write_impl


def todos():
    return [
        TodoItem(content="Inspect module", active_form="Inspecting module", status="in_progress"),
        TodoItem(content="Add tests", active_form="Adding tests", status="pending"),
    ]


def load_and_restore(source, target):
    resume = ResumeService(source.siada_config.workspace)
    data = resume.session_manager.load_session(source.session_id, source.openai_session.session_folder)
    resume.restore_to_running_session(data, target)
    return data


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_todos_all_fields_and_order_survive_runner_and_resume(baseline, stream):
    original = baseline.session("original")
    expected = todos()
    model = baseline.model(original, [
        [baseline.call("todo-1", "todo_write", {"todos": [t.model_dump() for t in expected]})],
        [baseline.text("tracked")],
    ])
    _, context, _ = await baseline.run(original, model, tools=[todo_write], stream=stream)
    assert context.todos == expected
    fresh = baseline.session("fresh")
    data = load_and_restore(original, fresh)
    assert fresh.state.pending_todos == expected
    resumed_context = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(resumed_context, fresh)
    assert resumed_context.todos == expected
    assert fresh.state.pending_todos is None
    assert fresh.task_message_state.get_messages() == data.items
    assert await fresh.openai_session.get_all_items() == data.items


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", "paused", "blocked", "complete"])
async def test_goal_all_fields_and_audit_history_survive_resume(baseline, status):
    original = baseline.session("original")
    goal = Goal(
        objective="Ship synthetic feature", status=status, consecutive_failures=3,
        consecutive_system_errors=1, turns=5, reminder_injected=True,
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-02T00:00:00Z",
    )
    goal_storage.save_goal(original.openai_session.session_folder, goal)
    goal_storage.append_goal_history(original.openai_session.session_folder, goal)
    fresh = baseline.session("fresh")
    fresh.state.pending_goal = Goal.create("stale pending goal")
    load_and_restore(original, fresh)
    assert fresh.state.pending_goal.model_dump() == goal.model_dump()
    context = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert context.goal.model_dump() == goal.model_dump()
    assert fresh.state.pending_goal is None
    assert goal_storage.load_goal_history(original.openai_session.session_folder)[0]["objective"] == goal.objective


@pytest.mark.asyncio
async def test_resume_stages_unfinished_tree_and_preserves_finished_results(baseline):
    original = baseline.session("original")
    root = original.siada_config.workspace
    for agent_id, parent_id, depth in [("parent", None, 1), ("child", "parent", 2), ("done", None, 1)]:
        subagent_persistence.record_start(
            root, original.session_id, agent_id=agent_id, parent_id=parent_id,
            depth=depth, title=f"Task {agent_id}", instruction=f"Inspect {agent_id}",
        )
    subagent_persistence.append_log(root, original.session_id, "done", "message", "saved result")
    subagent_persistence.record_finish(root, original.session_id, "done", "completed", "saved result")
    before = (original.openai_session.session_folder / "subagents" / "index.json").read_bytes()
    fresh = baseline.session("fresh")
    load_and_restore(original, fresh)
    note = fresh.state.pending_subagent_resume_note
    assert "id=parent depth=1 parent=main-agent" in note
    assert "id=child depth=2 parent=parent" in note
    assert "id=done" not in note
    context = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert context.root_session_id == original.session_id
    assert context.hook_pending_contexts == [note]
    assert fresh.state.pending_subagent_resume_note is None
    assert (original.openai_session.session_folder / "subagents" / "index.json").read_bytes() == before
    assert "saved result" in subagent_persistence.read_log_tail(root, original.session_id, "done")


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_background_completion_routes_only_to_parent_and_wakes_once(baseline, failed):
    parent = baseline.session("parent")
    other = baseline.session("other")
    parent_context = baseline.context(parent)
    other_context = baseline.context(other)
    gate = asyncio.Event()
    wakeups = []
    subagent_async.register_session_wakeup(parent.session_id, lambda: wakeups.append("parent"))
    subagent_async.register_session_wakeup(other.session_id, lambda: wakeups.append("other"))

    async def finish():
        await gate.wait()
        if failed:
            raise RuntimeError("synthetic child failure")
        return "synthetic child result"

    subagent_async.register_background_subtask(parent_context, finish)
    try:
        gate.set()
        assert await subagent_async.wait_for_session_background_subtasks(parent.session_id, timeout=1)
        await asyncio.sleep(0)
        assert len(parent_context.hook_pending_contexts) == 1
        assert ("failed" if failed else "completed") in parent_context.hook_pending_contexts[0]
        assert other_context.hook_pending_contexts == []
        assert wakeups == ["parent"]
    finally:
        await subagent_async.shutdown_session_background_subtasks(parent.session_id, timeout=1)
        subagent_async.unregister_session_wakeup(parent.session_id)
        subagent_async.unregister_session_wakeup(other.session_id)


@pytest.mark.asyncio
async def test_metadata_source_and_ownership_survive_message_writes(baseline):
    session = baseline.session()
    store = session.openai_session
    SessionOwnershipManager.set_session_source(store.session_folder, SessionOwner.LARK)
    metadata = store._read_metadata()
    metadata.update({"title": "Synthetic title", "agent_name": "baseline-agent", "custom": "retained"})
    store._write_metadata(metadata)
    SessionOwnershipManager.acquire_ownership(store.session_folder, SessionOwner.CLI)
    with pytest.raises(OwnershipError):
        SessionOwnershipManager.acquire_ownership(store.session_folder, SessionOwner.LARK)
    await store.add_items([
        {"role": "user", "content": "<system-reminder>hidden</system-reminder>"},
        {"role": "user", "content": "Human request"},
    ])
    context = baseline.context(session)
    await SiadaRunner._prepare_context_for_run(context, session, RuntimeSource.CLI)
    restored = store._read_metadata()
    assert restored["title"] == "Synthetic title"
    assert restored["agent_name"] == "baseline-agent"
    assert restored["custom"] == "retained"
    assert restored["first_user_message"] == "Human request"
    assert restored["session_source"] == "lark"
    assert restored["active_owner"] == "cli"
    assert context.runtime_source == "cli" and context.im_mode is True
    SessionOwnershipManager.release_ownership(store.session_folder, SessionOwner.LARK)
    assert SessionOwnershipManager.get_active_owner(store.session_folder) == "cli"
    SessionOwnershipManager.release_ownership(store.session_folder, SessionOwner.CLI)
    assert SessionOwnershipManager.get_active_owner(store.session_folder) is None


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_message_identity_streaming_and_terminal_events(terminal):
    tracker = MessageStateTracker(session_id="synthetic-session", run_id="synthetic-run")
    message = AgentMessage(id="synthetic-message", role="assistant")
    tracked = tracker.create_message(message)
    assert tracked.state == MessageState.CREATING
    tracker.add_message_part(message.id, "first ")
    tracker.add_message_part(message.id, "second")
    assert tracked.state == MessageState.STREAMING
    assert tracked.part_count == 2
    assert tracked.total_content_length == len("first second")
    if terminal == "completed":
        tracker.complete_message(message.id)
        assert message.is_complete
        assert tracked.events[-1].type == MessageEventType.MESSAGE_COMPLETED
    else:
        tracker.fail_message(message.id, "synthetic error")
        assert tracked.error == "synthetic error"
        assert tracked.events[-1].type == MessageEventType.ERROR
    assert tracked.is_terminal and not tracked.is_active
    assert tracker.get_message(message.id) is tracked
    assert message.content == "first second"
    assert all(event.run_id == "synthetic-run" for event in tracked.events)


def test_usage_round_trip_preserves_all_supported_details(baseline):
    expected = serialize_usage(baseline.usage())
    assert serialize_usage(deserialize_usage(json.loads(json.dumps(expected)))) == expected
    assert expected["input_tokens_details"] == {"cached_tokens": 20, "cache_write_tokens": 10}
    assert expected["output_tokens_details"] == {"reasoning_tokens": 7}


@pytest.mark.parametrize("payload", [None, {}, {"total_tokens": 5}, {"input_tokens_details": None}])
def test_usage_legacy_missing_and_null_fields(payload):
    restored = deserialize_usage(payload)
    if not payload:
        assert restored is None
    else:
        assert restored is not None
        assert restored.requests == 0
        assert restored.total_tokens == payload.get("total_tokens", 0)
        assert restored.input_tokens_details.cached_tokens == 0
        assert restored.input_tokens_details.cache_write_tokens == 0
        assert restored.output_tokens_details.reasoning_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("separate_by", ["agent", "workspace"])
async def test_different_cache_dimensions_are_isolated_and_same_session_reuses_context(baseline, monkeypatch, separate_by):
    first = baseline.session("first")
    workspace = baseline.workspace("other-workspace") if separate_by == "workspace" else None
    second = baseline.session("second", workspace)
    first_agent = SimpleNamespace(name="first-agent")
    second_agent = SimpleNamespace(name="other-agent" if separate_by == "agent" else "first-agent")
    built = []

    async def build(agent, workspace, session):
        built.append((agent.name, workspace))
        return baseline.context(session)

    monkeypatch.setattr(SiadaRunner, "_build_agent_context", build)
    first_context = await SiadaRunner.get_context(first_agent, first, first.siada_config.workspace)
    second_context = await SiadaRunner.get_context(second_agent, second, second.siada_config.workspace)
    assert first_context is not second_context
    assert await SiadaRunner.get_context(first_agent, first, first.siada_config.workspace) is first_context
    assert len(built) == 2


@pytest.mark.asyncio
async def test_per_run_binding_and_pending_skill_names_are_consumed_once(baseline):
    session = baseline.session()
    context = baseline.context(session)
    session.state.pending_skill_names = {"synthetic-skill"}
    await SiadaRunner._prepare_context_for_run(context, session, RuntimeSource.CLI)
    assert context.session is session
    assert context.root_session_id == session.session_id
    assert context.activated_skill_names == {"synthetic-skill"}
    assert session.state.pending_skill_names == set()
    await SiadaRunner._prepare_context_for_run(context, session, RuntimeSource.CLI)
    assert context.activated_skill_names == set()


@pytest.mark.asyncio
async def test_same_workspace_same_agent_sessions_are_isolated(baseline, monkeypatch):
    first = baseline.session("first")
    second = baseline.session("second")

    async def build(agent, workspace, session):
        return baseline.context(session)

    monkeypatch.setattr(SiadaRunner, "_build_agent_context", build)
    agent = SimpleNamespace(name="shared-agent")
    first_context = await SiadaRunner.get_context(agent, first, first.siada_config.workspace)
    await SiadaRunner._prepare_context_for_run(first_context, first)
    first_context.todos = todos()
    first_context.goal = Goal.create("first goal")
    first_context.todo_turns_since_write = 8
    first_context.hook_pending_contexts = ["first pending notification"]
    second_context = await SiadaRunner.get_context(agent, second, second.siada_config.workspace)
    await SiadaRunner._prepare_context_for_run(second_context, second)
    assert second_context is not first_context
    assert second_context.todos == [] and second_context.goal is None
    assert second_context.hook_pending_contexts == []
    assert second_context.todo_turns_since_write == 0
    assert first_context.session is first


@pytest.mark.asyncio
async def test_cache_lookups_and_background_drain_are_session_owned(baseline, monkeypatch):
    from siada.entrypoint.interaction.turn_policy import TurnPolicy

    first, second = baseline.session("first"), baseline.session("second")
    monkeypatch.setattr(SiadaRunner, "_build_agent_context", lambda a, w, s: asyncio.sleep(0, result=baseline.context(s)))
    agent = SimpleNamespace(name="shared-agent")
    ctx1 = await SiadaRunner.get_context(agent, first, first.siada_config.workspace)
    ctx2 = await SiadaRunner.get_context(agent, second, second.siada_config.workspace)
    ctx1.hook_pending_contexts = ["first notice"]
    ctx2.hook_pending_contexts = ["second notice"]
    assert SiadaRunner.find_session_context(first) is ctx1
    assert SiadaRunner.find_session_context(second) is ctx2
    assert TurnPolicy._drain_background_subtask_notes(second) == ["second notice"]
    assert ctx1.hook_pending_contexts == ["first notice"]
    # An in-place resume invalidates the old cache binding even in one workspace.
    first.session_id = "resumed"
    assert SiadaRunner.find_session_context(first) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", ["no_todo_call", "explicit_empty"])
async def test_empty_resume_clears_previous_todos(baseline, empty):
    original = baseline.session("original")
    if empty == "explicit_empty":
        original.openai_session.add_items_sync([
            baseline.call("empty", "todo_write", {"todos": []}).model_dump(exclude_none=True),
        ])
    fresh = baseline.session("fresh")
    fresh.state.pending_todos = todos()
    context = baseline.context(fresh)
    context.todos = todos()
    load_and_restore(original, fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert context.todos == []


@pytest.mark.asyncio
async def test_all_completed_todos_remain_cleared_after_resume(baseline):
    original = baseline.session("original")
    completed = [todo.model_copy(update={"status": "completed"}) for todo in todos()]
    model = baseline.model(original, [
        [baseline.call("done", "todo_write", {"todos": [todo.model_dump() for todo in completed]})],
        [baseline.text("done")],
    ])
    _, context, _ = await baseline.run(original, model, tools=[todo_write])
    assert context.todos == []
    fresh = baseline.session("fresh")
    load_and_restore(original, fresh)
    resumed = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(resumed, fresh)
    assert resumed.todos == []


@pytest.mark.asyncio
async def test_goalless_resume_clears_cached_goal(baseline):
    original = baseline.session("original")
    fresh = baseline.session("fresh")
    context = baseline.context(fresh)
    context.goal = Goal.create("stale cached goal")
    load_and_restore(original, fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert context.goal is None


@pytest.mark.asyncio
async def test_resume_preserves_actual_usage_not_request_budget(baseline):
    original = baseline.session("original")
    await baseline.run(original, baseline.model(original, [[baseline.text("done")]]))
    actual = serialize_usage(original.state.usage)
    fresh = baseline.session("fresh")
    load_and_restore(original, fresh)
    assert serialize_usage(fresh.state.usage) == actual


@pytest.mark.asyncio
async def test_resume_preserves_reminder_counters(baseline):
    original = baseline.session("original")
    context = baseline.context(original)
    todo_write_impl(context, todos())
    context.todo_turns_since_write = 9
    context.todo_turns_since_reminder = 4
    # Simulate the request-boundary commit after the reminder processor runs.
    from siada.services.session_runtime_state import save_context

    save_context(context)
    fresh = baseline.session("fresh")
    load_and_restore(original, fresh)
    restored = baseline.context(fresh)
    await SiadaRunner._prepare_context_for_run(restored, fresh)
    assert (restored.todo_turns_since_write, restored.todo_turns_since_reminder) == (9, 4)


@pytest.mark.asyncio
async def test_repeated_resume_does_not_duplicate_unfinished_notice(baseline):
    original = baseline.session("original")
    subagent_persistence.record_start(
        original.siada_config.workspace, original.session_id, agent_id="unfinished",
        parent_id=None, depth=1, title="Unfinished", instruction="Inspect module",
    )
    fresh = baseline.session("fresh")
    context = baseline.context(fresh)
    load_and_restore(original, fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    load_and_restore(original, fresh)
    await SiadaRunner._prepare_context_for_run(context, fresh)
    assert len(context.hook_pending_contexts) == 1


@pytest.mark.asyncio
async def test_resume_restores_session_title(baseline):
    original = baseline.session("original")
    metadata = original.openai_session._read_metadata()
    metadata["title"] = "Synthetic restored title"
    original.openai_session._write_metadata(metadata)
    fresh = baseline.session("fresh")
    fresh.state.session_title = "stale title"
    load_and_restore(original, fresh)
    assert fresh.state.session_title == "Synthetic restored title"


@pytest.mark.asyncio
async def test_cross_workspace_resume_uses_target_workspace(baseline):
    original = baseline.session("original", baseline.workspace("target-workspace"))
    fresh = baseline.session("fresh", baseline.workspace("other-workspace"))
    load_and_restore(original, fresh)
    assert fresh.openai_session.session_folder == original.openai_session.session_folder
    assert fresh.siada_config.workspace == original.siada_config.workspace