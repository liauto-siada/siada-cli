"""
Tests for the /goal completion-notification truncation logic in
``siada.services.goal.turn_hooks``.

OS-level notification APIs (e.g. macOS's osascript "display notification")
have length limits, and ``goal.objective`` is free-form user text that can
be arbitrarily long -- it must be capped before being embedded in the
notification message.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.turn.models import TurnOutput, TurnType
from siada.services.goal.models import Goal, GoalVerdict, GOAL_MAX_CONSECUTIVE_FAILURES
from siada.services.goal.turn_hooks import (
    _NOTIFICATION_OBJECTIVE_MAX_LEN,
    _truncate_for_notification,
)


class TestTruncateForNotification:
    def test_short_text_unchanged(self):
        assert _truncate_for_notification("ship it") == "ship it"

    def test_empty_text_unchanged(self):
        assert _truncate_for_notification("") == ""
        assert _truncate_for_notification(None) is None

    def test_text_exactly_at_limit_unchanged(self):
        text = "a" * _NOTIFICATION_OBJECTIVE_MAX_LEN
        assert _truncate_for_notification(text) == text

    def test_long_text_is_truncated_with_ellipsis(self):
        text = "a" * 200
        result = _truncate_for_notification(text)
        assert len(result) == _NOTIFICATION_OBJECTIVE_MAX_LEN
        assert result.endswith("…")

    def test_custom_max_len(self):
        text = "abcdefghij"
        result = _truncate_for_notification(text, max_len=5)
        assert result == "abcd…"


def _make_controller():
    ctrl = Controller.__new__(Controller)
    ctrl.config = SimpleNamespace(acp_mode=False, io=SimpleNamespace(acp_adapter=None))
    ctrl._acp_notifications = []
    ctrl.config.enable_notification = True

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


class TestNotificationMessageTruncatesLongObjective:
    def test_achieved_notification_truncates_long_objective(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        long_objective = "ship the entire feature end to end " * 10  # very long
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create(long_objective)
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=True, reason="all good")),
            ), patch("siada.notifications.show_completion_notification") as mock_notify:
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            mock_notify.assert_called_once()
            sent_message = mock_notify.call_args.kwargs.get("message", "")
            # The prefix "Goal reached: " plus the truncated objective must
            # stay well under the raw (very long) objective's length.
            assert len(sent_message) < len(long_objective)
            assert sent_message.startswith("Goal reached: ")

    def test_blocked_notification_truncates_long_objective(self, base_result):
        ctrl = _make_controller()
        turn = _make_turn()
        long_objective = "figure out this very ambiguous and long-winded goal " * 5
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session()
            goal = Goal.create(long_objective)
            goal.consecutive_failures = GOAL_MAX_CONSECUTIVE_FAILURES - 1
            fake_cache, _ = _context_cache_with("/ws", goal)

            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache), patch(
                "siada.services.goal.verifier.run_goal_verification",
                new=AsyncMock(return_value=GoalVerdict(passed=False, reason="still unclear")),
            ), patch("siada.notifications.show_completion_notification") as mock_notify:
                ctrl._maybe_run_goal_verifier(turn, session, session_dir, base_result)

            assert goal.status == "blocked"
            mock_notify.assert_called_once()
            sent_message = mock_notify.call_args.kwargs.get("message", "")
            assert len(sent_message) < len(long_objective)
            assert sent_message.startswith("Goal paused: ")
