"""
Tests for ConversationTurn.handle_interrupt restoring unpersisted user input
back to the ACP input box when Ctrl+C lands before the SDK has persisted the
input to the session (api_history.json).

Behavior contract:
- Input NOT in session history  -> emit ``restore_input`` session update so
  the frontend puts the text back into the input box; do NOT append the
  "interrupted by user" note (the turn left no trace in history).
- Input already persisted        -> keep the existing behavior (append the
  interrupt note when the tail item calls for it); never emit restore_input.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn


def _make_turn(*, user_input="fix the bug", history=None, acp_mode=True):
    """Build a minimal ConversationTurn wired with fake session/io.

    Returns (turn, sent_messages): ``sent_messages`` collects every ACP
    message handed to the fake adapter's ``_send_if_acp_robust``.
    """
    turn = ConversationTurn.__new__(ConversationTurn)

    sent_messages = []

    class _FakeAdapter:
        def _send_if_acp_robust(self, message_func, *_args, **_kwargs):
            sent_messages.append(message_func())

    turn.config = SimpleNamespace(
        acp_mode=acp_mode,
        io=SimpleNamespace(acp_adapter=_FakeAdapter()),
    )
    turn.session = SimpleNamespace(
        openai_session=SimpleNamespace(
            get_items=AsyncMock(return_value=list(history or [])),
            add_items=AsyncMock(),
        )
    )
    turn.input_data = SimpleNamespace(use_input=user_input)
    return turn, sent_messages


def _restore_notifications(sent_messages):
    return [
        m for m in sent_messages
        if getattr(m, "params", {}).get("reason") == "restore_input"
    ]


class TestRestoreUnpersistedInput:
    """Ctrl+C before persistence restores the input to the input box."""

    @pytest.mark.asyncio
    async def test_restore_when_history_has_no_matching_input(self):
        turn, sent = _make_turn(
            user_input="fix the bug",
            history=[{"role": "user", "content": "earlier question"}],
        )
        await turn.handle_interrupt()

        notifications = _restore_notifications(sent)
        assert len(notifications) == 1
        assert notifications[0].params["content"] == "fix the bug"
        # No interrupt note: the turn left no trace in history.
        turn.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_with_empty_history(self):
        """First-turn Ctrl+C before persistence: history is empty."""
        turn, sent = _make_turn(user_input="fix the bug", history=[])
        await turn.handle_interrupt()

        notifications = _restore_notifications(sent)
        assert len(notifications) == 1
        assert notifications[0].params["content"] == "fix the bug"
        turn.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_restore_when_input_persisted(self):
        turn, sent = _make_turn(
            user_input="fix the bug",
            history=[{"role": "user", "content": "fix the bug"}],
        )
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        # Existing behavior: interrupt note appended after the user message.
        turn.session.openai_session.add_items.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_restore_when_input_embedded_in_goal_reminder(self):
        """Goal reminder merged into the persisted input must still count as
        persisted (the persisted text contains the raw user input)."""
        turn, sent = _make_turn(
            user_input="fix the bug",
            history=[{
                "role": "user",
                "content": (
                    "fix the bug\n\n"
                    "<goal-reminder>keep working on the goal</goal-reminder>"
                ),
            }],
        )
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        turn.session.openai_session.add_items.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_restore_when_persisted_input_behind_tool_items(self):
        """Input persisted, then tool items followed — scanning must look past
        non-user tail items to find the matching user message."""
        turn, sent = _make_turn(
            user_input="fix the bug",
            history=[
                {"role": "user", "content": "fix the bug"},
                {"type": "function_call", "name": "run_cmd", "call_id": "c1"},
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "ok",
                },
            ],
        )
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        # Tail is a tool output -> existing behavior appends the note.
        turn.session.openai_session.add_items.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_restore_when_not_acp_mode(self):
        """Non-ACP mode has no frontend input box to restore into."""
        turn, sent = _make_turn(
            user_input="fix the bug",
            # Tail item matches none of the interrupt-note conditions, so the
            # existing logic stays silent too — isolates the restore channel.
            history=[{"type": "reasoning", "summary": []}],
            acp_mode=False,
        )
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        turn.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_restore_when_input_empty(self):
        turn, sent = _make_turn(user_input="", history=[])
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        turn.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_restore_when_input_data_missing(self):
        turn, sent = _make_turn(user_input="fix the bug", history=[])
        turn.input_data = None
        await turn.handle_interrupt()

        assert _restore_notifications(sent) == []
        turn.session.openai_session.add_items.assert_not_called()


class TestHandleInterruptRestoreOutcome:
    """handle_interrupt honours the early-restore outcome from execute().

    execute()'s KeyboardInterrupt handler runs the restore check BEFORE the
    dedicated-loop cleanup wait (so a frozen loop can't delay the restore),
    then forwards the outcome:

    - input_restored=True  -> input was handed back; skip everything
    - input_restored=False -> persistence already confirmed; go straight to
      the interrupt-note logic without re-running the restore check
    - input_restored=None  -> early check never ran (error path); full logic
    """

    @pytest.mark.asyncio
    async def test_input_restored_true_skips_note_and_notification(self):
        turn, sent = _make_turn(
            user_input="fix the bug",
            history=[{"role": "user", "content": "fix the bug"}],
        )
        await turn.handle_interrupt(input_restored=True)

        assert _restore_notifications(sent) == []
        turn.session.openai_session.add_items.assert_not_called()

    @pytest.mark.asyncio
    async def test_input_restored_false_skips_restore_check(self):
        """Already-confirmed-persisted: no restore notification even though
        the (stale, pre-cleanup) history the early check saw is re-read here;
        the note logic decides solely from the tail item type."""
        turn, sent = _make_turn(
            user_input="brand new input",
            history=[{"role": "user", "content": "brand new input"}],
        )
        await turn.handle_interrupt(input_restored=False)

        assert _restore_notifications(sent) == []
        # Tail is the persisted user message -> interrupt note appended.
        turn.session.openai_session.add_items.assert_called_once()
