"""Await logging owned by a mocked, non-streaming LiteLLM request.

LiteLLM 1.83.0 schedules ``_client_async_logging_helper`` before returning a
response. That task enqueues callbacks in a worker bound to the current event
loop. These fixtures use ``asyncio.run()``, so they must finish those tasks and
the queue before closing the loop; otherwise the next loop discards callbacks.

Only the current loop's producer tasks and queue are awaited. A foreign loop's
unfinished work, a timeout, or work left after stopping the idle worker fails
the test explicitly. No warning filter or logging switch is used. Callers
isolate user callbacks to empty lists; the shared sync callback executor is
outside this helper's scope. Callback exceptions handled internally by LiteLLM
are not surfaced by this helper.

One deadline covers all awaited operations. A callback that blocks the loop
synchronously cannot be interrupted by asyncio; exceeding the deadline is
reported once control returns.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

_DRAIN_TIMEOUT_SECONDS = 5.0


def _logging_worker() -> Any:
    """The process-global worker LiteLLM enqueues callback coroutines on."""
    from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

    return GLOBAL_LOGGING_WORKER


def _pending(worker: Any) -> int:
    """Count queued and in-flight items using Queue.join's completion signal."""
    queue = getattr(worker, "_queue", None)
    if queue is None:
        return 0
    return max(queue.qsize(), int(getattr(queue, "_unfinished_tasks", 0)))


def _producer_tasks() -> list[asyncio.Task]:
    """Find the pinned LiteLLM task that hands a response to its worker."""
    from litellm.utils import _client_async_logging_helper

    return [
        task for task in asyncio.all_tasks()
        if getattr(task.get_coro(), "cr_code", None)
        is _client_async_logging_helper.__code__
    ]


def _state(worker: Any) -> str:
    """Return counts only, without logging model requests or credentials."""
    return (
        f"unfinished={_pending(worker)}, "
        f"running={len(getattr(worker, '_running_tasks', ()))}, "
        f"producers={len(_producer_tasks())}"
    )


def _check_loop(worker: Any, loop: asyncio.AbstractEventLoop) -> None:
    queue = getattr(worker, "_queue", None)
    if queue is not None and getattr(worker, "_bound_loop", None) is not loop:
        if _pending(worker) or any(
            not task.done() for task in getattr(worker, "_running_tasks", ())
        ):
            raise AssertionError(
                f"LiteLLM logging has unfinished work on another loop: {_state(worker)}"
            )


async def drain_litellm_logging(timeout: float = _DRAIN_TIMEOUT_SECONDS) -> None:
    """Finish current-loop logging or fail, within one cooperative deadline."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("The LiteLLM logging drain timeout must be positive and finite.")
    worker = _logging_worker()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    _check_loop(worker, loop)

    try:
        async with asyncio.timeout_at(deadline):
            while True:
                producers = _producer_tasks()
                if producers:
                    await asyncio.gather(*producers)
                _check_loop(worker, loop)
                queue = getattr(worker, "_queue", None)
                if queue is None or getattr(worker, "_bound_loop", None) is not loop:
                    return
                if _pending(worker):
                    # Restart only this loop's worker if a prior stop left it idle.
                    worker.start()
                    await queue.join()
                running = [
                    task for task in getattr(worker, "_running_tasks", ())
                    if not task.done()
                ]
                if running:
                    await asyncio.gather(*running)
                _check_loop(worker, loop)
                if not _producer_tasks() and _pending(worker) == 0:
                    break
                if loop.time() >= deadline:
                    raise AssertionError(
                        f"LiteLLM logging drain exceeded {timeout}s: {_state(worker)}"
                    )

            # stop() only cancels the idle worker, after every callback completed.
            await worker.stop()
            _check_loop(worker, loop)
            if _pending(worker) or _producer_tasks():
                raise AssertionError(
                    f"LiteLLM logging was left unfinished after stop: {_state(worker)}"
                )
            if any(
                not task.done() for task in getattr(worker, "_running_tasks", ())
            ):
                raise AssertionError(
                    f"LiteLLM logging tasks survived stop: {_state(worker)}"
                )
            if loop.time() >= deadline:
                raise AssertionError(
                    f"LiteLLM logging drain exceeded {timeout}s: {_state(worker)}"
                )
    except TimeoutError as exc:
        raise AssertionError(
            f"LiteLLM logging drain exceeded {timeout}s: {_state(worker)}"
        ) from exc