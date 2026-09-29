"""Managed background worker + daemon drain entry for browser-skill learning.

The SQLite queue in ``playbooks.sqlite3`` is the single truth source; this
module only drains it through ``distiller.process_pending_updates``:

- ``BrowserLearningWorker`` — the runtime-side managed asyncio task (woken
  after every enqueue / browser-session registration; never starts itself).
- ``run_batch_distillation`` — the proactive daemon's periodic entry point,
  recovering pending/expired records from previous processes.

Both perform zero LLM calls when nothing is pending.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _distiller():
    from . import distiller

    return distiller


async def run_batch_distillation() -> dict:
    """Drain pending learning records. Returns {'processed': N, 'failed': M}."""
    return await _distiller().process_pending_updates()


class BrowserLearningWorker:
    """Managed background worker that drains the browser-skill learning queue.

    One asyncio management task plus an Event for wake-ups:

    - ``wake()``       — synchronous, cheap signal (runtime calls it right
                         after enqueueing an ExecutionRecord / registering a
                         browser session). Lazily spawns the management task
                         when an event loop is running. No-op once closed.
    - ``start()``      — explicit spawn of the single management task
                         (idempotent). Constructing/importing never starts
                         anything; the worker refuses to start after ``close()``.
    - ``drain_once()`` — one explicit drain through
                         ``distiller.process_pending_updates(store=...)``.
    - ``close()``      — cancels and awaits the management task. Cancellation
                         propagates into process_pending_updates, whose
                         ``finally`` releases the claimed lease; records stay
                         persisted in SQLite.

    The loop re-checks ``pending_count`` every ``retry_interval`` seconds, so
    backoff'd records are retried; when nothing is pending no LLM boundary is
    touched (drain is only invoked when pending_count > 0).
    """

    def __init__(self, store=None, retry_interval: float = 5.0):
        self._store = store
        self._retry_interval = max(0.05, float(retry_interval))
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _store_instance(self):
        if self._store is not None:
            return self._store
        from .playbook import PlaybookStore

        return PlaybookStore()

    def _ensure_task(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="browser-learning-worker")

    def wake(self) -> None:
        """Ask the loop to drain now. Safe from any context; ignored when closed."""
        if self._closed:
            logger.debug("[browser-skill] worker wake ignored: worker already closed")
            return
        if self._task is None or self._task.done():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                logger.debug("[browser-skill] wake without a running loop; next start() will pick it up")
            else:
                self._ensure_task()
        self._wake_event.set()

    def start(self) -> None:
        """Start the single management task. Requires a running event loop."""
        if self._closed:
            raise RuntimeError("[browser-skill] worker is closed and cannot be restarted")
        self._ensure_task()

    async def drain_once(self) -> dict:
        """One explicit drain through distiller.process_pending_updates."""
        logger.info("[STEP 12] learning worker draining queue")
        result = await _distiller().process_pending_updates(store=self._store)
        logger.info(
            "[STEP 12] drain finished: processed=%d failed=%d",
            result.get("processed", 0), result.get("failed", 0),
        )
        return result

    def _has_pending(self, store) -> bool:
        counter = getattr(store, "pending_count", None)
        if counter is None:
            return True
        try:
            return bool(counter())
        except Exception:  # noqa: BLE001 — unknown backend state: let distiller decide
            return True

    async def _run(self) -> None:
        store = self._store_instance()
        try:
            while True:
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=self._retry_interval)
                except asyncio.TimeoutError:
                    pass
                self._wake_event.clear()
                if not self._has_pending(store):
                    continue
                try:
                    await self.drain_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "[browser-skill] worker drain failed: %s; retrying in %.1fs",
                        e, self._retry_interval,
                    )
        except asyncio.CancelledError:
            raise
        finally:
            logger.debug("[browser-skill] worker loop exiting")

    async def close(self) -> None:
        """Cancel the management task and await its exit. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._wake_event.set()  # unblock a wake-wait so cancellation is prompt
        task, self._task = self._task, None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
