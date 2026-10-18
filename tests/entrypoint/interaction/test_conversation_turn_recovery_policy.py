"""Recovery budgets, admission failures, and cancellation stay bounded."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from agents.exceptions import ModelBehaviorError

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.provider.retry import MissingFinalResponseError
from siada.services.siada_runner import SiadaRunner


def make_turn(history):
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        agent_name="synthetic", workspace=".", io=SimpleNamespace(print_warning=Mock()),
    )
    turn.session = SimpleNamespace(openai_session=SimpleNamespace(
        get_items=AsyncMock(side_effect=history),
    ))
    turn._result_ready = threading.Event()
    turn._current_message_id = "old-message"
    turn._stream_start_id = "old-stream"
    turn.got_content_part = True
    turn.got_function_call_part = False
    turn._emit_message_end = Mock()
    return turn


def missing():
    return MissingFinalResponseError(
        model="synthetic", response_id="resp-test",
        last_event="response.output_text.delta", output_exposed=True,
    )


def test_continuation_notice_is_hidden_from_resumed_user_history():
    from siada.support.message_classifier import _is_whole_system_reminder

    assert _is_whole_system_reminder(ConversationTurn._STREAM_RECOVERY_INPUT)


@pytest.mark.asyncio
@pytest.mark.parametrize("history", [
    [],
    [{"role": "user", "content": "rewritten task"}],
])
async def test_history_rewrite_preserves_original_error_without_replay(history, monkeypatch):
    turn = make_turn([[{"role": "user", "content": "earlier task"}], history])
    error = missing()
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    turn.output_stream_content = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        await turn._run_stream_with_recovery("original task")
    assert caught.value is error
    assert run.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("original,history", [
    (["unsupported item"], []),
    ("task", ["unsupported history item"]),
])
async def test_unsupported_shapes_preserve_original_error(original, history, monkeypatch):
    turn = make_turn([[], history])
    error = missing()
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    turn.output_stream_content = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        await turn._run_stream_with_recovery(original)
    assert caught.value is error
    assert run.await_count == 1


@pytest.mark.asyncio
async def test_message_and_text_metadata_do_not_cause_input_replay(monkeypatch):
    turn = make_turn([[], [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "task", "annotations": []},
    ]}]])
    final = SimpleNamespace(final_output="ok")
    run = AsyncMock(side_effect=[httpx.ConnectError("interrupted"), final])
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    turn.output_stream_content = AsyncMock()
    assert await turn._run_stream_with_recovery("task") is final
    assert run.await_args.kwargs["user_input"] == turn._STREAM_RECOVERY_INPUT


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [missing(), httpx.ReadTimeout("interrupted")])
async def test_exhaustion_preserves_last_error_and_durable_input(error, monkeypatch):
    turn = make_turn([[], [{"role": "user", "content": "task"}],
                      [{"role": "user", "content": "task"}]])
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    turn.output_stream_content = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        await turn._run_stream_with_recovery("task")
    assert caught.value is error
    assert run.await_count == 3
    assert [call.kwargs["user_input"] for call in run.await_args_list] == [
        "task", turn._STREAM_RECOVERY_INPUT, turn._STREAM_RECOVERY_INPUT,
    ]
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2]
    assert turn._stream_start_id is None
    turn._emit_message_end.assert_called_with("answer")


@pytest.mark.asyncio
async def test_setup_failure_before_admission_reuses_original_multimodal_input(monkeypatch):
    old = [{"role": "user", "content": "earlier task"}]
    turn = make_turn([old, old])
    final = SimpleNamespace(final_output="ok")
    run = AsyncMock(side_effect=[httpx.ConnectError("setup failed"), final])
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    turn.output_stream_content = AsyncMock()
    original = [{"role": "user", "content": [{"type": "input_text", "text": "task"}]}]
    assert await turn._run_stream_with_recovery(original) is final
    assert all(call.kwargs["user_input"] is original for call in run.await_args_list)
    assert turn.current_result is final
    assert turn._result_ready.is_set()


@pytest.mark.asyncio
async def test_background_notice_does_not_count_as_original_input_admission(monkeypatch):
    turn = make_turn([[], [{"role": "system", "content": "background task completed"}]])
    final = SimpleNamespace(final_output="ok")
    run = AsyncMock(side_effect=[httpx.ConnectError("setup failed"), final])
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    turn.output_stream_content = AsyncMock()
    assert await turn._run_stream_with_recovery("original task") is final
    assert [call.kwargs["user_input"] for call in run.await_args_list] == [
        "original task", "original task",
    ]


@pytest.mark.asyncio
async def test_goal_reminder_merged_into_input_still_counts_as_admitted(monkeypatch):
    turn = make_turn([[], [{"role": "user", "content": [
        {"type": "input_text", "text": "original task"},
        {"type": "input_text", "text": "<system-reminder>goal</system-reminder>"},
    ]}]])
    final = SimpleNamespace(final_output="ok")
    run = AsyncMock(side_effect=[httpx.ConnectError("interrupted"), final])
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    turn.output_stream_content = AsyncMock()
    assert await turn._run_stream_with_recovery("original task") is final
    assert run.await_args.kwargs["user_input"] == turn._STREAM_RECOVERY_INPUT


@pytest.mark.asyncio
async def test_storage_read_failure_prevents_continuation(monkeypatch):
    turn = make_turn([[], OSError("storage unavailable")])
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    turn.output_stream_content = AsyncMock(side_effect=missing())
    with pytest.raises(OSError, match="storage unavailable"):
        await turn._run_stream_with_recovery("task")
    assert run.await_count == 1
    turn.config.io.print_warning.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("invalid"), ModelBehaviorError("unrelated"),
                                 asyncio.CancelledError()])
async def test_nontransport_errors_and_cancellation_do_not_recover(error, monkeypatch):
    turn = make_turn([[]])
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    turn.output_stream_content = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await turn._run_stream_with_recovery("task")
    assert run.await_count == 1
    turn.config.io.print_warning.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_during_backoff_prevents_new_run(monkeypatch):
    turn = make_turn([[], [{"role": "user", "content": "task"}]])
    run = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError()))
    turn.output_stream_content = AsyncMock(side_effect=missing())
    with pytest.raises(asyncio.CancelledError):
        await turn._run_stream_with_recovery("task")
    assert run.await_count == 1
    assert turn.current_result is None
    assert not turn._result_ready.is_set()