from datetime import datetime
from unittest.mock import patch

import pytest

from siada.services.goal.models import (
    Goal,
    GoalVerdict,
    GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
    GOAL_MAX_TURNS,
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


def test_goal_max_turns_is_positive():
    assert GOAL_MAX_TURNS > 0


def test_goal_max_consecutive_system_errors_is_positive_and_much_smaller():
    """A system/infra error tells us nothing about whether the objective
    was reached, so it must trip a much smaller budget than the generous
    one reserved for genuine "not yet achieved" judgments -- otherwise a
    broken verifier call would silently retry just as many times as a
    legitimately multi-round task."""
    assert GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS > 0
    assert GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS < GOAL_MAX_TURNS


def test_goal_consecutive_system_errors_survives_serialization_round_trip():
    goal = Goal.create("ship the feature")
    goal.consecutive_system_errors = 2
    dumped = goal.model_dump_json()
    restored = Goal.model_validate_json(dumped)
    assert restored.consecutive_system_errors == 2


@pytest.mark.parametrize("status", ["blocked", "paused", "complete"])
def test_elapsed_time_freezes_and_resumes_without_counting_stopped_time(status):
    clock = {"now": "2026-01-01T00:00:00Z"}
    with patch("siada.services.goal.models._now_iso", side_effect=lambda: clock["now"]):
        goal = Goal.create("verify active duration")
        clock["now"] = "2026-01-01T00:00:02.250Z"
        goal.set_status(status)
        clock["now"] = "2026-01-01T00:01:00Z"
        goal.touch()
        assert goal.elapsed_seconds() == 2.25
        restored = Goal.model_validate_json(goal.model_dump_json())
        assert restored.elapsed_seconds() == 2.25

        restored.set_status("active")
        clock["now"] = "2026-01-01T00:01:00.750Z"
        assert restored.elapsed_seconds() == 3
        restored.set_status("blocked")
        clock["now"] = "2026-01-01T00:02:00Z"
        restored.set_status("blocked")
        assert restored.elapsed_seconds() == 3


@pytest.mark.parametrize("status", ["active", "blocked", "paused", "complete"])
def test_legacy_goal_timing_uses_creation_and_last_update(status):
    with patch("siada.services.goal.models._now_iso", return_value="2026-01-01T00:01:00Z"):
        goal = Goal.model_validate({
            "objective": "restore legacy progress", "status": status,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:10Z",
        })
        assert goal.elapsed_seconds() == (60 if status == "active" else 10)


def test_elapsed_time_handles_invalid_and_future_timestamps():
    with patch("siada.services.goal.models._now_iso", return_value="2026-01-01T00:00:00Z"):
        invalid = Goal(objective="invalid legacy timestamp", created_at="invalid")
        future = Goal(objective="future timestamp", created_at="2026-01-01T00:00:01Z")
        assert invalid.elapsed_seconds() == 0
        assert future.elapsed_seconds() == 0
