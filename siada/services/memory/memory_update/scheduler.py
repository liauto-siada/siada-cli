"""Scheduler — coordinates trigger + two-stage updater + task lifecycle.

The scheduler is the single async entry point ``ApiMessageTransferFilter``
hits before compaction. Its contract:

1. ``run()`` is **async and awaitable**: callers must ``await`` it. It
   returns only after the synchronous stage has completed (or
   short-circuited because the trigger said no).
2. Inside ``run()`` we take a shallow copy of ``real_api_messages`` on
   the synchronous path; once that copy exists, the caller is free to
   mutate / replace the original list (e.g. via compaction).
3. ``sync_stage`` is awaited; failure is logged but never propagated.
4. ``async_stage`` is wrapped in ``asyncio.create_task`` and tracked in
   an in-flight set. ``shutdown(timeout)`` drains the set on session
   close.

Per-session isolation is enforced by ``CodeAgentContext.memory_scheduler``
giving each session its own scheduler instance — no cross-session
state lives here.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, List, Set

from siada.foundation.logging import logger

from .trigger import MemoryUpdateTrigger
from .updater import MemoryUpdater

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext


class MemoryUpdateScheduler:
    """Coordinates trigger + two-stage updater + background task lifecycle.

    Notes:

    * ``_in_flight`` only tracks **async-stage** tasks. The sync-stage
      coroutine is always awaited inline, so by the time we leave
      ``run()`` it's either complete or has logged its failure.
    * Done-callbacks discard tasks from the set automatically, so
      memory usage stays bounded (one transient entry per concurrent
      async stage). With trigger sparsity the set is usually empty
      and never grows beyond a small constant.
    """

    def __init__(
        self,
        trigger: MemoryUpdateTrigger,
        updater: MemoryUpdater,
    ) -> None:
        self._trigger = trigger
        self._updater = updater
        self._in_flight: Set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        context: "CodeAgentContext",
        tokens_count: int,
        real_api_messages: List[Any],
    ) -> None:
        """Run the two-stage memory update for the current LLM call.

        Stage order:

        0. ``context.memory_tools_enabled`` — master switch; if False,
           all memory pipeline stages are skipped immediately.
        1. ``trigger.should_trigger()`` — predicate (raises tolerated).
        2. ``snapshot = list(real_api_messages)`` — shallow copy on the
           synchronous boundary.
        3. ``await updater.sync_stage(...)`` — must finish before
           compaction; failure is logged but never propagated.
        4. ``asyncio.create_task(updater.async_stage(...))`` —
           fire-and-forget, tracked for shutdown.
        """
        # 0. Master switch: when memory is globally disabled, skip the
        #    entire pipeline — no session markdown write, no review agent.
        if not getattr(context, "memory_tools_enabled", True):
            logger.info("[memory-update] skipped — memory master switch is OFF")
            return

        # 1. Trigger: predicates must be exception-safe.
        try:
            should_trigger = self._trigger.should_trigger(
                context=context,
                tokens_count=tokens_count,
                item_count=len(real_api_messages),
            )
        except Exception as e:
            # Defensive: wrapping here also catches misbehaving custom
            # triggers that don't follow the "never raise" contract.
            logger.warning(f"[memory-update] trigger raised: {e}")
            should_trigger = False
        if not should_trigger:
            return

        # 2. Capture the snapshot at the synchronous boundary so the
        # main thread is free to mutate ``real_api_messages`` from
        # this point on (compaction may rewrite the list in place).
        snapshot: List[Any] = list(real_api_messages)
        session_id = self._safe_session_id(context)

        # 3. Sync stage — MUST complete before compaction starts.
        # We treat its failure as non-fatal: missing one memory write
        # is far cheaper than failing an LLM call.
        try:
            await self._updater.sync_stage(
                context=context,
                snapshot=snapshot,
                tokens_count=tokens_count,
            )
            logger.info(
                f"[memory-update] sync stage done "
                f"(session={session_id}, items={len(snapshot)})"
            )
        except Exception as e:
            logger.warning(
                f"[memory-update] sync stage failed "
                f"(session={session_id}): {e}"
            )

        # 4. Async stage — fire-and-forget. Even if the sync stage
        # failed above, we still try the async one so review-agent
        # memory updates can proceed independently.
        try:
            task = asyncio.create_task(
                self._run_async_safely(context, snapshot, tokens_count),
                name=f"memory-update-async-{session_id}",
            )
            self._in_flight.add(task)
            # Auto-cleanup the in-flight set when the task finishes —
            # ``discard`` is safe even if the task was never inserted.
            task.add_done_callback(self._in_flight.discard)
        except Exception as e:
            # ``create_task`` failing is virtually impossible (would
            # require no running event loop), but we still belt-and-
            # braces it so the main flow never sees an exception.
            logger.warning(
                f"[memory-update] async stage schedule failed: {e}"
            )

    # ------------------------------------------------------------------
    # public lifecycle
    # ------------------------------------------------------------------

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Drain any in-flight async-stage tasks before session close.

        Called from session-cleanup hooks (e.g. ConversationTurn's
        memory drain). Bounded by ``timeout``; on timeout we cancel
        whatever is still pending so the event loop can fully shut down.
        """
        if not self._in_flight:
            return

        # Snapshot the set so concurrent ``add``/``discard`` calls
        # can't surprise us mid-await.
        pending = list(self._in_flight)
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            cancelled = 0
            for t in pending:
                if not t.done():
                    t.cancel()
                    cancelled += 1
            logger.warning(
                f"[memory-update] shutdown timeout ({timeout}s); "
                f"cancelled {cancelled} pending async-stage tasks"
            )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _run_async_safely(
        self,
        context: "CodeAgentContext",
        snapshot: List[Any],
        tokens_count: int,
    ) -> None:
        """Wrap ``async_stage`` so background failures never escape.

        Any exception is caught and logged; the task itself completes
        normally so the done-callback runs and the in-flight set is
        cleaned up.
        """
        session_id = self._safe_session_id(context)
        try:
            await self._updater.async_stage(
                context=context,
                snapshot=snapshot,
                tokens_count=tokens_count,
            )
            logger.info(
                f"[memory-update] async stage done "
                f"(session={session_id}, items={len(snapshot)})"
            )
        except asyncio.CancelledError:
            # Re-raise so the task is properly marked cancelled — the
            # done-callback will still clear the in-flight slot.
            logger.info(
                f"[memory-update] async stage cancelled "
                f"(session={session_id})"
            )
            raise
        except Exception as e:
            logger.warning(
                f"[memory-update] async stage failed "
                f"(session={session_id}): {e}"
            )

    @staticmethod
    def _safe_session_id(context: "CodeAgentContext") -> str:
        """Defensive accessor — tests may pass partial contexts."""
        sid = getattr(context, "session_id", None)
        return sid if sid else "unknown-session"
