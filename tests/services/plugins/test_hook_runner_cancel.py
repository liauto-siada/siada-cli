"""Async hooks reap their subprocesses on cancellation and timeout."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.services.plugins.hook_runner import HookRunner
from siada.services.plugins.types import HookEntry


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("timeout", [False, True])
async def test_hook_process_is_reaped(background, timeout, monkeypatch):
    entered = asyncio.Event()

    async def communicate(_):
        entered.set()
        if timeout:
            raise asyncio.TimeoutError
        await asyncio.Event().wait()

    proc = SimpleNamespace(
        pid=123456, returncode=None, communicate=communicate,
        kill=Mock(), wait=AsyncMock(),
    )
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", spawn)
    killpg = Mock()
    monkeypatch.setattr("siada.services.plugins.hook_runner.os.killpg", killpg, raising=False)
    runner = HookRunner()
    execute = runner._execute_async if background else runner._execute_with_result
    task = asyncio.create_task(execute(HookEntry(command="synthetic hook"), "test", ".", "PreTurn", "{}"))
    await entered.wait()
    if not timeout:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    proc.wait.assert_awaited_once()
    assert killpg.called or proc.kill.called