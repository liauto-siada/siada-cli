"""Queries stay independent of active model turns and serial command input."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.entrypoint.interaction.command_input import CommandInput
from siada.entrypoint.interaction.turn.command_turn import CommandTurn
from siada.entrypoint.interaction.turn.models import TurnInput
from siada.io import stdin_interrupt_monitor as stdin
from siada.support.slash_commands import SlashCommands
from tests.entrypoint.interaction.test_controller_loop import (
    _make_config, _make_controller, _run_loop_patches,
)


def commands():
    slash = SlashCommands.__new__(SlashCommands)
    slash.io = Mock()
    return slash


def session(config):
    return SimpleNamespace(session_id="synthetic-session", siada_config=config)


def frame(prompt, *, structured=False):
    body = prompt
    if structured:
        envelope = {
            "params": {"prompt": prompt, "queue_id": "synthetic-queue"},
            "_meta": {"siadaLog": {"requestId": "synthetic-request"}},
        }
        if structured == "flat":
            envelope.update(envelope.pop("params"))
        body = json.dumps(envelope)
    return ["<<<SIADA_MSG_START>>>\n", body + "\n", "<<<SIADA_MSG_END>>>\n"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["status", "help"])
async def test_query_formats_output_without_shared_io_or_input_ready(name):
    config, _ = _make_config()
    slash = commands()
    turn = CommandTurn(config, session(config), slash)
    result = await turn.execute_immediate(TurnInput(use_input=f"/{name}"))
    assert result.output and result.metadata["command"] == name
    slash.io.print_info.assert_not_called()
    assert config.io.info_lines == []


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["/clear", "/model synthetic", "/statusbar", "!status"])
async def test_mutations_and_shell_commands_cannot_use_immediate_execution(prompt):
    config, _ = _make_config()
    with pytest.raises(ValueError):
        await CommandTurn(config, session(config), commands()).execute_immediate(
            TurnInput(use_input=prompt),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [False, True, "flat"])
async def test_reader_dispatches_queries_while_model_turn_remains_active(monkeypatch, structured):
    config, io = _make_config()
    slash = commands()
    ctrl, ui, policy, _ = _make_controller(config, slash, session=session(config))
    monitor = stdin.StdinInterruptMonitor()
    monkeypatch.setattr(stdin, "is_monitor_active", lambda: True)
    monkeypatch.setattr(stdin, "get_stdin_monitor", lambda: monitor)
    inputs = asyncio.Queue()
    inputs.put_nowait("long model turn")

    async def read():
        value = await inputs.get()
        if value is None:
            raise EOFError
        return value

    io.get_input_async = read
    entered, release, result_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
    observed = []

    async def execute(turn, text, running_session, **kwargs):
        observed.append(text)
        entered.set()
        await release.wait()
        return SimpleNamespace(output="model finished")

    policy.execute = execute
    notifications = []

    def notify(method, payload):
        notifications.append((method, payload))
        if method == "ui/commandResult":
            result_ready.set()

    ui.send_notification.side_effect = notify
    stdin.drain_pending_injections()
    stdin.set_agent_running(True)
    with _run_loop_patches():
        runtime = asyncio.create_task(ctrl.run_async())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            active = ctrl._active_task
            await asyncio.to_thread(monitor._dispatch_or_enqueue, frame("/status", structured=structured))
            await asyncio.wait_for(result_ready.wait(), 2)
            result = next(payload for method, payload in notifications if method == "ui/commandResult")
            assert "Model: initial-model" in result["content"]
            assert result["commandId"] and result["command"] == "status"
            if structured:
                assert result["queueId"] == "synthetic-queue"
            assert ctrl._active_task is active and not active.done()
            assert stdin.drain_pending_injections() == []
            assert monitor._queue.empty()
            assert observed == ["long model turn"]
            assert ui.set_processing.call_args_list == [((True,),)]
            release.set()
            inputs.put_nowait(None)
            assert await asyncio.wait_for(runtime, 2) == 0
            assert monitor._command_handler is None and not ctrl._command_tasks
        finally:
            release.set()
            if not runtime.done():
                runtime.cancel()
                await asyncio.gather(runtime, return_exceptions=True)
            stdin.drain_pending_injections()
            stdin.set_agent_running(False)


@pytest.mark.asyncio
async def test_serial_commands_are_fifo_and_not_tool_input_or_model_injections(monkeypatch):
    config, io = _make_config()
    ctrl, _, _, _ = _make_controller(config, commands(), session=session(config))
    monitor = stdin.StdinInterruptMonitor()
    monitor.set_command_handler(ctrl._route_command, ctrl._request_command_cancel)
    ctrl._loop = asyncio.get_running_loop()
    ctrl._accepting_commands = True
    monkeypatch.setattr(stdin, "get_stdin_monitor", lambda: monitor)
    stdin.drain_pending_injections()
    stdin.set_agent_running(True)
    try:
        for prompt in ["/clear", "/model next", "!status"]:
            monitor._dispatch_or_enqueue(frame(prompt))
        await asyncio.sleep(0)
        assert [item.prompt for item in ctrl._pending_commands] == ["/clear", "/model next", "!status"]
        assert monitor._queue.empty() and stdin.drain_pending_injections() == []

        async def wait_input():
            await asyncio.Event().wait()

        io.get_input_async = wait_input
        item = await ctrl._read_input()
        assert isinstance(item, CommandInput) and item.prompt == "/clear"
        monitor._handle_cancel_pending()
        await asyncio.sleep(0)
        assert not ctrl._pending_commands and not ctrl._commands_available.is_set()
    finally:
        stdin.drain_pending_injections()
        stdin.set_agent_running(False)


@pytest.mark.asyncio
async def test_query_waits_while_serial_command_mutates_session():
    config, _ = _make_config()
    ctrl, ui, _, _ = _make_controller(config, commands(), session=session(config))
    ctrl._accepting_commands = True
    ctrl._executing_serial_command = True
    request = CommandInput("/status", "c", "r")
    ctrl._accept_command(request)
    await asyncio.sleep(0)
    assert list(ctrl._pending_commands) == [request] and not ctrl._command_tasks
    ui.send_notification.assert_not_called()
    ctrl._executing_serial_command = False
    ctrl._accept_command(ctrl._pending_commands.popleft())
    await asyncio.gather(*tuple(ctrl._command_tasks))
    assert ui.send_notification.call_args.args[0] == "ui/commandResult"


@pytest.mark.asyncio
async def test_query_failure_has_own_error_result_without_cancelling_active_task():
    config, _ = _make_config()
    slash = commands()
    slash.get_status_text = Mock(side_effect=RuntimeError("synthetic query failure"))
    ctrl, ui, _, _ = _make_controller(config, slash, session=session(config))
    ctrl._active_task = asyncio.create_task(asyncio.Event().wait())
    try:
        await ctrl._execute_immediate_command(CommandInput("/status", "c", "r"))
        method, result = ui.send_notification.call_args.args
        assert method == "ui/commandResult" and result["error"]
        assert not ctrl._active_task.done()
        ui.set_processing.assert_not_called()
    finally:
        ctrl._active_task.cancel()
        await asyncio.gather(ctrl._active_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_session_exit_cancels_and_drains_unfinished_command_tasks(monkeypatch):
    config, io = _make_config()
    ctrl, ui, policy, _ = _make_controller(config, commands(), session=session(config))
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def query(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async def start(_):
        ctrl._accept_command(CommandInput("/status", "shutdown", "r"))

    async def read():
        await entered.wait()
        raise EOFError

    monkeypatch.setattr(CommandTurn, "execute_immediate", query)
    policy.start_session = start
    io.get_input_async = read
    with _run_loop_patches():
        assert await asyncio.wait_for(ctrl.run_async(), 2) == 0
    assert cleaned.is_set() and not ctrl._command_tasks
    ui.close.assert_called_once()


@pytest.mark.asyncio
async def test_queued_model_change_precedes_next_ordinary_prompt():
    config, io = _make_config()
    ctrl, _, _, _ = _make_controller(config, commands(), session=session(config))
    request = CommandInput("/model next", "c", "r")
    ctrl._pending_commands.append(request)
    ctrl._commands_available.set()
    io.get_input_async = AsyncMock(return_value="next user prompt")
    assert await ctrl._read_input() is request
    io.get_input_async.assert_not_awaited()
    assert not ctrl._commands_available.is_set()