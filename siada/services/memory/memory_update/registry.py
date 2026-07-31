"""Per-session scheduler registry — owns the per-``session_id`` lifecycle.

We deliberately keep the scheduler instances OUT of ``CodeAgentContext``
because:

* ``CodeAgentContext`` is a pydantic data model living in
  ``siada/foundation/`` — pulling service-layer types into it would
  invert layering and make the foundation depend on memory internals.
* Schedulers own ``asyncio.Task`` references that must not be
  serialized; embedding them as ``PrivateAttr`` works but leaks
  runtime state into a model whose contract is "plain data".
* Multiple call sites (filter, future cleanup hooks, tests) all want
  the SAME scheduler for a given session — a registry keyed by
  ``session_id`` makes that contract explicit.

The registry is process-wide and asyncio-friendly: dict insert/lookup
in CPython are atomic from the event loop's perspective, so no extra
locking is required for the single-loop case typical of this codebase.

Public API:
    - ``get_memory_scheduler(session_id)``     — lazy build + cache
    - ``release_memory_scheduler(session_id)`` — pop entry on session
      shutdown (does NOT call ``shutdown()`` itself; callers do that
      first when they want to flush in-flight async-stage tasks).
    - ``reset_memory_scheduler_registry()``    — test/teardown helper.
"""
from __future__ import annotations

from typing import Dict, Optional

from siada.foundation.logging import logger

from .scheduler import MemoryUpdateScheduler


# session_id → scheduler. Module-private; access only via the helpers.
_SCHEDULERS: Dict[str, MemoryUpdateScheduler] = {}


def get_memory_scheduler(session_id: Optional[str]) -> Optional[MemoryUpdateScheduler]:
    """Return the per-session scheduler, building it on first access.

    Returns ``None`` if:
      * ``session_id`` is missing (no stable key to cache under), or
      * the lazy factory raises (logged, swallowed — main flow must
        never break because of memory-layer initialization issues).

    The returned object is safe to ``await scheduler.run(...)`` and
    ``await scheduler.shutdown(...)``; calling code should treat
    ``None`` as "memory update disabled for this turn".
    """
    if not session_id:
        # No usable cache key. Returning None is the documented
        # contract for "best-effort, please skip".
        return None

    cached = _SCHEDULERS.get(session_id)
    if cached is not None:
        return cached

    # Local import keeps this module's load-time graph free of the
    # full memory-service dependency tree.
    try:
        from . import build_default_memory_scheduler

        scheduler = build_default_memory_scheduler()
    except Exception as e:
        # Never propagate: scheduler init is "best-effort". A bad
        # build means we degrade to no pre-compaction memory updates,
        # but the LLM call still proceeds.
        logger.warning(
            f"[memory-update] failed to build scheduler "
            f"(session={session_id}): {e}"
        )
        return None

    # ``setdefault`` makes the first writer win under any (unlikely)
    # concurrent build attempts — a duplicate scheduler from a race
    # would simply be GC'd after this returns.
    return _SCHEDULERS.setdefault(session_id, scheduler)


def release_memory_scheduler(session_id: Optional[str]) -> Optional[MemoryUpdateScheduler]:
    """Pop the scheduler for ``session_id`` (if any) and return it.

    Useful in session-shutdown paths so callers can chain:

        scheduler = release_memory_scheduler(sid)
        if scheduler is not None:
            await scheduler.shutdown(timeout=...)

    Returning the popped instance (instead of doing the shutdown here)
    keeps this helper sync-only and lets the caller decide on the
    timeout / await strategy that matches their cleanup context.
    """
    if not session_id:
        return None
    return _SCHEDULERS.pop(session_id, None)


def reset_memory_scheduler_registry() -> None:
    """Drop every cached scheduler — for unit tests / teardown only.

    No ``shutdown()`` is called: tests should manage their own
    asyncio task lifecycle to avoid stray warnings.
    """
    _SCHEDULERS.clear()
