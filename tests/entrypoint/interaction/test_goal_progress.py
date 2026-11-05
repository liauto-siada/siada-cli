"""Goal notifications produce console progress without replaying old verdicts."""

from copy import deepcopy

import pytest

from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
from siada.entrypoint.interaction.goal_progress import publish_goal_progress
from siada.foundation.execution_progress import execution_progress_scope


def _present(params, method="context/goalState"):
    messages = []
    with ConsoleProgressPresenter(messages.append) as presenter:
        with execution_progress_scope(presenter.channel):
            publish_goal_progress(method, params)
    return messages


def _goal(status="active", turns=0):
    return {
        "objective": "Ship the synthetic goal", "status": status,
        "turns": turns, "elapsedSeconds": 65.9,
    }


@pytest.mark.parametrize("method, params", [
    ("unrelated/event", {"goal": _goal()}),
    ("context/goalState", {"goal": None, "verifying": False}),
    ("context/goalState", {}),
])
def test_ignores_unrelated_and_cleared_goal_snapshots(method, params):
    assert _present(params, method) == []


@pytest.mark.parametrize("status, turns, label", [
    ("active", 0, "Goal started"),
    ("active", 2, "Goal continuing"),
    ("paused", 2, "Goal paused"),
    ("blocked", 2, "Goal blocked"),
    ("complete", 2, "Goal complete"),
])
def test_goal_state_labels_include_objective_rounds_and_elapsed(status, turns, label):
    assert _present({"goal": _goal(status, turns), "verifying": False}) == [
        f"[{label}] Ship the synthetic goal (rounds: {turns}, elapsed: 65s)"
    ]


def test_verifier_start_does_not_replay_latest_result():
    messages = _present({
        "goal": _goal(turns=3), "verifying": True,
        "latestResult": {"achieved": False, "reason": "Historical feedback"},
    })
    assert messages == ["[Goal verifying] Ship the synthetic goal (rounds: 3, elapsed: 65s)"]


@pytest.mark.parametrize("status, achieved, outcome, label", [
    ("complete", True, "achieved", "Goal achieved"),
    ("active", False, "not_achieved", "Goal not achieved"),
    ("active", False, "system_error", "Goal verification error"),
    ("blocked", False, "blocked", "Goal blocked"),
    ("blocked", False, "system_error", "Goal blocked"),
])
def test_live_verdicts_include_statistics_feedback_and_notices(status, achieved, outcome, label):
    params = {
        "goal": _goal(status, turns=2), "verifying": False,
        "notice": "Synthetic lifecycle notice",
        "result": {
            "achieved": achieved, "outcome": outcome, "turns": 2,
            "elapsedSeconds": 125.9, "tokensUsed": 12345,
            "reason": "Synthetic verifier feedback", "nextAction": "Synthetic next action",
        },
    }
    original = deepcopy(params)

    assert _present(params) == [
        f"[{label}] Ship the synthetic goal (rounds: 2, elapsed: 125s, tokens: 12,345)\n"
        "Reason: Synthetic verifier feedback\n"
        "Next action: Synthetic next action\n"
        "Notice: Synthetic lifecycle notice"
    ]
    assert params == original


def test_progress_has_no_console_side_effects_without_an_owner(capsys):
    publish_goal_progress("context/goalState", {"goal": _goal(), "verifying": True})
    assert capsys.readouterr().out == ""


def test_default_presenter_prints_goal_events_to_stdout(capsys):
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            publish_goal_progress("context/goalState", {"goal": _goal(), "verifying": False})

    captured = capsys.readouterr()
    assert captured.out == "[Goal started] Ship the synthetic goal (rounds: 0, elapsed: 65s)\n"
    assert captured.err == ""


def test_empty_verdict_feedback_is_omitted_and_zero_tokens_are_kept():
    messages = _present({
        "goal": _goal("complete", 1),
        "result": {"achieved": True, "tokensUsed": 0, "reason": "", "nextAction": ""},
    })
    assert messages == ["[Goal achieved] Ship the synthetic goal (rounds: 1, elapsed: 65s, tokens: 0)"]