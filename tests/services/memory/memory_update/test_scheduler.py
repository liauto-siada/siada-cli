"""Tests for ``MemoryUpdateScheduler`` — the two-stage orchestrator.

Critical contracts validated here:

* ``run()`` is async and **must be awaitable**.
* When the trigger says "no", neither stage runs.
* On trigger "yes":
    1. ``sync_stage`` is awaited inline — it MUST finish before
       ``run()`` returns;
    2. ``async_stage`` is scheduled via ``create_task`` and tracked in
       ``_in_flight``; it MUST NOT delay ``run()``.
* sync_stage failure does NOT prevent async_stage from being scheduled
  (failure decoupling).
* async_stage failure is swallowed by ``_run_async_safely`` and the
  task self-cleans from ``_in_flight``.
* ``shutdown(timeout)`` drains ONLY ``_in_flight`` (async-stage tasks);
  on timeout, pending tasks are cancelled.
* Multiple consecutive ``run()`` calls don't leak tasks.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.services.memory.memory_update.scheduler import (
    MemoryUpdateScheduler,
)
from siada.services.memory.memory_update.trigger import MemoryUpdateTrigger
from siada.services.memory.memory_update.updater import MemoryUpdater


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class _StaticTrigger(MemoryUpdateTrigger):
    """Trigger whose verdict is configurable per-instance."""

    def __init__(self, verdict: bool, *, raises: BaseException | None = None):
        self.verdict = verdict
        self.raises = raises
        self.calls = 0

    def should_trigger(self, *, context, tokens_count, item_count):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.verdict


class _ProgrammableUpdater(MemoryUpdater):
    """Updater whose stages are fully programmable.

    Test code can plug in `sync_impl` / `async_impl` coroutines to
    simulate fast paths, slow paths, and failures. Recorded events
    let assertions inspect ordering.
    """

    def __init__(self):
        self.sync_calls = 0
        self.async_calls = 0
        self.sync_completed = asyncio.Event()
        self.async_started = asyncio.Event()
        self.async_completed = asyncio.Event()
        self.sync_impl = None  # type: ignore[assignment]
        self.async_impl = None  # type: ignore[assignment]

    async def sync_stage(self, *, context, snapshot, tokens_count):
        self.sync_calls += 1
        if self.sync_impl is not None:
            await self.sync_impl(snapshot)
        self.sync_completed.set()

    async def async_stage(self, *, context, snapshot, tokens_count):
        self.async_calls += 1
        self.async_started.set()
        try:
            if self.async_impl is not None:
                await self.async_impl(snapshot)
        finally:
            self.async_completed.set()


def _ctx(session_id: str = "sess-X") -> SimpleNamespace:
    return SimpleNamespace(session_id=session_id)


# ---------------------------------------------------------------------------
# trigger=False short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_no_op_when_trigger_false():
    trig = _StaticTrigger(False)
    upd = _ProgrammableUpdater()
    sched = MemoryUpdateScheduler(trigger=trig, updater=upd)

    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=[1, 2, 3],
    )

    assert trig.calls == 1
    assert upd.sync_calls == 0
    assert upd.async_calls == 0
    assert sched._in_flight == set()


@pytest.mark.asyncio
async def test_trigger_exception_treated_as_false():
    """A buggy trigger must not crash the LLM call path."""
    trig = _StaticTrigger(True, raises=RuntimeError("boom"))
    upd = _ProgrammableUpdater()
    sched = MemoryUpdateScheduler(trigger=trig, updater=upd)

    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=[1],
    )
    assert upd.sync_calls == 0
    assert upd.async_calls == 0


# ---------------------------------------------------------------------------
# happy path: timing contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_stage_completes_before_run_returns_async_stage_after():
    """The two-stage timing contract — the heart of this design.

    The sync stage MUST complete before ``run()`` returns; the async
    stage MUST still be running afterwards (we lengthen it via sleep
    so the timing is observable).
    """
    upd = _ProgrammableUpdater()

    # async_stage takes a measurable time, sync_stage is instant.
    async def _slow_async(_snap):
        await asyncio.sleep(0.05)

    upd.async_impl = _slow_async

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )
    snapshot_src = [{"role": "user", "content": "hi"}]

    await sched.run(
        context=_ctx(),
        tokens_count=10,
        real_api_messages=snapshot_src,
    )

    # When run() returns:
    # 1) sync stage MUST be complete (await semantics).
    # 2) async stage is *scheduled* (in _in_flight) but its coroutine
    #    body may not have begun running yet — ``create_task`` only
    #    queues the coroutine; it actually starts on the next loop
    #    yield. The crucial guarantee is "not yet completed", which we
    #    enforce by making async_stage sleep 50ms.
    assert upd.sync_completed.is_set(), \
        "sync stage must have finished before run() returned"
    assert not upd.async_completed.is_set(), \
        "async stage must still be in flight (slow_async sleeps 50ms)"
    assert len(sched._in_flight) == 1, \
        "async stage must have been scheduled (tracked in _in_flight)"

    # Yield once → the queued task begins running.
    await asyncio.sleep(0)
    assert upd.async_started.is_set(), \
        "after a single loop yield, async stage must have started"
    assert not upd.async_completed.is_set(), \
        "but slow_async still hasn't finished its 50ms sleep"

    # Now wait for async to finish naturally — this validates the
    # done-callback removes it from the in-flight set.
    await asyncio.wait_for(upd.async_completed.wait(), timeout=1.0)
    # Give the loop a chance to fire the done-callback.
    await asyncio.sleep(0)
    assert sched._in_flight == set()


@pytest.mark.asyncio
async def test_snapshot_is_decoupled_from_caller_list():
    """Mutating the caller's list AFTER run() must not affect snapshot."""
    upd = _ProgrammableUpdater()
    captured: list = []

    async def _record(snap):
        # Capture the list reference the updater actually saw.
        captured.append(list(snap))

    upd.sync_impl = _record

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )

    src = [{"role": "user", "content": "1"}]
    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=src,
    )

    # Mutate the caller's list AFTER run() returned — simulating
    # compaction overwriting the originals.
    src.append({"role": "user", "content": "2"})
    src[0]["content"] = "MUTATED"

    # The sync stage saw the snapshot at the time of call, length 1.
    # (Inner-dict shared reference is documented and acceptable.)
    assert len(captured[0]) == 1


# ---------------------------------------------------------------------------
# failure decoupling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_stage_failure_does_not_block_async_stage():
    """sync_stage failing → log warning, async_stage STILL scheduled."""
    upd = _ProgrammableUpdater()

    async def _fail(_snap):
        raise RuntimeError("disk full")

    upd.sync_impl = _fail

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )

    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=["x"],
    )

    # async_stage was scheduled and ran to completion.
    await asyncio.wait_for(upd.async_completed.wait(), timeout=1.0)
    assert upd.async_calls == 1


@pytest.mark.asyncio
async def test_async_stage_failure_is_swallowed():
    """async_stage raising → ``_run_async_safely`` catches; task ends OK."""
    upd = _ProgrammableUpdater()

    async def _fail(_snap):
        raise RuntimeError("LLM unreachable")

    upd.async_impl = _fail

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )

    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=["x"],
    )

    # Wait for the async task to finish (it raises but is swallowed).
    await asyncio.wait_for(upd.async_completed.wait(), timeout=1.0)
    await asyncio.sleep(0)  # let done-callback fire

    # The task was tracked, then auto-cleaned. No exceptions surfaced.
    assert sched._in_flight == set()


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_with_no_in_flight_returns_immediately():
    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(False),
        updater=_ProgrammableUpdater(),
    )
    # Should not raise / not hang.
    await sched.shutdown(timeout=0.1)


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_async_tasks_and_cancels_on_timeout():
    upd = _ProgrammableUpdater()

    async def _long_async(_snap):
        # Long enough that shutdown's tiny timeout will trip.
        await asyncio.sleep(2.0)

    upd.async_impl = _long_async

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )
    await sched.run(
        context=_ctx(), tokens_count=0, real_api_messages=["x"],
    )

    assert len(sched._in_flight) == 1
    pending_task = next(iter(sched._in_flight))

    # Drive the shutdown timeout — the task should be cancelled.
    await sched.shutdown(timeout=0.05)

    # Give the loop a chance to process the cancellation + callback.
    await asyncio.sleep(0)
    assert pending_task.cancelled() or pending_task.done()
    # The done-callback (or the cancellation) should leave the set
    # empty.
    assert sched._in_flight == set()


# ---------------------------------------------------------------------------
# multi-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_runs_track_all_async_tasks_and_self_clean():
    """Three back-to-back ``run()`` calls → three async tasks, all cleaned."""
    upd = _ProgrammableUpdater()
    completed_count = 0

    async def _record_async(_snap):
        nonlocal completed_count
        await asyncio.sleep(0.01)
        completed_count += 1

    upd.async_impl = _record_async

    sched = MemoryUpdateScheduler(
        trigger=_StaticTrigger(True), updater=upd,
    )

    for i in range(3):
        # Reset events between runs so we can re-await per run.
        upd.sync_completed.clear()
        upd.async_started.clear()
        upd.async_completed.clear()
        await sched.run(
            context=_ctx(f"sess-{i}"),
            tokens_count=0,
            real_api_messages=[i],
        )

    # All three should be tracked at this point — possibly some have
    # already finished and self-cleaned, but at least one is in flight
    # since the last sleep is still running.
    assert sched._in_flight  # non-empty

    # Drain via shutdown with a comfortable timeout.
    await sched.shutdown(timeout=2.0)
    assert sched._in_flight == set()
    assert upd.sync_calls == 3
    assert upd.async_calls == 3
    assert completed_count == 3
