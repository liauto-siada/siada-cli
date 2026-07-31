"""In-memory snapshot view that quacks like a ``FileSession``.

This adapter lets ``MemoryService.save_session_memory`` and the rest of
the memory pipeline consume a list of API messages that lives entirely
in memory (a shallow copy of ``real_api_messages`` taken right before
compaction), without ever touching ``api_history.json`` /
``api_messages.json`` on disk. Decoupling this way means:

* the snapshot is **immutable from outside** — once captured, the main
  thread is free to mutate / replace ``real_api_messages`` (compaction,
  new turns, …) without races;
* ``MemoryService`` is duck-typed against the FileSession protocol
  (``session_id`` / ``session_folder`` + ``get_items`` /
  ``get_effective_messages`` / ``get_api_messages``), so we don't have
  to extend ``MemoryService`` to accept a new input type.

The class is package-private (``_`` prefix) because its only legitimate
constructor is ``PreCompactionMemoryUpdater``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple


class _SnapshotSessionView:
    """Read-only view onto a captured API-messages snapshot.

    Implements the subset of the ``FileSession`` interface that
    ``MemoryService`` relies on:

    * ``session_id`` / ``session_folder``  — plain attributes.
    * ``get_items(limit=None)``            — returns the snapshot, with
      optional tail-truncation matching ``FileSession.get_items``.
    * ``get_effective_messages()``         — the snapshot **is** the
      effective view (already unsummarized), so we just return it.
    * ``get_api_messages()``               — there is no underlying
      ``api_messages.json`` here, so we report "no snapshot available"
      via ``(None, -1)``.

    All getters return fresh ``list(...)`` copies to keep the internal
    snapshot truly immutable from the caller's perspective.
    """

    def __init__(
        self,
        session_id: str,
        session_folder: Optional[Path],
        snapshot: List[Any],
    ) -> None:
        # FileSession-protocol attributes
        self.session_id = session_id
        # ``session_folder`` may legitimately be ``None`` for purely
        # in-memory contexts (e.g. unit tests). MemoryService treats
        # missing folders defensively, so this is safe.
        self.session_folder = session_folder
        # Internal snapshot — only this view holds a reference; the
        # outside world can no longer mutate it through us.
        self._snapshot = list(snapshot)

    # ---- FileSession protocol ----

    async def get_items(self, limit: Optional[int] = None) -> List[Any]:
        """Return the snapshot (or its tail when ``limit`` is given)."""
        if limit is None:
            return list(self._snapshot)
        if limit < len(self._snapshot):
            return list(self._snapshot[-limit:])
        return list(self._snapshot)

    async def get_effective_messages(self) -> List[Any]:
        """Return the effective (i.e. unsummarized) message list.

        The snapshot already represents the "effective" semantics by
        construction, so no merging or fallback logic is needed.
        """
        return list(self._snapshot)

    async def get_api_messages(self) -> Tuple[Optional[List[Any]], int]:
        """No on-disk ``api_messages.json`` snapshot exists for a view.

        Returning ``(None, -1)`` matches the contract used by
        ``FileSession.get_api_messages`` when the file is missing.
        """
        return None, -1
