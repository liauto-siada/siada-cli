"""
Tests for TurnPolicy._maybe_retry_turn.

This is the TurnPolicy-layer half of the generic auto-retry mechanism:
ConversationTurn.execute() (or any future detector) only detects a
retry-worthy condition and tags the turn's result with a generic
``retry_reason`` string on ``TurnOutput.metadata`` (see
siada.entrypoint.interaction.turn.models.RETRY_REASON_METADATA_KEY /
RETRY_REASON_TRUNCATED_REASONING_ONLY, and
ConversationTurn._is_truncated_reasoning_only_completion's dedicated tests
for the first, and so far only, consumer: the Chat Completions/LiteLLM
truncated-stream guard).

The actual retry here reuses the exact same SwitchEvent
(ai_analysis_prompt=...) -> pending_input -> the controller's run loop
`continue` mechanism /goal uses for its own auto-retry loop -- it does NOT
call turn.execute() again itself. Bounded to a small number of consecutive
attempts, and placed BEFORE the result is ever handed to
TurnPolicy._maybe_run_goal_verifier.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Import turn_policy first: it pulls in siada.session before turn.models
# touches siada.support.slash_commands, avoiding a circular import
# (checkpoint_tracker <-> session_manager) that the old controller import
# used to mask.
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.entrypoint.interaction.turn.models import (
    TurnOutput,
    TurnType,
    RETRY_REASON_METADATA_KEY,
    RETRY_REASON_TRUNCATED_REASONING_ONLY,
    RETRY_NOTICES,
)
from siada.support.slash_commands import SwitchEvent


def _make_controller():
    return TurnPolicy(
        config=SimpleNamespace(),
        slash_commands=SimpleNamespace(),
        send_notification=None,
    )


def _output(reason: str | None, text: str = ""):
    metadata = {}
    if reason is not None:
        metadata[RETRY_REASON_METADATA_KEY] = reason
    return TurnOutput(output=text, metadata=metadata, next_action=None)


def _flagged():
    return _output(RETRY_REASON_TRUNCATED_REASONING_ONLY)


class TestMaybeRetryTurn:
    def test_retry_notice_is_hidden_from_resumed_history(self):
        """Every registered retry notice must be recognized by
        message_classifier._is_whole_system_reminder as a whole
        <system-reminder> block, so it gets stripped out of what the
        frontend replays on session resume/pullHistory -- the user must
        never see this internal nudge as if they had typed it."""
        from siada.support.message_classifier import _is_whole_system_reminder

        for notice in RETRY_NOTICES.values():
            assert _is_whole_system_reminder(notice)

    def test_returns_none_unchanged(self):
        controller = _make_controller()
        assert controller._maybe_retry_turn(None) is None

    def test_passthrough_when_no_reason(self):
        controller = _make_controller()
        result = _output(None, "a real answer")
        out = controller._maybe_retry_turn(result)
        assert out is result

    def test_passthrough_when_reason_unrecognized(self):
        controller = _make_controller()
        result = _output("some_future_reason_not_yet_registered", "text")
        out = controller._maybe_retry_turn(result)
        assert out is result

    def test_resets_streak_on_healthy_turn(self):
        controller = _make_controller()
        controller._auto_retry_count = 2
        result = _output(None, "a real answer")
        controller._maybe_retry_turn(result)
        assert controller._auto_retry_count == 0

    def test_returns_switch_event_when_flagged(self):
        """Flagged result must become a SwitchEvent(ai_analysis_prompt=...)
        TurnOutput -- the exact same shape /goal returns from
        maybe_run_goal_verifier -- so Controller.run()'s existing
        SwitchEvent handling drives the retry via pending_input, instead of
        this method calling turn.execute() itself."""
        controller = _make_controller()
        flagged = _flagged()

        out = controller._maybe_retry_turn(flagged)

        assert isinstance(out.output, SwitchEvent)
        notice = RETRY_NOTICES[RETRY_REASON_TRUNCATED_REASONING_ONLY]
        assert out.output.kwargs.get("ai_analysis_prompt") == notice
        assert controller._auto_retry_count == 1

    def test_increments_streak_across_consecutive_flagged_turns(self):
        controller = _make_controller()
        flagged = _flagged()

        for expected in range(1, controller._MAX_AUTO_RETRIES + 1):
            out = controller._maybe_retry_turn(flagged)
            assert isinstance(out.output, SwitchEvent)
            assert controller._auto_retry_count == expected

    def test_gives_up_and_passes_through_after_max_retries(self):
        controller = _make_controller()
        controller._auto_retry_count = controller._MAX_AUTO_RETRIES
        flagged = _flagged()

        out = controller._maybe_retry_turn(flagged)

        # Exhausted -- surfaces the (still-flagged) result as-is rather than
        # yet another SwitchEvent, and resets the streak.
        assert out is flagged
        assert controller._auto_retry_count == 0

    def test_streak_resets_after_giving_up_then_resolves_normally(self):
        controller = _make_controller()
        controller._auto_retry_count = controller._MAX_AUTO_RETRIES
        flagged = _flagged()
        controller._maybe_retry_turn(flagged)
        assert controller._auto_retry_count == 0

        # A subsequent healthy turn keeps the streak at 0.
        healthy = _output(None, "ok now")
        out = controller._maybe_retry_turn(healthy)
        assert out is healthy
        assert controller._auto_retry_count == 0


def _make_full_controller():
    """A TurnPolicy with just enough real state for execute() to run without
    touching disk/ACP/hooks: slash_commands has no ``hook_runner`` attribute,
    so every PreTurn/UserPromptSubmit/Stop/PostTurn hook call is skipped (see
    ``getattr(self.slash_commands, "hook_runner", None)``)."""
    return TurnPolicy(
        config=SimpleNamespace(acp_mode=False, io=SimpleNamespace(acp_adapter=None)),
        slash_commands=SimpleNamespace(),
        send_notification=None,
    )


def _make_turn_mock(execute_result):
    turn = Mock()
    turn.get_turn_type.return_value = TurnType.CONVERSATION
    turn.execute.return_value = execute_result
    return turn


class TestExecuteTurnWithOwnershipDoesNotInterfereWithGoalVerifier:
    """Integration-style tests for the interaction between
    TurnPolicy._maybe_retry_turn and TurnPolicy._maybe_run_goal_verifier
    inside TurnPolicy.execute (migrated from the controller's
    _execute_turn_with_ownership).

    The goal verifier reads the actual conversation history from disk and
    updates goal.turns/consecutive_failures as a side effect -- it must
    NEVER run against a fake/interrupted "reasoning-only" completion, or a
    truncated stream would get silently counted as a real (failed) attempt
    at the objective, and its own SwitchEvent would clobber our retry
    notice.
    """

    def test_goal_verifier_skipped_when_retry_is_triggered(self):
        controller = _make_full_controller()
        flagged = _flagged()
        turn = _make_turn_mock(flagged)
        session = SimpleNamespace()  # no .state -> _get_session_dir() returns None safely

        with patch.object(TurnPolicy, "_maybe_run_goal_verifier") as mock_verifier, \
             patch("siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=False):
            out = controller.execute(turn, "hello", session)

        mock_verifier.assert_not_called()
        assert isinstance(out.output, SwitchEvent)
        notice = RETRY_NOTICES[RETRY_REASON_TRUNCATED_REASONING_ONLY]
        assert out.output.kwargs.get("ai_analysis_prompt") == notice

    def test_goal_verifier_still_runs_for_a_healthy_turn(self):
        controller = _make_full_controller()
        healthy = _output(None, "a real answer")
        turn = _make_turn_mock(healthy)
        session = SimpleNamespace()

        with patch.object(
            TurnPolicy, "_maybe_run_goal_verifier", return_value=healthy
        ) as mock_verifier, patch(
            "siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=False
        ):
            out = controller.execute(turn, "hello", session)

        mock_verifier.assert_called_once()
        assert out is healthy

    def test_goal_verifier_still_runs_once_retries_are_exhausted(self):
        """After _MAX_AUTO_RETRIES consecutive fake completions,
        _maybe_retry_turn gives up and passes the (still-flagged) result
        through unchanged -- at that point it SHOULD reach the goal
        verifier like a normal turn (the automatic retry budget has been
        exhausted, so ordinary failure-handling takes over)."""
        controller = _make_full_controller()
        controller._auto_retry_count = controller._MAX_AUTO_RETRIES
        flagged = _flagged()
        turn = _make_turn_mock(flagged)
        session = SimpleNamespace()

        with patch.object(
            TurnPolicy, "_maybe_run_goal_verifier", return_value=flagged
        ) as mock_verifier, patch(
            "siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=False
        ):
            out = controller.execute(turn, "hello", session)

        mock_verifier.assert_called_once()
        assert out is flagged
