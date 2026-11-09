"""
Tests for TurnPolicy._maybe_run_goal_verifier and _push_goal_state_via_acp.
"""
import tempfile
from contextlib import contextmanager
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import turn_policy first: it pulls in siada.session before turn.models
# touches siada.support.slash_commands, avoiding a circular import
# (checkpoint_tracker <-> session_manager) that the old controller import
# used to mask.
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.entrypoint.interaction.turn.models import GOAL_VERIFICATION_METADATA_KEY, TurnOutput, TurnType
from siada.services.goal.models import (
    Goal,
    GoalVerdict,
    GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
    GOAL_MAX_TURNS,
)
from siada.services.goal import goal_storage


def _make_controller():
    notifications = []

    def fake_send(method, params):
        notifications.append((method, params))

    policy = TurnPolicy(
        config=SimpleNamespace(acp_mode=False, io=SimpleNamespace(acp_adapter=None)),
        slash_commands=SimpleNamespace(),
        send_notification=fake_send,
    )
    policy._acp_notifications = notifications
    # Keep the existing synchronous verdict assertions; execute the async
    # verifier on a real loop rather than mocking its coroutine boundary.
    verify = policy._maybe_run_goal_verifier
    policy._maybe_run_goal_verifier = lambda *args: asyncio.run(verify(*args))
    return policy


def _make_turn(turn_type=TurnType.CONVERSATION):
    return SimpleNamespace(get_turn_type=lambda: turn_type)


def _make_session(workspace="/ws"):
    file_session = SimpleNamespace()
    return SimpleNamespace(
        session_id="goal-session",
        openai_session=file_session,
        siada_config=SimpleNamespace(workspace=workspace),
    )


def _context_cache_with(workspace, goal, goal_max_turns=None):
    context = SimpleNamespace(goal=goal)
    if goal_max_turns is not None:
        context.goal_max_turns = goal_max_turns
    return {("agent", workspace, "goal-session"): context}, context


@pytest.fixture
def base_result():
    return TurnOutput(output="assistant reply", metadata={"k": "v"}, next_action=None)


class TestMaybeRunGoalVerifier:
    @pytest.mark.parametrize("outcome", ["achieved", "no_next_action", "exhausted", "system_error", "crashed"])
    def test_terminal_outcomes_freeze_timing_and_push_current_verification_round(self, tmp_path, base_result, outcome):
        clock = {"now": "2026-01-01T00:00:00Z"}
        ctrl = _make_controller()
        session = _make_session()
        with patch("siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]):
            goal = Goal.create("verify elapsed time")
            goal.consecutive_system_errors = GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS - 1
            cache, _ = _context_cache_with("/ws", goal, goal_max_turns=1)
            clock["now"] = "2026-01-01T00:00:02Z"

            async def verify(*args):
                clock["now"] = "2026-01-01T00:00:10.750Z"
                if outcome == "crashed":
                    raise RuntimeError("Synthetic verifier crash")
                return GoalVerdict(
                    passed=outcome == "achieved", reason="Synthetic verdict",
                    nextAction="" if outcome == "no_next_action" else "Run synthetic checks",
                    systemError=outcome == "system_error",
                )

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", cache), patch(
                "siada.services.goal.verifier.run_goal_verification", new=verify,
            ):
                ctrl._maybe_run_goal_verifier(_make_turn(), session, tmp_path, base_result)
            initial = ctrl._acp_notifications[0][1]
            final = ctrl._acp_notifications[-1][1]
            assert initial["verifying"] is True
            assert initial["goal"]["turns"] == 1
            assert initial["goal"]["elapsedSeconds"] == 2
            assert final["goal"]["elapsedSeconds"] == 10.75
            assert final["result"]["elapsedSeconds"] == 10
            assert final["goal"]["status"] == ("complete" if outcome == "achieved" else "blocked")
            clock["now"] = "2026-01-01T01:00:00Z"
            assert goal_storage.load_goal(tmp_path).elapsed_seconds() == 10.75

    @pytest.mark.parametrize("failure", ["no_next_action", "exhausted", "system_error", "crashed"])
    def test_blocked_outcome_preserves_answer_and_carries_failure_metadata(self, base_result, tmp_path, failure):
        ctrl = _make_controller()
        session = _make_session()
        goal = Goal.create("Ship synthetic feature")
        goal.consecutive_system_errors = GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS - 1
        cache, _ = _context_cache_with("/ws", goal, goal_max_turns=1)
        original_metadata = dict(base_result.metadata)
        verdict = GoalVerdict(
            passed=False, reason="Synthetic tests failed",
            nextAction="" if failure == "no_next_action" else "Fix the synthetic tests",
            systemError=failure == "system_error",
        )
        verify = AsyncMock(return_value=verdict)
        if failure == "crashed":
            verify.side_effect = RuntimeError("Synthetic verifier crashed")
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", cache), patch(
            "siada.services.goal.verifier.run_goal_verification", verify,
        ):
            out = ctrl._maybe_run_goal_verifier(_make_turn(), session, tmp_path, base_result)
        assert out.output == "assistant reply"
        assert out.metadata["k"] == original_metadata["k"]
        outcome = out.metadata[GOAL_VERIFICATION_METADATA_KEY]
        assert outcome["status"] == "blocked"
        assert outcome["objective"] == goal.objective
        assert outcome["notice"] == ctrl._acp_notifications[-1][1]["notice"]
        assert outcome["reason"] == (
            "Goal verification could not finish: Synthetic verifier crashed"
            if failure == "crashed" else verdict.reason
        )
        if failure in {"system_error", "crashed"}:
            assert "Send a new message to resume work" in outcome["notice"]
            assert "/goal resume" not in outcome["notice"]

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
            assert final_result["outcome"] == "achieved"
            assert final_result["continuing"] is False
            assert goal_storage.load_goal(session_dir).verification_results == [final_result]
            assert ctrl._acp_notifications[-1][1]["latestResult"] == final_result

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
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False,
                        reason="tests not run",
                        nextAction="run the tests",
                    )
                ),
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
            assert final_result["outcome"] == "not_achieved"
            assert final_result["continuing"] is True
            assert goal_storage.load_goal(session_dir).verification_results == [final_result]

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
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False, reason="not yet", nextAction="continue implementation"
                    )
                ),
            ):
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.turns == 2
            assert goal.consecutive_failures == 2

    def test_max_consecutive_failures_trip_to_blocked(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ambiguous goal")
            goal.consecutive_failures = GOAL_MAX_TURNS - 1
            fake_cache, _ = _context_cache_with("/ws", goal, goal_max_turns=GOAL_MAX_TURNS)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False,
                        reason="still unclear",
                        nextAction="inspect the failing evidence",
                    )
                ),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.turns == 1
            assert goal.consecutive_failures == GOAL_MAX_TURNS
            # Once blocked, the turn output passes through unchanged — no forced retry.
            assert out is base_result
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "blocked"

    def test_configured_max_consecutive_failures_override_default(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("bounded goal")
            goal.consecutive_failures = 1
            fake_cache, _ = _context_cache_with("/ws", goal, goal_max_turns=2)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False, reason="not yet", nextAction="make one more change"
                    )
                ),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.consecutive_failures == 2
            assert out is base_result

    @pytest.mark.parametrize("next_action", ["", " \n\t "])
    def test_empty_next_action_stops_automatic_continuation(self, base_result, next_action):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("no actionable follow-up")
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(
                    passed=False, reason="nothing remains", nextAction=next_action,
                )),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            assert goal.turns == 1
            assert out is base_result
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.status == "blocked"
            assert ctrl._acp_notifications[-1][1]["result"]["nextAction"] == ""

    @pytest.mark.parametrize("error", [RuntimeError("boom"), AttributeError("Synthetic legacy timer is unavailable")])
    def test_verifier_exception_schedules_continuation(self, base_result, error):
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
                new=AsyncMock(side_effect=error),
            ):
                out = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert isinstance(out.output, SwitchEvent)
            assert out.metadata == base_result.metadata
            assert str(error) in out.output.kwargs["ai_analysis_prompt"]
            assert goal.status == "active"
            assert goal.consecutive_failures == 0
            assert goal.consecutive_system_errors == 1
            records = goal_storage.load_goal(session_dir).verification_results
            assert len(records) == 1
            assert records[0]["outcome"] == "system_error"
            assert records[0]["continuing"] is True
            assert ctrl._acp_notifications[-1][1]["result"] == records[0]

    def test_verifier_crash_then_success_completes_after_continuation(self, tmp_path, base_result):
        from siada.support.slash_commands import SwitchEvent

        ctrl = _make_controller()
        session = _make_session()
        goal = Goal.create("Complete synthetic verification")
        cache, _ = _context_cache_with("/ws", goal)
        verify = AsyncMock(side_effect=[
            RuntimeError("Synthetic temporary verifier failure"),
            GoalVerdict(passed=True, reason="Synthetic evidence is complete"),
        ])
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", cache), patch(
            "siada.services.goal.verifier.run_goal_verification", verify,
        ):
            first = ctrl._maybe_run_goal_verifier(_make_turn(), session, tmp_path, base_result)
            assert isinstance(first.output, SwitchEvent)
            assert goal.status == "active"
            second = ctrl._maybe_run_goal_verifier(_make_turn(), session, tmp_path, base_result)

        assert second is base_result
        assert goal.status == "complete"
        assert goal.turns == 2
        assert goal.consecutive_system_errors == 0
        records = goal_storage.load_goal(tmp_path).verification_results
        assert [record["outcome"] for record in records] == ["system_error", "achieved"]
        assert [record["continuing"] for record in records] == [True, False]
        assert records[0]["id"] != records[1]["id"]

    def test_repeated_verifier_exceptions_trip_to_blocked_quickly(self, base_result):
        """Unlike genuine 'not yet achieved' judgments (which use the configured
        maximum-turn budget), a run of verifier CRASHES
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
        configured maximum-turn budget."""
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

    def test_system_error_breaker_is_independent_of_one_turn_limit(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            fake_cache, _ = _context_cache_with("/ws", goal, goal_max_turns=1)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(
                    passed=False, reason="verifier unavailable", systemError=True,
                )),
            ):
                first = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)
                assert goal.status == "active"
                second = ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            from siada.support.slash_commands import SwitchEvent

            assert isinstance(first.output, SwitchEvent)
            assert second is base_result
            assert goal.status == "blocked"
            assert goal.consecutive_failures == 0
            assert goal.consecutive_system_errors == GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
            records = goal_storage.load_goal(session_dir).verification_results
            assert [record["outcome"] for record in records] == ["system_error", "system_error"]
            assert [record["continuing"] for record in records] == [True, False]
            assert records[0]["id"] != records[1]["id"]
            assert ctrl._acp_notifications[2][1]["latestResult"] == records[0]
            assert "/goal resume" not in ctrl._acp_notifications[-1][1]["notice"]

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
                new=AsyncMock(
                    return_value=GoalVerdict(
                        passed=False, reason="not yet", nextAction="continue implementation"
                    )
                ),
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
    """Tests for TurnPolicy._maybe_reset_goal_on_new_turn.

    A fresh conversation turn should normalize a stale goal left over from a
    previous turn: "complete" goals are cleared on new user conversations, "blocked" goals are
    reactivated when the user sends a new conversational message, which resumes
    verification automatically without an additional command.
    """

    def test_blocked_goal_resume_preserves_elapsed_time_and_excludes_wait(self, tmp_path):
        ctrl = _make_controller()
        session = _make_session()
        clock = {"now": "2026-01-01T00:00:00Z"}
        with patch("siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]):
            goal = Goal.create("resume a timed goal")
            clock["now"] = "2026-01-01T00:00:12.250Z"
            goal.set_status("blocked")
            goal_storage.save_goal(tmp_path, goal)
            restored = goal_storage.load_goal(tmp_path)
            cache, _ = _context_cache_with("/ws", restored)
            clock["now"] = "2026-01-01T01:00:00Z"
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", cache):
                ctrl._maybe_reset_goal_on_new_turn(_make_turn(), session, tmp_path)
            snapshot = ctrl._acp_notifications[-1][1]["goal"]
            assert snapshot["status"] == "active"
            assert snapshot["elapsedSeconds"] == 12.25
            assert snapshot["elapsedUpdatedAt"] == clock["now"]
            clock["now"] = "2026-01-01T01:00:02.750Z"
            assert goal_storage.load_goal(tmp_path).elapsed_seconds() == 15

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

    def test_active_goal_refreshes_frontend_snapshot(self):
        """An unchanged active goal is re-pushed on a user turn.

        The status bar is rendered purely from these pushes, so continuing
        after an interrupt (or after any frontend state reset) must restore
        it instead of waiting for the next verifier round.
        """
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        goal = Goal.create("ship it")
        fake_cache, context = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        assert context.goal is goal
        assert goal.status == "active"
        assert [m for m, _ in ctrl._acp_notifications] == ["context/goalState"]
        snapshot = ctrl._acp_notifications[-1][1]
        assert snapshot["goal"]["status"] == "active"
        assert snapshot["verifying"] is False

    def test_paused_goal_resumes_on_new_user_turn(self):
        """A goal paused by an interruption resumes when the user types again.

        Unlike a blocked goal, resuming keeps the accumulated time and the
        failure counters: an interruption is not a fresh retry budget.
        """
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        goal = Goal.create("ship it")
        goal.set_status("paused")
        goal.consecutive_failures = 2
        goal.reminder_injected = True
        fake_cache, context = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(turn, session, Path("/tmp"))
        assert context.goal is goal
        assert goal.status == "active"
        assert goal.consecutive_failures == 2
        assert goal.reminder_injected is True
        assert [m for m, _ in ctrl._acp_notifications] == ["context/goalState"]
        assert ctrl._acp_notifications[-1][1]["goal"]["status"] == "active"
        assert ctrl._acp_notifications[-1][1]["verifying"] is False

    def test_complete_goal_is_archived_and_cleared_on_new_input(self, tmp_path, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session()
        clock = {"now": "2026-01-01T00:00:00Z"}
        with patch("siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]):
            goal = Goal.create("ship it")
            clock["now"] = "2026-01-01T00:01:02Z"
            goal.set_status("complete")
            goal.turns = 2
            goal_storage.save_goal(tmp_path, goal)
            fake_cache, context = _context_cache_with("/ws", goal)
            clock["now"] = "2026-01-01T01:00:00Z"

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification", new=AsyncMock(),
            ) as verify:
                ctrl._maybe_reset_goal_on_new_turn(turn, session, tmp_path)
                assert ctrl._maybe_run_goal_verifier(turn, session, tmp_path, base_result) is base_result

            assert context.goal is None
            assert goal.status == "complete"
            assert goal.elapsed_seconds() == 62
            assert goal.turns == 2
            assert goal_storage.load_goal(tmp_path) is None
            history = goal_storage.load_goal_history(tmp_path)
            assert len(history) == 1
            assert history[0]["status"] == "complete"
            assert history[0]["active_elapsed_seconds"] == 62
            assert history[0]["turns"] == 2
            assert ctrl._acp_notifications == [
                ("context/goalState", {"goal": None, "verifying": False})
            ]
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(turn, session, tmp_path)
            assert len(goal_storage.load_goal_history(tmp_path)) == 1
            verify.assert_not_called()

    def test_blocked_goal_is_reactivated_on_new_input(self):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("ship it")
            goal.status = "blocked"
            goal.consecutive_failures = GOAL_MAX_TURNS
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
            goal.consecutive_failures = GOAL_MAX_TURNS
            goal.reminder_injected = True  # was already reminded before blocking
            fake_cache, context = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(turn, session, session_dir)

            assert goal.reminder_injected is False
            persisted = goal_storage.load_goal(session_dir)
            assert persisted.reminder_injected is False

    def test_blocked_goal_stays_blocked_on_internal_continuation(self):
        ctrl = _make_controller()
        turn = _make_turn()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create("stop automatically retrying")
            goal.status = "blocked"
            goal.consecutive_failures = GOAL_MAX_TURNS
            goal.reminder_injected = True
            goal_storage.save_goal(session_dir, goal)
            fake_cache, context = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(
                    turn, session, session_dir, user_initiated=False,
                )

            assert context.goal is goal
            assert goal.status == "blocked"
            assert goal.consecutive_failures == GOAL_MAX_TURNS
            assert goal.reminder_injected is True
            assert goal_storage.load_goal(session_dir).status == "blocked"
            assert ctrl._acp_notifications == []


class TestInterruptPausesGoal:
    """An interrupted turn must stop an active goal's elapsed clock.

    Before this, an interruption left ``status == "active"`` with
    ``active_started_at`` set, so ``Goal.elapsed_seconds()`` kept counting the
    idle gap (and the whole offline gap after quitting) even though nobody was
    working on the goal.
    """

    @staticmethod
    def _session_with_folder(tmp_path):
        session = _make_session()
        session.state = SimpleNamespace(
            openai_session=SimpleNamespace(session_folder=tmp_path),
            pending_goal=None,
            pending_goal_loaded=False,
        )
        return session

    @pytest.mark.asyncio
    @pytest.mark.parametrize("interrupt", [KeyboardInterrupt, asyncio.CancelledError])
    async def test_interrupted_turn_freezes_time_and_next_message_resumes_goal(self, tmp_path, interrupt):
        clock = {"now": "2026-01-01T00:00:00Z"}
        ctrl = _make_controller()
        session = self._session_with_folder(tmp_path)
        turn = Mock()
        turn.get_turn_type.return_value = TurnType.CONVERSATION
        turn.execute = AsyncMock(side_effect=interrupt())

        with patch(
            "siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]
        ):
            goal = Goal.create("finish the interrupted task")
            goal.consecutive_failures = 2
            goal.reminder_injected = True
            goal_storage.save_goal(tmp_path, goal)
            fake_cache, context = _context_cache_with("/ws", goal)
            clock["now"] = "2026-01-01T00:00:07.500Z"

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=False
            ), patch(
                "siada.services.plugins.hook_runner.set_active"
            ), patch(
                "siada.session.ownership.SessionOwnershipManager.owned_turn",
                _noop_owned_turn,
            ):
                with pytest.raises(interrupt):
                    await ctrl.execute(turn, "continue the goal", session)

            assert context.goal is goal
            assert goal.status == "paused"
            assert goal.elapsed_seconds() == 7.5
            persisted = goal_storage.load_goal(tmp_path)
            assert persisted.status == "paused"
            assert persisted.elapsed_seconds() == 7.5
            snapshot = ctrl._acp_notifications[-1][1]
            assert snapshot["goal"]["status"] == "paused"
            assert snapshot["goal"]["elapsedSeconds"] == 7.5
            assert snapshot["verifying"] is False
            assert snapshot["notice"] == "Goal paused — send a new message to resume."

            # The idle gap while interrupted is not counted. A user message
            # resumes the goal without resetting its failure budget.
            clock["now"] = "2026-01-01T01:00:00Z"
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                ctrl._maybe_reset_goal_on_new_turn(_make_turn(), session, tmp_path)
            assert goal.status == "active"
            assert goal.consecutive_failures == 2
            assert goal.reminder_injected is True
            assert ctrl._acp_notifications[-1][1]["goal"]["status"] == "active"
            clock["now"] = "2026-01-01T01:00:02.500Z"
            assert goal_storage.load_goal(tmp_path).elapsed_seconds() == 10.0

    @pytest.mark.asyncio
    async def test_end_session_freezes_active_goal_without_ui_notice(self, tmp_path):
        clock = {"now": "2026-01-01T00:00:00Z"}
        ctrl = _make_controller()
        session = self._session_with_folder(tmp_path)
        with patch(
            "siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]
        ):
            goal = Goal.create("freeze when the CLI exits")
            goal_storage.save_goal(tmp_path, goal)
            fake_cache, _ = _context_cache_with("/ws", goal)
            clock["now"] = "2026-01-01T00:00:04Z"
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                await ctrl.end_session(session, "normal")

            assert goal.status == "paused"
            assert goal_storage.load_goal(tmp_path).elapsed_seconds() == 4
            snapshot = ctrl._acp_notifications[-1][1]
            assert snapshot["goal"]["status"] == "paused"
            # Nothing to flash to a frontend that is shutting down.
            assert "notice" not in snapshot

    @pytest.mark.parametrize("status", ["blocked", "paused", "complete"])
    def test_only_active_goals_are_paused(self, tmp_path, status):
        ctrl = _make_controller()
        session = self._session_with_folder(tmp_path)
        goal = Goal.create("already stopped")
        goal.set_status(status)
        goal_storage.save_goal(tmp_path, goal)
        fake_cache, _ = _context_cache_with("/ws", goal)

        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            assert ctrl._pause_goal_on_interrupt(session, tmp_path) is False

        assert goal.status == status
        assert goal_storage.load_goal(tmp_path).status == status
        assert ctrl._acp_notifications == []

    def test_paused_goal_stays_paused_on_internal_continuation(self, tmp_path):
        ctrl = _make_controller()
        session = self._session_with_folder(tmp_path)
        goal = Goal.create("do not auto-resume")
        goal.set_status("paused")
        goal_storage.save_goal(tmp_path, goal)
        fake_cache, _ = _context_cache_with("/ws", goal)

        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            ctrl._maybe_reset_goal_on_new_turn(
                _make_turn(), session, tmp_path, user_initiated=False,
            )

        assert goal.status == "paused"
        assert goal_storage.load_goal(tmp_path).status == "paused"
        assert ctrl._acp_notifications == []


@contextmanager
def _noop_owned_turn(*_args, **_kwargs):
    """Skip on-disk session ownership bookkeeping in turn-level tests."""
    yield


