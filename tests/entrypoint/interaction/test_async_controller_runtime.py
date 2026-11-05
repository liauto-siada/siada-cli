"""Behavioral coverage for the single-loop controller and cancellation boundaries."""

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.turn.command_turn import CommandTurn, ControllerExit
from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import TurnInput
from siada.io.io import InputOutput, BACKGROUND_WAKEUP_SENTINEL
from siada.io.stdin_interrupt_monitor import StdinInterruptMonitor
from siada.services.siada_runner import SiadaRunner
from siada.tools.agent.subagent_async import (
    has_pending_background_subtasks, register_background_subtask,
)
from tests.entrypoint.interaction.test_controller_loop import (
    _make_config, _make_controller, _make_session, _run_loop_patches,
)
from tests.entrypoint.interaction.test_nointeractive_controller import (
    SyntheticStream, headless,
)


def test_multiple_turns_and_background_work_share_entrypoint_loop():
    config, _ = _make_config(inputs=["first", "second"])
    ctrl, _, policy, _ = _make_controller(
        config, SimpleNamespace(), session=_make_session("loop-identity"),
    )
    loops = []
    child_completed = threading.Event()

    async def execute(*args, **kwargs):
        loops.append(asyncio.get_running_loop())
        if len(loops) == 1:
            async def child():
                await asyncio.sleep(0)
                loops.append(asyncio.get_running_loop())
                child_completed.set()
            asyncio.create_task(child())
        return SimpleNamespace(output="done")

    policy.execute = execute
    with _run_loop_patches():
        assert ctrl.run() == 0
    assert child_completed.is_set()
    assert len(loops) == 3 and all(loop is loops[0] for loop in loops)
    assert loops[0].is_closed()
    assert not any(t.name == "ConversationTurn-AsyncLoop" for t in threading.enumerate())


@pytest.mark.asyncio
async def test_cancelled_turn_cleans_up_then_accepts_next_input_on_same_loop():
    config, io = _make_config(inputs=["first", "second"])
    ctrl, ui, policy, _ = _make_controller(
        config, SimpleNamespace(), session=_make_session("cancel-resume"),
    )
    loops, calls = [], []

    async def execute(turn, text, session, **kwargs):
        loops.append(asyncio.get_running_loop())
        calls.append(text)
        if text == "first":
            asyncio.get_running_loop().call_soon(ctrl.keyboard_interrupt)
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                calls.append("cleaned")
        return SimpleNamespace(output="done")

    policy.execute = execute
    with _run_loop_patches():
        assert await ctrl.run_async() == 0
    assert calls == ["first", "cleaned", "second"]
    assert loops[0] is loops[1]
    assert io.error_lines == []
    ui.close.assert_called_once()


@pytest.mark.asyncio
async def test_external_dispatcher_cancellation_propagates_after_cleanup():
    config, io = _make_config()
    entered = asyncio.Event()

    async def input_wait():
        entered.set()
        await asyncio.Event().wait()

    io.get_input_async = input_wait
    ctrl, ui, policy, _ = _make_controller(
        config, SimpleNamespace(), session=_make_session("external-cancel"),
    )
    with _run_loop_patches():
        task = asyncio.create_task(ctrl.run_async())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(policy.ended) == 1
    ui.close.assert_called_once()


@pytest.mark.asyncio
async def test_background_wakeup_does_not_wait_for_user_input():
    config, io = _make_config()
    cancelled = asyncio.Event()

    async def read():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    io.get_input_async = read
    ctrl, _, _, _ = _make_controller(config, SimpleNamespace())
    task = asyncio.create_task(ctrl._read_input())
    await asyncio.sleep(0)
    ctrl._bg_wakeup_event.set()
    assert await task == BACKGROUND_WAKEUP_SENTINEL
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_input_wins_when_background_and_user_input_are_both_ready():
    config, _ = _make_config(inputs=["human follow-up"])
    ctrl, _, _, _ = _make_controller(config, SimpleNamespace())
    ctrl._bg_wakeup_event.set()
    assert await ctrl._read_input() == "human follow-up"
    assert ctrl._bg_wakeup_event.is_set()


@pytest.mark.asyncio
async def test_stdin_reader_wakes_from_thread_and_retains_sync_tool_queue():
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader()
    try:
        task = asyncio.create_task(monitor.readline_async())
        await asyncio.sleep(0)
        thread = threading.Thread(target=monitor._enqueue_line, args=("hello\n",))
        thread.start()
        assert await asyncio.wait_for(task, 1) == "hello\n"
        thread.join()
        monitor._enqueue_line("tool reply\n")
        assert monitor.readline() == "tool reply\n"
        monitor._enqueue_line(None)
        with pytest.raises(EOFError):
            await monitor.readline_async()
    finally:
        monitor.unbind_async_reader()


@pytest.mark.asyncio
async def test_cancelling_input_read_preserves_next_message():
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader()
    try:
        task = asyncio.create_task(monitor.readline_async())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        monitor._enqueue_line("next\n")
        assert await monitor.readline_async() == "next\n"
    finally:
        monitor.unbind_async_reader()


@pytest.mark.asyncio
async def test_async_input_parses_multimodal_request_without_stale_images(monkeypatch):
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.get_stdin_monitor", lambda: monitor)
    io = InputOutput.__new__(InputOutput)
    io._notification_handler = None
    io._pending_image_paths = ["old-image"]
    payload = {"prompt": "describe", "image_paths": ["synthetic.png"],
               "_meta": {"siadaLog": {"requestId": "synthetic-request"}}}
    for text in (json.dumps(payload), '{"prompt":"next"}'):
        for line in ("<<<SIADA_MSG_START>>>\n", text + "\n", "<<<SIADA_MSG_END>>>\n"):
            monitor._enqueue_line(line)
    try:
        assert await io.get_input_async() == "describe"
        assert io._pending_image_paths == ["synthetic.png"]
        assert io._input_request_id == "synthetic-request"
        assert await io.get_input_async() == "next"
        assert io._pending_image_paths == []
        assert io._input_request_id != "synthetic-request"
    finally:
        monitor.unbind_async_reader()


@pytest.mark.asyncio
async def test_cancelled_partial_frame_is_retained_for_next_read(monkeypatch):
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.get_stdin_monitor", lambda: monitor)
    io = InputOutput.__new__(InputOutput)
    io._notification_handler = None
    monitor._enqueue_line("<<<SIADA_MSG_START>>>\n")
    monitor._enqueue_line("first line\n")
    task = asyncio.create_task(io.get_input_async())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    monitor._enqueue_line("second line\n")
    monitor._enqueue_line("<<<SIADA_MSG_END>>>\n")
    try:
        assert await io.get_input_async() == "first line\nsecond line"
    finally:
        monitor.unbind_async_reader()


@pytest.mark.asyncio
async def test_nested_prompt_notification_is_processed_as_input(monkeypatch):
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.get_stdin_monitor", lambda: monitor)
    io = InputOutput.__new__(InputOutput)
    io._notification_handler = Mock()
    body = json.dumps({"jsonrpc": "2.0", "method": "agent/execute", "params": {"prompt": "nested"}})
    for line in ("<<<SIADA_MSG_START>>>\n", body + "\n", "<<<SIADA_MSG_END>>>\n"):
        monitor._enqueue_line(line)
    try:
        assert await io.get_input_async() == "nested"
        io._notification_handler.assert_not_called()
    finally:
        monitor.unbind_async_reader()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_error", [False, True])
async def test_stream_cancellation_drains_result_and_background_sibling(headless, monkeypatch, cleanup_error):
    config, session = headless
    entered, cleaned = asyncio.Event(), asyncio.Event()
    child_started, child_cleaned = asyncio.Event(), asyncio.Event()
    result = SyntheticStream(error=ValueError("synthetic cleanup failure") if cleanup_error else None)

    async def model_run():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    result.run_loop_task = asyncio.create_task(model_run())
    result.cancel.side_effect = result.run_loop_task.cancel

    async def child():
        child_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            child_cleaned.set()

    ctx = SimpleNamespace(session_id=session.session_id, hook_pending_contexts=[])
    register_background_subtask(ctx, child)
    await child_started.wait()
    monkeypatch.setattr(SiadaRunner, "run_agent", AsyncMock(return_value=result))
    turn = ConversationTurn(config, session, SimpleNamespace(), render_stream=False)

    async def consume(_):
        await entered.wait()
        await asyncio.Event().wait()

    turn.output_stream_content = consume
    turn.handle_interrupt = AsyncMock()
    task = asyncio.create_task(turn.execute(TurnInput(use_input="synthetic task")))
    await entered.wait()
    # Wait for the stream handle to be installed, not just the model task.
    while turn.current_result is None:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set() and child_cleaned.is_set()
    assert not has_pending_background_subtasks(session.session_id)
    assert turn.current_result is None
    turn.handle_interrupt.assert_awaited_once()


@pytest.mark.asyncio
async def test_slash_exit_is_a_control_event_not_a_loop_terminating_baseexception():
    def exit_command(*args):
        raise SystemExit(0)

    turn = CommandTurn(SimpleNamespace(acp_mode=False), None, SimpleNamespace(run=exit_command))
    with pytest.raises(ControllerExit):
        await turn.execute(TurnInput(use_input="/exit"))
    assert await asyncio.create_task(asyncio.sleep(0, result="loop alive")) == "loop alive"


@pytest.mark.asyncio
async def test_cancelled_slash_command_releases_and_drains_sync_reader(monkeypatch):
    monitor = StdinInterruptMonitor()
    entered, cleaned = threading.Event(), threading.Event()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.get_stdin_monitor", lambda: monitor)

    def command(*args):
        entered.set()
        try:
            while True:
                monitor.readline(timeout=0.01)
        finally:
            cleaned.set()

    turn = CommandTurn(SimpleNamespace(acp_mode=False), None, SimpleNamespace(run=command))
    task = asyncio.create_task(turn.execute(TurnInput(use_input="/configure")))
    await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_eof_wakes_controller_and_cancels_active_turn():
    config, _ = _make_config()
    ctrl, _, _, _ = _make_controller(config, SimpleNamespace())
    monitor = StdinInterruptMonitor()
    monitor.bind_async_reader(ctrl._request_shutdown)
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def active():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    ctrl._active_task = asyncio.create_task(active())
    await entered.wait()
    try:
        monitor._enqueue_line(None)
        await asyncio.sleep(0)
        with pytest.raises(asyncio.CancelledError):
            await ctrl._active_task
        assert ctrl._exit_requested and cleaned.is_set()
    finally:
        monitor.unbind_async_reader()


def test_controller_closes_mcp_on_the_session_loop(monkeypatch):
    config, _ = _make_config()
    ctrl, _, policy, _ = _make_controller(
        config, SimpleNamespace(), session=_make_session("mcp-cleanup"),
    )
    seen = []

    async def start(_):
        seen.append(asyncio.get_running_loop())

    async def shutdown():
        seen.append(asyncio.get_running_loop())

    policy.start_session = start
    service = SimpleNamespace(is_initialized=True, shutdown=shutdown)
    monkeypatch.setattr("siada.services.mcp.manager_service._mcp_manager_service", service)
    with _run_loop_patches():
        assert ctrl.run() == 0
    assert len(seen) == 2 and seen[0] is seen[1]
    assert seen[0].is_closed()