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
from unittest.mock import MagicMock

import siada.session  # noqa: F401 -- break circular-import chain
import siada.support.checkpoint_tracker  # noqa: F401

from siada.services.goal import goal_storage
from siada.services.goal.models import Goal
from siada.services.session_management import SessionData
from siada.support.resume_service import ResumeService
from siada.support.slash_commands import SlashCommands


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
