"""Tests for SiadaRunner._maybe_merge_goal_reminder.

The reminder must be merged into the turn's input exactly ONCE per goal
activation, not on every turn -- since (unlike the old ephemeral
per-LLM-call GoalReminderFilter) the merged reminder now becomes part of
the real, persisted turn input and gets written to api_history.json by the
SDK's own session bookkeeping. Re-merging every turn would keep appending
the same multi-paragraph block into persisted history forever.
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from siada.services.goal.models import Goal
from siada.services.goal import goal_storage
from siada.services.siada_runner import SiadaRunner


def _make_context(goal=None, session_dir: Path | None = None):
    context = MagicMock()
    context.goal = goal
    if session_dir is not None:
        context.session.state.openai_session.session_folder = session_dir
    else:
        context.session = None
    return context


def test_no_merge_when_no_goal():
    context = _make_context(goal=None)
    result = SiadaRunner._maybe_merge_goal_reminder(context, "hello")
    assert result == "hello"


def test_no_merge_when_goal_not_active():
    goal = Goal.create("ship it")
    goal.status = "paused"
    context = _make_context(goal=goal)
    result = SiadaRunner._maybe_merge_goal_reminder(context, "hello")
    assert result == "hello"


def test_merges_once_on_first_active_turn():
    goal = Goal.create("ship it")
    context = _make_context(goal=goal)
    result = SiadaRunner._maybe_merge_goal_reminder(context, "hello")

    assert isinstance(result, list)
    assert "<system-reminder>" in result[0]["content"][1]["text"]
    assert goal.reminder_injected is True


def test_does_not_merge_again_on_subsequent_turns():
    """Core regression: once reminder_injected is True, later turns while
    the SAME goal stays active must NOT get another reminder merged in --
    otherwise every ordinary follow-up message would keep appending the
    same big block into persisted history."""
    goal = Goal.create("ship it")
    context = _make_context(goal=goal)

    first = SiadaRunner._maybe_merge_goal_reminder(context, "first message")
    assert isinstance(first, list)  # merged

    second = SiadaRunner._maybe_merge_goal_reminder(context, "second message")
    assert second == "second message"  # untouched, no reminder appended

    third = SiadaRunner._maybe_merge_goal_reminder(context, "third message")
    assert third == "third message"


def test_persists_reminder_injected_flag_to_goal_json():
    goal = Goal.create("ship it")
    with tempfile.TemporaryDirectory() as d:
        session_dir = Path(d)
        goal_storage.save_goal(session_dir, goal)  # pre-existing goal.json
        context = _make_context(goal=goal, session_dir=session_dir)

        SiadaRunner._maybe_merge_goal_reminder(context, "hello")

        reloaded = goal_storage.load_goal(session_dir)
        assert reloaded is not None
        assert reloaded.reminder_injected is True


def test_merge_survives_when_no_session_available():
    """Defensive: helper must not blow up when context.session is None
    (e.g. lightweight test/mocked contexts) -- persistence is best-effort."""
    goal = Goal.create("ship it")
    context = _make_context(goal=goal, session_dir=None)
    result = SiadaRunner._maybe_merge_goal_reminder(context, "hello")
    assert isinstance(result, list)
    assert goal.reminder_injected is True
