"""Regressions for request-owned LiteLLM logging teardown."""

from __future__ import annotations

import asyncio
import time

import pytest

import _litellm_test_cleanup as cleanup


class RecordingWorker:
    """A loop-owned queue whose callbacks report observable completion."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._bound_loop = loop
        self._queue = asyncio.Queue()
        self._running_tasks = set()
        self._worker_task = None
        self.stopped = False

    def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            callback = await self._queue.get()
            try:
                await callback()
            finally:
                self._queue.task_done()

    async def stop(self):
        self.stopped = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
            self._worker_task = None


def test_drain_finishes_current_loop_callbacks(monkeypatch):
    async def run():
        worker = RecordingWorker(asyncio.get_running_loop())
        completed = []

        async def record():
            completed.append("finished")

        worker._queue.put_nowait(record)
        monkeypatch.setattr(cleanup, "_logging_worker", lambda: worker)
        await cleanup.drain_litellm_logging()
        assert completed == ["finished"]
        assert worker.stopped
        assert worker._queue.empty()
        assert worker._queue._unfinished_tasks == 0
        assert worker._worker_task is None

    asyncio.run(run())


def test_producer_detection_matches_pinned_litellm_task():
    from litellm.utils import _client_async_logging_helper

    async def run():
        # This real producer branch returns without initializing a worker.
        task = asyncio.create_task(_client_async_logging_helper(
            logging_obj=object(), result=None, start_time=0, end_time=0,
            is_completion_with_fallbacks=True,
        ))
        try:
            assert cleanup._producer_tasks() == [task]
        finally:
            await task

    asyncio.run(run())


def test_drain_rejects_foreign_loop_work_without_running_it(monkeypatch):
    foreign_loop = asyncio.new_event_loop()
    worker = RecordingWorker(foreign_loop)
    called = []

    async def record():
        called.append("wrong loop")

    worker._queue.put_nowait(record)
    monkeypatch.setattr(cleanup, "_logging_worker", lambda: worker)
    try:
        with pytest.raises(AssertionError, match="another loop"):
            asyncio.run(cleanup.drain_litellm_logging())
        assert not called and not worker.stopped
        assert worker._queue.qsize() == 1
        assert worker._queue._unfinished_tasks == 1
    finally:
        foreign_loop.close()


def test_empty_foreign_loop_is_left_untouched(monkeypatch):
    foreign_loop = asyncio.new_event_loop()
    worker = RecordingWorker(foreign_loop)
    monkeypatch.setattr(cleanup, "_logging_worker", lambda: worker)
    try:
        asyncio.run(cleanup.drain_litellm_logging())
        assert not worker.stopped and worker._worker_task is None
    finally:
        foreign_loop.close()


def test_drain_timeout_covers_worker_stop(monkeypatch):
    async def run():
        worker = RecordingWorker(asyncio.get_running_loop())

        async def wedged_stop():
            await asyncio.Event().wait()

        worker.stop = wedged_stop
        monkeypatch.setattr(cleanup, "_logging_worker", lambda: worker)
        started = time.monotonic()
        with pytest.raises(AssertionError, match="exceeded"):
            await cleanup.drain_litellm_logging(timeout=0.02)
        assert time.monotonic() - started < 0.5

    asyncio.run(run())


def test_drain_reports_work_added_during_stop(monkeypatch):
    async def run():
        worker = RecordingWorker(asyncio.get_running_loop())

        async def unprocessed():
            raise AssertionError("This callback must not be silently drained.")

        async def enqueue_during_stop():
            worker._queue.put_nowait(unprocessed)

        worker.stop = enqueue_during_stop
        monkeypatch.setattr(cleanup, "_logging_worker", lambda: worker)
        with pytest.raises(AssertionError, match="unfinished after stop"):
            await cleanup.drain_litellm_logging()
        assert worker._queue.qsize() == 1

    asyncio.run(run())