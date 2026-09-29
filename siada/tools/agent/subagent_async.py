"""
Background-task registry for ``run_subtask(async=True)`` runs.

When a sub-agent is launched with ``async_mode=True``, ``run_subtask`` must
return to the parent LLM call immediately instead of awaiting the sub-agent's
full run. This module owns the resulting ``asyncio.Task`` for the rest of its
lifetime:

- ``register_background_subtask`` wraps the sub-agent coroutine, creates the
  task, and tracks it under the parent session's id so an unfinished task is
  never silently lost.
- On completion (success or failure), the wrapper stages a short notification
  message into the parent's ``CodeAgentContext.hook_pending_contexts`` — the
  same queue ``SiadaRunHooks.on_llm_start`` already drains into the next LLM
  call as a system message (see ``siada/agent_hub/hooks/siada_run_hooks.py``).
  This is how the parent agent "hears back" from the sub-agent without any
  new injection machinery.
- ``shutdown_session_background_subtasks`` drains (or cancels, on timeout)
  every task still tracked for a session — called at session end so no task
  is left dangling when the process exits. Mirrors the same
  register/shutdown shape already used by
  ``siada.services.memory.memory_update.registry`` for the pre-compaction
  memory scheduler.
- ``register_session_wakeup`` lets the interaction layer (Controller) attach a
  per-session callback that fires the moment a background task's completion
  note has been staged. Without it, a task that finishes *after* the parent's
  turn has ended would sit in ``hook_pending_contexts`` until the user's next
  message triggers the next LLM call; the wakeup lets the idle input loop
  break out immediately and auto-inject the result as a continuation turn.
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from typing import TYPE_CHECKING, Awaitable, Callable, Dict, Set

from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext


# session_id -> {task_id -> asyncio.Task}. Module-private; access only via
# the functions below.
_SESSION_TASKS: Dict[str, Dict[str, "asyncio.Task"]] = {}

# session_id -> wakeup callback. Invoked (best-effort) right after a
# background task's completion note is staged, from the task's own thread
# (ConversationTurn's dedicated loop) — callbacks must be thread-safe and
# non-blocking. Guarded by _SESSION_WAKEUP_LOCK: registration happens on the
# main (Controller) thread while firing happens on the dedicated-loop thread.
_SESSION_WAKEUP: Dict[str, Callable[[], None]] = {}
_SESSION_WAKEUP_LOCK = threading.Lock()


def register_session_wakeup(session_id: str, callback: Callable[[], None]) -> None:
    """Register (or replace) the wakeup callback fired when any of this
    session's background sub-agent tasks stages its completion note."""
    with _SESSION_WAKEUP_LOCK:
        _SESSION_WAKEUP[session_id] = callback


def unregister_session_wakeup(session_id: str) -> None:
    """Remove the wakeup callback for a session (session end / teardown)."""
    with _SESSION_WAKEUP_LOCK:
        _SESSION_WAKEUP.pop(session_id, None)


def _fire_session_wakeup(session_id: str) -> None:
    """Invoke the registered wakeup callback, if any. Never raises — a broken
    callback must not kill the background task that just completed."""
    with _SESSION_WAKEUP_LOCK:
        callback = _SESSION_WAKEUP.get(session_id)
    if callback is None:
        return
    try:
        callback()
    except Exception as e:
        logger.warning(
            "[subagent_async] session=%s wakeup callback failed: %s", session_id, e
        )


def _tasks_for_session(session_id: str) -> Dict[str, "asyncio.Task"]:
    return _SESSION_TASKS.setdefault(session_id, {})


def register_background_subtask(
    agent_context: "CodeAgentContext",
    run_coro_factory: Callable[[], Awaitable[str]],
) -> str:
    """Schedule a sub-agent run in the background and return its task id.

    Args:
        agent_context: The PARENT agent's CodeAgentContext. Its
            ``hook_pending_contexts`` list receives the completion
            notification; its ``session_id`` is the tracking key.
        run_coro_factory: Zero-arg callable returning the awaitable that
            actually executes the sub-agent (typically a closure over
            ``run_subtask_impl(...)``). Deferred (not a bare coroutine) so
            the coroutine object is only created inside the task, avoiding
            "coroutine was never awaited" warnings if scheduling itself
            somehow fails.

    Returns:
        A short task id the parent (and, if surfaced, the model) can use to
        refer to this background run.
    """
    task_id = uuid.uuid4().hex[:8]
    session_id = agent_context.session_id or "unknown-session"

    async def _wrapped() -> None:
        try:
            summary = await run_coro_factory()
            note = (
                f"[Background sub-agent task {task_id} completed]\n{summary}"
            )
            logger.info(
                "[subagent_async] task=%s session=%s completed, summary_len=%d",
                task_id, session_id, len(summary or ""),
            )
        except asyncio.CancelledError:
            logger.info("[subagent_async] task=%s session=%s cancelled", task_id, session_id)
            raise
        except Exception as e:
            note = f"[Background sub-agent task {task_id} failed]\n{type(e).__name__}: {e}"
            logger.warning(
                "[subagent_async] task=%s session=%s failed: %s", task_id, session_id, e
            )
        else:
            pass
        finally:
            pass

        # Stage the completion note for the parent's next LLM call. Best
        # effort: a context that has since been torn down (e.g. process
        # exiting) must not raise out of the background task.
        try:
            agent_context.hook_pending_contexts.append(note)
        except Exception as e:
            logger.warning(
                "[subagent_async] task=%s failed to stage completion note: %s",
                task_id, e,
            )

        # Wake the (possibly idle) input loop so the staged note can be
        # injected as an auto-continuation turn immediately, instead of
        # waiting for the user's next message. Fired strictly AFTER staging
        # so a woken loop that drains the queue always sees the note.
        _fire_session_wakeup(session_id)

    task = asyncio.create_task(_wrapped(), name=f"run_subtask-async-{task_id}")
    tasks = _tasks_for_session(session_id)
    tasks[task_id] = task

    def _cleanup(_task: "asyncio.Task", *, _tid=task_id, _sid=session_id) -> None:
        _tasks_for_session(_sid).pop(_tid, None)

    task.add_done_callback(_cleanup)

    logger.info(
        "[subagent_async] task=%s session=%s scheduled in background",
        task_id, session_id,
    )
    return task_id


async def shutdown_session_background_subtasks(
    session_id: str, timeout: float = 30.0
) -> None:
    """Await (or cancel, on timeout) every background sub-agent task for a session.

    Call this at session end so a still-running ``async=True`` sub-agent is
    never silently dropped. Safe to call even when there are no tracked
    tasks (no-op).
    """
    tasks_map = _SESSION_TASKS.pop(session_id, None)
    if not tasks_map:
        return

    pending = list(tasks_map.values())
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True), timeout=timeout
        )
    except asyncio.TimeoutError:
        cancelled = 0
        for t in pending:
            if not t.done():
                t.cancel()
                cancelled += 1
        logger.warning(
            "[subagent_async] shutdown timeout (%ss) for session=%s; cancelled %d pending task(s)",
            timeout, session_id, cancelled,
        )


async def wait_for_session_background_subtasks(
    session_id: str, timeout: float = 30.0
) -> bool:
    """Wait up to ``timeout`` seconds for a session's pending background
    sub-agent tasks to finish, WITHOUT cancelling them on timeout.

    Used when a conversation turn's model output looks like a final,
    no-more-tool-calls completion while background ``run_subtask(async=True)``
    tasks are still outstanding (see ``Controller._maybe_await_background_subtask_summary``):
    give the tasks a bounded grace period to land their real result before
    deciding whether to hand control back to the user or inject an
    auto-continuation turn with their summaries.

    Deliberately does NOT use ``asyncio.wait_for(asyncio.gather(...), ...)``
    like ``shutdown_session_background_subtasks`` does -- ``wait_for``
    cancels its awaited future (here, the ``gather``, which cancels all its
    children) on timeout, which would kill still-useful in-progress work
    just because this particular caller stopped waiting. Polls ``done()``
    instead so a timeout here only means "stop waiting", never "cancel".

    Must be called on the event loop the tasks were created on (same
    requirement as ``shutdown_session_background_subtasks``).

    Returns:
        True if there was nothing to wait for, or everything finished within
        ``timeout``. False if one or more tasks are still running when the
        deadline is reached (they are left running, untouched).
    """
    tasks_map = _SESSION_TASKS.get(session_id)
    if not tasks_map:
        return True

    pending = list(tasks_map.values())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if all(t.done() for t in pending):
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(0.1, remaining))


def has_pending_background_subtasks(session_id: str) -> bool:
    """Return True if `session_id` still has unfinished background sub-agent tasks."""
    tasks_map = _SESSION_TASKS.get(session_id)
    return bool(tasks_map)


def cancel_session_background_subtasks(session_id: str) -> int:
    """Request cancellation of every background sub-agent task for a session.

    Unlike ``shutdown_session_background_subtasks`` (async, awaits/cancels
    from *within* the owning event loop), this is a plain sync function safe
    to call from a **different thread** than the one running the tasks —
    e.g. the main thread handling a Ctrl+C while the tasks live on
    ``ConversationTurn``'s dedicated background-loop thread. Calling
    ``task.cancel()`` directly from another thread is not thread-safe (the
    task's internal state is only safe to mutate on its own loop), so this
    schedules the cancellation via ``loop.call_soon_threadsafe`` instead of
    cancelling immediately in-line.

    Does not wait for the tasks to actually finish cancelling; the tasks'
    own ``done_callback`` (registered in ``register_background_subtask``)
    still fires normally and removes them from the registry once they do.

    Returns:
        The number of tasks for which cancellation was requested.
    """
    tasks_map = _SESSION_TASKS.get(session_id)
    if not tasks_map:
        return 0

    requested = 0
    for task_id, task in list(tasks_map.items()):
        if task.done():
            continue
        try:
            loop = task.get_loop()
            loop.call_soon_threadsafe(task.cancel)
            requested += 1
        except Exception as e:
            logger.warning(
                "[subagent_async] task=%s session=%s failed to request cancellation: %s",
                task_id, session_id, e,
            )

    if requested:
        logger.info(
            "[subagent_async] requested cancellation of %d background task(s) for session=%s",
            requested, session_id,
        )
    return requested
