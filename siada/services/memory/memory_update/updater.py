"""Updater implementations — the *how* of a memory update.

Two-stage protocol:

* ``sync_stage``  — must finish **before** compaction starts. The
  scheduler ``await`` s it, so it must be quick (markdown + sqlite,
  millisecond-grade). Failure here is tolerated: the scheduler logs a
  warning and still proceeds to schedule the async stage.
* ``async_stage`` — fire-and-forget. The scheduler wraps it in
  ``asyncio.create_task`` and returns immediately. Failure here is
  swallowed inside ``_run_async_safely`` and never surfaces.

Both stages receive the **same in-memory snapshot** captured by the
scheduler at the synchronous boundary, so the markdown written by
``sync_stage`` and the inline-memory updates produced by ``async_stage``
describe the same point in time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.services.memory.memory_service import MemoryService


class MemoryUpdater(ABC):
    """Two-stage updater contract.

    Implementations should:

    * accept ``snapshot`` as already-shallow-copied (the scheduler does
      the copy at the synchronous boundary) and treat it as immutable;
    * keep ``sync_stage`` free of LLM calls or long I/O;
    * be safe to invoke concurrently across sessions; **single-session
      concurrency is bounded by trigger sparsity** (compaction itself
      is rare), so simple file/DB locks inside MemoryService suffice.
    """

    @abstractmethod
    async def sync_stage(
        self,
        *,
        context: "CodeAgentContext",
        snapshot: List[Any],
        tokens_count: int,
    ) -> None:
        """Synchronous stage — must complete before compaction starts."""
        ...

    @abstractmethod
    async def async_stage(
        self,
        *,
        context: "CodeAgentContext",
        snapshot: List[Any],
        tokens_count: int,
    ) -> None:
        """Asynchronous stage — runs in a background task; LLM-OK."""
        ...


class PreCompactionMemoryUpdater(MemoryUpdater):
    """Default updater wired into ``ApiMessageTransferFilter``.

    sync_stage  — wraps ``snapshot`` in ``_SnapshotSessionView`` and
                  forwards to ``MemoryService.save_session_memory``,
                  which writes the markdown + indexes it into SQLite/FTS5.
                  Reuses the existing ``LAST_MEMORY_NAME`` global cache
                  so multiple pre-compaction triggers in the same
                  session keep appending to the same memory file.

    async_stage — derives session text from the same snapshot via
                  ``MemoryService._get_all_messages`` /
                  ``_format_session_content`` and feeds it to
                  ``review_and_update_inline_memory``, which decides
                  whether to update ``MEMORY.md`` / ``USER.md``.

    Both stages share the snapshot — sync writes the markdown that
    captures the moment, async distills durable facts out of the same
    moment.
    """

    def __init__(self, memory_service: "MemoryService") -> None:
        self._memory_service = memory_service

    # ---- sync stage -----------------------------------------------------

    async def sync_stage(
        self,
        *,
        context: "CodeAgentContext",
        snapshot: List[Any],
        tokens_count: int,
    ) -> None:
        view = self._build_view(context, snapshot)
        # Pass workspace so the markdown's metadata block records where
        # the session ran. ``root_dir`` is what every other call site
        # (e.g. ConversationTurn._save_session_memory_if_needed) uses.
        workspace: Optional[str] = getattr(context, "root_dir", None)
        await self._memory_service.save_session_memory(view, workspace=workspace)

    # ---- async stage ----------------------------------------------------

    async def async_stage(
        self,
        *,
        context: "CodeAgentContext",
        snapshot: List[Any],
        tokens_count: int,
    ) -> None:
        # Local import: review agent depends on the agents framework
        # which is heavy and only needed in the background path.
        from siada.services.memory.memory_review_agent import (
            review_and_update_inline_memory,
        )

        view = self._build_view(context, snapshot)
        # Use MemoryService internals to produce exactly the same
        # role/content view that the markdown write used. This keeps
        # the async-stage input consistent with the sync-stage output
        # — same conversation, same formatter, same point in time.
        messages = await self._memory_service._get_all_messages(view)
        if not messages:
            logger.info(
                "[memory-update] async stage: no messages in snapshot, "
                "skipping review"
            )
            return

        session_content = self._memory_service._format_session_content(messages)
        await review_and_update_inline_memory(session_content)

    # ---- helpers --------------------------------------------------------

    def _build_view(
        self,
        context: "CodeAgentContext",
        snapshot: List[Any],
    ) -> Any:
        """Build a fresh ``_SnapshotSessionView`` for the given context.

        Each stage gets its own view instance so that any per-call
        state inside the view (currently none) cannot leak between
        sync and async paths. The underlying ``snapshot`` list is the
        same shallow copy in both cases.
        """
        # Local import to avoid making this module import-cycle-prone.
        from siada.services.memory.memory_update.snapshot_view import (
            _SnapshotSessionView,
        )

        session = getattr(context, "session", None)
        # ``session.openai_session`` (FileSession) carries
        # ``session_folder``; tolerate odd shapes (tests, mocks).
        openai_session = getattr(session, "openai_session", None) if session else None
        session_folder = getattr(openai_session, "session_folder", None)

        return _SnapshotSessionView(
            session_id=context.session_id or "unknown-session",
            session_folder=session_folder,
            snapshot=snapshot,
        )
