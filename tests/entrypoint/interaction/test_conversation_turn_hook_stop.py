"""Hook stops terminate cleanly without manufacturing a model completion."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents.exceptions import (
    ToolInputGuardrailTripwireTriggered,
    ToolOutputGuardrailTripwireTriggered,
)
from agents.tool_guardrails import ToolGuardrailFunctionOutput

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import TurnInput


@pytest.mark.asyncio
@pytest.mark.parametrize("render_stream", [False, True])
@pytest.mark.parametrize("exception_type,event", [
    (ToolInputGuardrailTripwireTriggered, "PreToolUse"),
    (ToolOutputGuardrailTripwireTriggered, "PostToolUse"),
])
async def test_hook_stop_returns_none_and_next_turn_can_complete(
    render_stream, exception_type, event,
):
    io = SimpleNamespace(
        _pending_image_paths=None, print_hook=Mock(), print_error=Mock(),
        acp_adapter=Mock(),
    )
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.render_stream = render_stream
    turn.config = SimpleNamespace(
        agent_name="synthetic", acp_mode=True, enable_notification=False, io=io,
    )
    turn.session = SimpleNamespace(state=SimpleNamespace(pending_memory_task=None))
    turn.current_result = None
    turn.output_data = SimpleNamespace(output="previous turn")
    turn._stop_waiting_spinner = Mock()
    turn._save_session_memory_if_needed = AsyncMock()
    reason = "Synthetic hook stop"
    stopped = ToolGuardrailFunctionOutput.raise_exception(output_info=reason)
    turn._run_stream_with_recovery = AsyncMock(side_effect=exception_type(None, stopped))
    turn.handle_error = Mock(side_effect=AssertionError("Hook stop must not be an error"))

    assert await turn.execute(TurnInput(use_input="synthetic stop request")) is None
    assert turn.output_data is None
    assert turn.current_result is None
    assert turn.error is None
    assert turn.end_time is not None
    io.print_hook.assert_called_once_with(reason, event, status="stopped")
    io.print_error.assert_not_called()
    turn.handle_error.assert_not_called()
    turn._save_session_memory_if_needed.assert_not_awaited()
    turn._stop_waiting_spinner.assert_called_once()
    if render_stream:
        io.acp_adapter._send_if_acp_robust.assert_called_once()
        notification = io.acp_adapter._send_if_acp_robust.call_args.args[0]()
        assert notification.params["reason"] == "input_ready"

    turn._run_stream_with_recovery.side_effect = None
    turn._run_stream_with_recovery.return_value = SimpleNamespace(
        final_output="fresh answer", new_items=[],
    )
    result = await turn.execute(TurnInput(use_input="synthetic next request"))
    assert result.output == "fresh answer"
    assert turn.output_data is result
    assert turn.error is None
    if turn.session.state.pending_memory_task is not None:
        await turn.session.state.pending_memory_task