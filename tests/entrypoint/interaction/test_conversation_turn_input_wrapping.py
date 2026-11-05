"""Input envelopes distinguish human turns from internal continuations."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import RETRY_NOTICES, TurnInput
from siada.support.message_classifier import format_native_items_for_display


@pytest.mark.parametrize("text,expected,visible", [
    ("continue the task", "<user_input>continue the task</user_input>", True),
    (
        "Please explain <system-reminder>retry</system-reminder>",
        "<user_input>Please explain <system-reminder>retry</system-reminder></user_input>",
        True,
    ),
    (
        "<system-reminder>Completion verifier result: not passed.</system-reminder>",
        "<system-reminder>Completion verifier result: not passed.</system-reminder>",
        False,
    ),
    *[(notice, notice, False) for notice in RETRY_NOTICES.values()],
])
def test_execute_wraps_human_input_but_not_internal_continuations(
    monkeypatch, text, expected, visible,
):
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        agent_name="input-wrapping-test",
        acp_mode=False,
        enable_notification=False,
        io=SimpleNamespace(_pending_image_paths=None),
    )
    turn.session = SimpleNamespace(state=SimpleNamespace(pending_memory_task=None))
    turn.current_result = None
    turn._stop_waiting_spinner = Mock()
    turn._save_session_memory_if_needed = AsyncMock()
    turn._run_stream_with_recovery = AsyncMock(
        return_value=SimpleNamespace(final_output="done", new_items=[]),
    )
    turn.handle_error = Mock(side_effect=AssertionError("Unexpected turn failure"))
    output = asyncio.run(turn.execute(TurnInput(use_input=text)))

    assert output.output == "done"
    turn.handle_error.assert_not_called()
    turn._run_stream_with_recovery.assert_awaited_once_with(expected)
    displayed = format_native_items_for_display([{"role": "user", "content": expected}])
    assert displayed == ([{"role": "user", "content": text}] if visible else [])