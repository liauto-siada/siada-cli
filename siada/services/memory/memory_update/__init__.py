"""Memory update package: pre-compaction snapshot capture pipeline.

This package implements the design described in
``design_docs/pre-compaction-memory-update-design.md``: a two-stage
(sync + async) hook that runs immediately before context compaction,
so the memory pipeline always sees the unsummarized message stream.

Public surface:
    - ``MemoryUpdateTrigger`` / ``PreCompactionTrigger``
    - ``MemoryUpdater`` / ``PreCompactionMemoryUpdater``
    - ``MemoryUpdateScheduler``
    - ``build_default_memory_scheduler`` — single assembly point.
    - ``get_memory_scheduler`` / ``release_memory_scheduler`` /
      ``reset_memory_scheduler_registry`` — per-session scheduler
      lifecycle (decoupled from ``CodeAgentContext``; see
      ``registry.py`` for rationale).
"""
from .scheduler import MemoryUpdateScheduler
from .trigger import MemoryUpdateTrigger, PreCompactionTrigger
from .updater import MemoryUpdater, PreCompactionMemoryUpdater


def build_default_memory_scheduler() -> MemoryUpdateScheduler:
    """Default factory: ``PreCompactionTrigger`` + ``PreCompactionMemoryUpdater``.

    Lives at module scope so callers (CodeAgentContext) don't have to
    construct the dependency graph themselves. Builds a fresh
    ``MemoryService`` instance pointing at the default
    ``~/.siada-cli/workspace/memory`` directory.
    """
    # Local import to avoid a circular import at package load time:
    # MemoryService → FileSession → … → siada.foundation, while this
    # module is itself imported lazily from ``CodeAgentContext``.
    from siada.services.memory.memory_service import MemoryService

    memory_service = MemoryService()
    return MemoryUpdateScheduler(
        trigger=PreCompactionTrigger(),
        updater=PreCompactionMemoryUpdater(memory_service),
    )


# Re-export the registry helpers AFTER the factory is defined so the
# registry's lazy import inside ``get_memory_scheduler`` always finds
# ``build_default_memory_scheduler`` already attached to the package.
from .registry import (  # noqa: E402  (intentional late import)
    get_memory_scheduler,
    release_memory_scheduler,
    reset_memory_scheduler_registry,
)


__all__ = [
    "MemoryUpdateScheduler",
    "MemoryUpdateTrigger",
    "PreCompactionTrigger",
    "MemoryUpdater",
    "PreCompactionMemoryUpdater",
    "build_default_memory_scheduler",
    "get_memory_scheduler",
    "release_memory_scheduler",
    "reset_memory_scheduler_registry",
]
