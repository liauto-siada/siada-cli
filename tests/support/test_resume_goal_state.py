"""Tests covering the GoalStatusBar-on-resume bug fix:

Resuming a session with an active (non-cleared) goal used to leave the
frontend's GoalStatusBar blank until the next conversation turn happened to
run SiadaRunner._prepare_context_for_run's lazy pending_goal -> context.goal
consumption. Two pieces fix this:

1. ResumeService.restore_to_running_session must reliably stage the
   recovered goal (or explicitly clear a stale one) on
   running_session.state.pending_goal, regardless of what was there before.
2. SlashCommands.cmd_resume must immediately re-push that goal's state to
   the frontend via context/goalState right after restoring, instead of
   waiting for the next turn.

createdAt/turns/status/objective are already persisted to goal.json on
every save_goal() call throughout the goal's lifecycle (see
goal_storage.py / turn_hooks.py) -- no additional persistence work was
needed for those; this is purely about RE-SENDING that already-durable
state to a freshly (re)connected frontend.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import siada.session  # noqa: F401 -- break circular-import chain
import siada.support.checkpoint_tracker  # noqa: F401

from siada.services.goal import goal_storage
from siada.services.goal.models import Goal
from siada.services.session_management import SessionData
from siada.support.resume_service import ResumeService
from siada.support.slash_commands import SlashCommands
from siada.tools.todo.models import TodoItem


def _make_running_session() -> MagicMock:
    running_session = MagicMock()
    running_session.state.openai_session = None  # skip the FileSession swap branch
    running_session.state.pending_goal = None
    return running_session


def _make_session_data(session_dir: Path) -> SessionData:
    return SessionData(
        session_id="sess-123",
        items=[],
        metadata={},
        api_messages=None,
        api_messages_tokens=None,
        session_path=session_dir,
    )


class TestRestoreToRunningSessionStagesGoal:
    def test_stages_recovered_goal_into_pending_goal(self):
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal = Goal.create("ship the feature")
            goal_storage.save_goal(session_dir, goal)

            running_session = _make_running_session()
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            staged = running_session.state.pending_goal
            assert staged is not None
            assert staged.objective == "ship the feature"
            assert staged.status == "active"

    def test_explicitly_clears_stale_pending_goal_when_no_goal_json(self):
        """A stale pending_goal from a PREVIOUS resume/goal activity on the
        same long-lived RunningSession object must never leak into a
        session that has no goal.json (e.g. goal was cleared before
        disconnecting, or this is a different, goal-less session)."""
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)  # no goal.json written

            running_session = _make_running_session()
            running_session.state.pending_goal = Goal.create("stale leftover goal")
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            assert running_session.state.pending_goal is None


class TestPushResumedGoalStateToUi:
    def _make_slash_commands_with_acp(self):
        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        return sc

    def test_restored_blocked_goal_pushes_frozen_time_without_reactivation(self, tmp_path):
        sc = self._make_slash_commands_with_acp()
        clock = {"now": "2026-01-01T00:00:00Z"}
        with patch("siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]):
            goal = Goal.create("restore frozen Goal time")
            clock["now"] = "2026-01-01T00:00:12.250Z"
            goal.set_status("blocked")
            goal_storage.save_goal(tmp_path, goal)
            clock["now"] = "2026-01-01T01:00:00Z"
            session = _make_running_session()
            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()), _make_session_data(tmp_path), session,
            )
            sc._push_resumed_goal_state_to_ui(session)
            snapshot = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]["goal"]
            assert snapshot["status"] == "blocked"
            assert snapshot["elapsedSeconds"] == 12.25
            assert snapshot["elapsedUpdatedAt"] == clock["now"]
            assert session.state.pending_goal.status == "blocked"

    def test_pushes_goal_state_when_goal_present(self):
        sc = self._make_slash_commands_with_acp()
        session = MagicMock()
        goal = Goal.create("ship the feature")
        goal.turns = 3
        session.state.pending_goal = goal

        sc._push_resumed_goal_state_to_ui(session)

        sc.io.acp_adapter._send_if_acp.assert_called_once()
        _, kwargs = sc.io.acp_adapter._send_if_acp.call_args
        assert kwargs["method"] == "context/goalState"
        assert kwargs["params"]["goal"]["objective"] == "ship the feature"
        assert kwargs["params"]["goal"]["status"] == "active"
        assert kwargs["params"]["goal"]["createdAt"] == goal.created_at
        assert kwargs["params"]["goal"]["turns"] == 3
        assert kwargs["params"]["verifying"] is False

    def test_pushes_explicit_clear_when_no_goal(self):
        sc = self._make_slash_commands_with_acp()
        session = MagicMock()
        session.state.pending_goal = None

        sc._push_resumed_goal_state_to_ui(session)

        sc.io.acp_adapter._send_if_acp.assert_called_once()
        _, kwargs = sc.io.acp_adapter._send_if_acp.call_args
        assert kwargs["method"] == "context/goalState"
        assert kwargs["params"] == {"goal": None, "verifying": False}

    def test_noop_when_not_in_acp_mode(self):
        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = None
        session = MagicMock()
        session.state.pending_goal = Goal.create("ship the feature")

        # Must not raise even though there's a goal to push.
        sc._push_resumed_goal_state_to_ui(session)


class TestPushResumedTodoStateToUi:
    def test_resume_command_pushes_goal_and_todos_after_history(self):
        sc = SlashCommands(io=MagicMock())
        session = MagicMock()
        session.siada_config.workspace = "/sample/project"
        data = SessionData(session_id="resumed", items=[], metadata={})
        service = MagicMock()
        service.get_session_info.return_value.project_root = "/sample/project"
        service.execute.return_value = (data, "Restored")
        calls = []
        with (
            patch("siada.support.resume_service.ResumeService", return_value=service),
            patch.object(sc, "_send_history_to_ui", side_effect=lambda _: calls.append("history")),
            patch.object(sc, "_push_resumed_goal_state_to_ui", side_effect=lambda _: calls.append("goal")),
            patch.object(sc, "_push_resumed_todo_state_to_ui", side_effect=lambda _: calls.append("todos")),
        ):
            sc.cmd_resume(session, "resumed")

        service.restore_to_running_session.assert_called_once_with(data, session)
        assert calls == ["history", "goal", "todos"]

    def test_pushes_recovered_todos_without_consuming_pending_state(self):
        sc = SlashCommands(io=MagicMock())
        session = MagicMock()
        todos = [
            TodoItem(content="Inspect module", active_form="Inspecting module", status="in_progress"),
            TodoItem(content="Add tests", active_form="Adding tests", status="pending"),
        ]
        session.state.pending_todos = todos

        sc._push_resumed_todo_state_to_ui(session)

        _, kwargs = sc.io.acp_adapter._send_if_acp.call_args
        assert kwargs["method"] == "context/todoState"
        assert kwargs["params"] == {"todos": [
            {"content": "Inspect module", "status": "in_progress"},
            {"content": "Add tests", "status": "pending"},
        ]}
        assert session.state.pending_todos is todos

    def test_empty_todos_explicitly_clear_frontend(self):
        sc = SlashCommands(io=MagicMock())
        session = MagicMock()
        session.state.pending_todos = []

        sc._push_resumed_todo_state_to_ui(session)

        _, kwargs = sc.io.acp_adapter._send_if_acp.call_args
        assert kwargs["params"] == {"todos": []}

    def test_noop_without_acp(self):
        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = None
        sc._push_resumed_todo_state_to_ui(MagicMock())
class TestReplayGoalVerificationRecords:
    def test_replays_archived_and_current_verification_records(self, tmp_path):
        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        archived = Goal.create("previous goal")
        archived.verification_results = [{"id": "previous-check", "achieved": True}]
        goal_storage.append_goal_history(tmp_path, archived)
        current = Goal.create("current goal")
        current.verification_results = [{"id": "current-check", "achieved": False}]
        session = MagicMock()
        session.state.openai_session.session_folder = tmp_path
        session.state.pending_goal = current
        sc._push_resumed_goal_state_to_ui(session)
        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["results"] == archived.verification_results + current.verification_results
        assert params["latestResult"] == current.verification_results[-1]

        session.state.pending_goal = None
        sc._push_resumed_goal_state_to_ui(session)
        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["goal"] is None
        assert params["results"] == archived.verification_results


def _make_push_session(session_dir=None, workspace="/sample/project", session_id="sess-123"):
    """Build a minimal RunningSession-shaped object for the UI push helpers."""
    return SimpleNamespace(
        session_id=session_id,
        siada_config=SimpleNamespace(workspace=workspace),
        state=SimpleNamespace(
            openai_session=SimpleNamespace(session_folder=session_dir),
            pending_goal=None,
        ),
    )


class TestPushCurrentGoalState:
    """``/model`` reloads history (ui/loadHistory) but must re-push the goal.

    The frontend drops its local goal state whenever it replaces history, so
    the live goal snapshot has to follow immediately; otherwise the Goal
    status bar stays missing until the next verifier round.
    """

    def test_pushes_live_context_goal_and_replays_verdicts(self, tmp_path):
        from siada.services.siada_runner import SiadaRunner

        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        archived = Goal.create("previous goal")
        archived.verification_results = [{"id": "previous-check"}]
        goal_storage.append_goal_history(tmp_path, archived)
        current = Goal.create("current goal")
        current.verification_results = [{"id": "current-check"}]
        session = _make_push_session(session_dir=tmp_path)
        context = SimpleNamespace(goal=current, session=SimpleNamespace(session_id="sess-123"))
        cache = {("coder", "/sample/project", "sess-123"): context}

        with patch.dict(SiadaRunner._context_cache, cache, clear=True):
            sc._push_current_goal_state_to_ui(session)

        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["goal"]["objective"] == "current goal"
        assert params["goal"]["status"] == "active"
        assert params["verifying"] is False
        assert params["results"] == archived.verification_results + current.verification_results
        assert params["latestResult"] == current.verification_results[-1]

    def test_falls_back_to_persisted_goal_without_live_context(self, tmp_path):
        from siada.services.siada_runner import SiadaRunner

        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        goal_storage.save_goal(tmp_path, Goal.create("persisted goal"))
        session = _make_push_session(session_dir=tmp_path)

        with patch.dict(SiadaRunner._context_cache, {}, clear=True):
            sc._push_current_goal_state_to_ui(session)

        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["goal"]["objective"] == "persisted goal"

    def test_prefers_staged_goal_over_persisted_file(self, tmp_path):
        from siada.services.siada_runner import SiadaRunner

        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        goal_storage.save_goal(tmp_path, Goal.create("persisted goal"))
        staged = Goal.create("staged goal")
        session = _make_push_session(session_dir=tmp_path)
        session.state.pending_goal = staged

        with patch.dict(SiadaRunner._context_cache, {}, clear=True):
            sc._push_current_goal_state_to_ui(session)

        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["goal"]["objective"] == "staged goal"

    def test_explicitly_clears_frontend_when_no_goal_exists(self, tmp_path):
        from siada.services.siada_runner import SiadaRunner

        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = MagicMock()
        session = _make_push_session(session_dir=tmp_path)

        with patch.dict(SiadaRunner._context_cache, {}, clear=True):
            sc._push_current_goal_state_to_ui(session)

        params = sc.io.acp_adapter._send_if_acp.call_args.kwargs["params"]
        assert params["goal"] is None
        assert params["verifying"] is False

    def test_noop_without_acp(self, tmp_path):
        sc = SlashCommands(io=MagicMock())
        sc.io.acp_adapter = None
        goal_storage.save_goal(tmp_path, Goal.create("persisted goal"))

        sc._push_current_goal_state_to_ui(_make_push_session(session_dir=tmp_path))

        sc.io.acp_adapter = MagicMock()
        sc._push_current_goal_state_to_ui(_make_push_session(session_dir=tmp_path))
        assert sc.io.acp_adapter._send_if_acp.call_count == 1
