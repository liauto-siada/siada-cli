from datetime import datetime

from siada.services.goal.models import (
    Goal,
    GoalVerdict,
    GOAL_MAX_CONSECUTIVE_FAILURES,
    GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
)


def test_goal_create_defaults():
    goal = Goal.create("ship the feature")
    assert goal.objective == "ship the feature"
    assert goal.status == "active"
    assert goal.consecutive_failures == 0
    assert goal.consecutive_system_errors == 0
    assert goal.created_at == goal.updated_at
    # created_at/updated_at must be valid ISO-8601
    datetime.fromisoformat(goal.created_at.replace("Z", "+00:00"))


def test_goal_touch_updates_timestamp_only():
    goal = Goal.create("ship the feature")
    created = goal.created_at
    goal.consecutive_failures = 3
    goal.touch()
    assert goal.created_at == created
    assert goal.consecutive_failures == 3
    # touch() must produce a valid ISO-8601 timestamp
    datetime.fromisoformat(goal.updated_at.replace("Z", "+00:00"))


def test_goal_serialization_round_trip():
    goal = Goal.create("ship the feature")
    goal.consecutive_failures = 2
    goal.status = "paused"
    dumped = goal.model_dump_json()
    restored = Goal.model_validate_json(dumped)
    assert restored == goal


def test_goal_verdict_defaults():
    verdict = GoalVerdict(passed=False, reason="not yet")
    assert verdict.nextAction == ""
    # systemError is a purely code-level classification set only by
    # verifier.py's exception handlers -- never true by default, and never
    # something the LLM itself reports (see GoalVerdict.systemError docstring).
    assert verdict.systemError is False


def test_goal_verdict_system_error_can_be_set_explicitly():
    verdict = GoalVerdict(passed=False, reason="crashed", systemError=True)
    assert verdict.systemError is True


def test_goal_max_consecutive_failures_is_positive():
    assert GOAL_MAX_CONSECUTIVE_FAILURES > 0


def test_goal_max_consecutive_system_errors_is_positive_and_much_smaller():
    """A system/infra error tells us nothing about whether the objective
    was reached, so it must trip a much smaller budget than the generous
    one reserved for genuine "not yet achieved" judgments -- otherwise a
    broken verifier call would silently retry just as many times as a
    legitimately multi-round task."""
    assert GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS > 0
    assert GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS < GOAL_MAX_CONSECUTIVE_FAILURES


def test_goal_consecutive_system_errors_survives_serialization_round_trip():
    goal = Goal.create("ship the feature")
    goal.consecutive_system_errors = 2
    dumped = goal.model_dump_json()
    restored = Goal.model_validate_json(dumped)
    assert restored.consecutive_system_errors == 2
