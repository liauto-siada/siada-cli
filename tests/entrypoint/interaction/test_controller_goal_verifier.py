"""
Tests for Controller._maybe_run_goal_verifier and _push_goal_state_via_acp.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.turn.models import TurnOutput, TurnType
from siada.services.goal.models import (
    Goal,
    GoalVerdict,
    GOAL_MAX_CONSECUTIVE_FAILURES,
    GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
)
from siada.services.goal import goal_storage


def _make_controller():
    ctrl = Controller.__new__(Controller)
    ctrl.config = SimpleNamespace(acp_mode=False, io=SimpleNamespace(acp_adapter=None))
    ctrl._acp_notifications = []

    def fake_send(method, params):
        ctrl._acp_notifications.append((method, params))

    ctrl._send_acp_notification = fake_send
    return ctrl


def _make_turn(turn_type=TurnType.CONVERSATION):
    return SimpleNamespace(get_turn_type=lambda: turn_type)


def _make_session(workspace="/ws"):
    file_session = SimpleNamespace()
    return SimpleNamespace(
        openai_session=file_session,
        siada_config=SimpleNamespace(workspace=workspace),
    )


def _context_cache_with(workspace, goal):
    context = SimpleNamespace(goal=goal)
    return {("agent", workspace): context}, context


@pytest.fixture
def base_result():
    return TurnOutput(output="assistant reply", metadata={"k": "v"}, next_action=None)


class TestMaybeRunGoalVerifier:
    def test_skips_command_turns(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn(TurnType.COMMAND)
        session = _make_session()
        out = ctrl._maybe_run_goal_verifier(turn, session, Path("/tmp"), base_result)
        assert out is base_result
        assert ctrl._acp_notifications == []

    def test_skips_when_result_is_none(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        out = ctrl._maybe_run_goal_verifier(turn, session, Path("/tmp"), None)
        assert out is None

    def test_skips_when_no_active_goal(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        fake_cache, _ = _context_cache_with("/ws", None)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            out = ctrl._maybe_run_goal_verifier(turn, session, Path("/tmp"), base_result)
        assert out is base_result
        assert ctrl._acp_notifications == []

    def test_skips_when_goal_paused(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        goal = Goal.create("paused goal")
        goal.status = "paused"
        fake_cache, _ = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            out = ctrl._maybe_run_goal_verifier(turn, session, Path("/tmp"), base_result)
        assert out is base_result
        assert ctrl._acp_notifications == []

    def test_verdict_passed_marks_complete(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=True, reason="all good")),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert out is base_result
            assert goal.status == "complete"
            assert goal.turns == 1
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "complete"
            assert persisted.turns == 1
            methods = [m for m, _ in ctrl._acp_notifications]
            assert methods == ["context/goalState", "context/goalState"]
            assert ctrl._acp_notifications[0][1]["verifying"] is True
            assert ctrl._acp_notifications[-1][1]["goal"]["status"] == "complete"
            # A structured "result" payload rides along on the final push so
            # the frontend can render the collapsible "Goal achieved" summary.
            final_result = ctrl._acp_notifications[-1][1]["result"]
            assert final_result["achieved"] is True
            assert final_result["turns"] == 1
            assert final_result["objective"] == "ship it"
            assert final_result["reason"] == "all good"
            assert "elapsedSeconds" in final_result
            assert "tokensUsed" in final_result

    def test_verdict_failed_injects_feedback_switch_event(self, base_result):
        from siada.support.slash_commands import SwitchEvent

        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=False, reason="tests not run")),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "active"
            assert goal.consecutive_failures == 1
            assert goal.turns == 1
            assert isinstance(out.output, SwitchEvent)
            assert "tests not run" in out.output.kwargs["ai_analysis_prompt"]
            assert "ship it" in out.output.kwargs["ai_analysis_prompt"]
            # metadata from the original result must be preserved
            assert out.metadata == base_result.metadata
            # A "not yet achieved" result payload rides along on the final push.
            final_result = ctrl._acp_notifications[-1][1]["result"]
            assert final_result["achieved"] is False
            assert final_result["turns"] == 1
            assert final_result["reason"] == "tests not run"

    def test_verdict_failed_with_next_action_appends_it_to_feedback(self, base_result):
        from siada.support.slash_commands import SwitchEvent

        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("do something ambitious")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False,
                        reason="tests still failing",
                        nextAction="run the test suite and fix the failures",
                    )
                ),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert isinstance(out.output, SwitchEvent)
            prompt = out.output.kwargs["ai_analysis_prompt"]
            assert "tests still failing" in prompt
            assert "run the test suite and fix the failures" in prompt


    def test_turns_increments_across_multiple_verification_rounds(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=False, reason="not yet")),
            ):
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.turns == 2
            assert goal.consecutive_failures == 2

    def test_consecutive_failures_trip_to_blocked(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ambiguous goal")
            goal.consecutive_failures = GOAL_MAX_CONSECUTIVE_FAILURES - 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=False, reason="still unclear")),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.consecutive_failures == GOAL_MAX_CONSECUTIVE_FAILURES
            # Once blocked, the turn output passes through unchanged — no forced retry.
            assert out is base_result
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "blocked"

    def test_verifier_exception_does_not_crash_turn(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            # A crash in the verifier call itself (not a returned failed verdict)
            # must fail safe: pass the turn through unchanged, no genuine-judgment
            # failure recorded -- but it DOES count against the small, separate
            # system-error budget (GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS) so a
            # persistently broken verifier still surfaces to the user quickly.
            assert out is base_result
            assert goal.status == "active"
            assert goal.consecutive_failures == 0
            assert goal.consecutive_system_errors == 1

    def test_repeated_verifier_exceptions_trip_to_blocked_quickly(self, base_result):
        """Unlike genuine 'not yet achieved' judgments (which get a generous
        GOAL_MAX_CONSECUTIVE_FAILURES budget), a run of verifier CRASHES
        (never even producing a verdict) must trip 'blocked' after the much
        smaller GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS threshold."""
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.consecutive_system_errors = GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS - 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(side_effect=RuntimeError("boom again")),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.consecutive_system_errors == GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
            assert goal.consecutive_failures == 0
            assert out is base_result
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "blocked"

    def test_system_error_verdict_does_not_count_as_genuine_failure(self, base_result):
        """A GoalVerdict.systemError=True verdict (returned by verifier.py's
        exception handlers -- see verifier.py) is a mechanical fail-safe, not
        a genuine judgment about the objective. It must not consume the
        generous GOAL_MAX_CONSECUTIVE_FAILURES budget."""
        from siada.support.slash_commands import SwitchEvent

        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False, reason="verifier blew up", systemError=True,
                    )
                ),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "active"
            assert goal.consecutive_system_errors == 1
            assert goal.consecutive_failures == 0
            assert isinstance(out.output, SwitchEvent)

    def test_consecutive_system_errors_trip_to_blocked_much_faster_than_failures(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ambiguous goal")
            goal.consecutive_system_errors = GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS - 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False, reason="verifier blew up again", systemError=True,
                    )
                ),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.consecutive_system_errors == GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
            assert goal.consecutive_failures == 0
            assert out is base_result
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "blocked"

    def test_genuine_failure_resets_system_error_streak(self, base_result):
        """A genuine "not yet achieved" judgment (systemError=False) must
        reset any accumulated system-error streak -- an occasional infra
        hiccup followed by a real judgment isn't a persistently broken
        verifier."""
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.consecutive_system_errors = 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=False, reason="not yet")),
            ):
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.consecutive_system_errors == 0
            assert goal.consecutive_failures == 1

    def test_genuine_success_resets_system_error_streak(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.consecutive_system_errors = 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=True, reason="all good")),
            ):
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "complete"
            assert goal.consecutive_system_errors == 0


class TestMaybeResetGoalOnNewTurn:
    """Tests for Controller._maybe_reset_goal_on_new_turn.

    A fresh conversation turn should normalize a stale goal left over from a
    previous turn: "complete" goals are dropped entirely, "blocked" goals are
    reactivated (so the user typing again resumes verification automatically,
    without requiring an explicit /goal resume).
    """

    def test_skips_command_turns(self):
        ctrl = _make_controller()
        turn = _make_turn(TurnType.COMMAND)
        session = _make_session()
        goal = Goal.create("ship it")
        goal.status = "complete"
        fake_cache, context = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        # Slash-command turns (including /goal itself) must not touch the goal.
        assert context.goal is goal
        assert ctrl._acp_notifications == []

    def test_skips_when_no_goal(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        fake_cache, _ = _context_cache_with("/ws", None)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        assert ctrl._acp_notifications == []

    def test_skips_when_goal_active(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        goal = Goal.create("ship it")
        fake_cache, context = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        assert context.goal is goal
        assert goal.status == "active"
        assert ctrl._acp_notifications == []

    def test_skips_when_goal_paused(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        goal = Goal.create("ship it")
        goal.status = "paused"
        fake_cache, context = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        assert context.goal is goal
        assert goal.status == "paused"
        assert ctrl._acp_notifications == []

    def test_complete_goal_is_cleared_on_new_input(self):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.status = "complete"
            goal_storage.save_goal(session_dir, goal)
            fake_cache, context = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(turn, session, session_dir)

            # Context and on-disk state must both be cleared — no lingering
            # "Goal complete" status bar on the next turn.
            assert context.goal is None
            assert goal_storage.load_goal(session_dir) is None
            assert ctrl._acp_notifications == [
                ("context/goalState", {"goal": None, "verifying": False})
            ]
            # The goal must be archived to history before it's dropped --
            # goal.json only ever holds the current goal.
            history = goal_storage.load_goal_history(session_dir)
            assert len(history) == 1
            assert history[0]["objective"] == "ship it"
            assert history[0]["status"] == "complete"

    def test_blocked_goal_is_reactivated_on_new_input(self):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.status = "blocked"
            goal.consecutive_failures = GOAL_MAX_CONSECUTIVE_FAILURES
            fake_cache, context = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(turn, session, session_dir)

            assert context.goal is goal
            assert goal.status == "active"
            assert goal.consecutive_failures == 0
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "active"
            assert persisted.consecutive_failures == 0
            methods = [m for m, _ in ctrl._acp_notifications]
            assert methods == ["context/goalState"]
            assert ctrl._acp_notifications[0][1]["goal"]["status"] == "active"

    def test_blocked_goal_reactivation_resets_reminder_injected(self):
        """Reactivating a blocked goal is a meaningful restart of work on
        it, so the model must see the hidden reminder again on the next
        turn -- reminder_injected must be reset to False, same as a brand
        new goal via Goal.create() (see
        SiadaRunner._maybe_merge_goal_reminder)."""
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.status = "blocked"
            goal.consecutive_failures = GOAL_MAX_CONSECUTIVE_FAILURES
            goal.reminder_injected = True  # was already reminded before blocking
            fake_cache, context = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(turn, session, session_dir)

            assert goal.reminder_injected is False
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.reminder_injected is False


