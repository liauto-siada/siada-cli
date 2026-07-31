"""
In-memory session and compaction callback for sub-agents (run_subtask).

Design
------
``InMemorySession`` - lightweight ``Session``-protocol implementation backed by
a plain list.  ``add_items`` deduplicates entries by content fingerprint to
handle the write-back overlap described below.

Two cooperating hooks
---------------------
``make_sub_agent_session_input_callback`` - produces the ``session_input_callback``.
``make_sub_agent_compaction_filter``       - produces the ``call_model_input_filter``.

1. ``session_input_callback(history_items, new_items)``
   The framework invokes this once per run, with history and the new-turn input
   *already separated*.  Its only job is to **persist ``new_items`` into the
   session immediately** (``session.add_items(new_items)``).  This matters
   because the compaction filter reads ``session.get_items()`` *before* the
   framework's ``save_result_to_session`` has run; without seeding the new input
   here, the first model call of a (re-)run would not see the new input.  The
   callback returns ``history_items + new_items`` for the framework's bookkeeping
   but performs no compaction.

2. ``call_model_input_filter(data)``
   Runs before *every* model call and performs the actual compaction.  It treats
   ``session.get_items()`` as the authoritative, up-to-date context - seeded by
   the callback at run start and kept current per turn by the framework's
   per-turn ``save_result_to_session``.  When the context exceeds the token
   threshold it summarises, writes the compacted list back to the session, and
   returns it as the model input.

Why read from the session instead of ``model_data.input``
---------------------------------------------------------
The framework's RunState keeps an uncompressed full item list.  Once we compact
and write back, that list diverges from the (shorter) session.  Reading from
``session.get_items()`` instead - and seeding new input through the callback -
keeps the filter aligned with the compacted history without any fragile boundary
reconstruction (length slices, fingerprint sets, last-item anchors).

Deduplication in ``add_items``
------------------------------
After the filter writes ``compacted`` to the session, the framework's
``save_result_to_session`` re-persists the turn's items, which may overlap with
the tail of ``compacted``.  ``InMemorySession.add_items`` silently skips any item
whose content fingerprint is already present, preventing duplicates without
requiring knowledge of the runner's internal bookkeeping.

Debug dump mode
---------------
When enabled (``SIADA_SUBAGENT_DUMP`` truthy, or the global ``DEBUG`` flag), the
session snapshots its items to ``<log_dir>/sub_agent_dumps/<session_id>.jsonl``
at key points (filter entry, before / after compaction).  This makes it easy to
inspect how a sub-agent's context evolves across turns and across compaction
when diagnosing problems.  Dumping is a no-op (and never raises) when disabled.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from agents.items import TResponseInputItem
from agents.run_config import CallModelData, ModelInputData

from siada.agent_hub.context_filter.compaction_strategy import CompactionError
from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)
from siada.agent_hub.context_filter.utils import calculate_tokens
from siada.foundation.logging import get_log_directory, logger

if TYPE_CHECKING:
    from siada.models.model_run_config import ModelRunConfig


# ---------------------------------------------------------------------------
# Debug dump configuration
# ---------------------------------------------------------------------------
#
# Enable via either:
#   * SIADA_SUBAGENT_DUMP = 1 / true / yes / on   (explicit, takes precedence)
#   * DEBUG = 1 / true / yes                       (global debug flag fallback)
#
# Dump files live under ``<log_dir>/sub_agent_dumps/<session_id>.jsonl`` and each
# dump appends one JSON object per line:
#   {"timestamp": ..., "session_id": ..., "label": ..., "item_count": N, "items": [...]}

_DUMP_ENV = "SIADA_SUBAGENT_DUMP"
_DUMP_SUBDIR = "sub_agent_dumps"
_TRUTHY = ("1", "true", "yes", "on")


def _is_dump_enabled() -> bool:
    """Return True when sub-agent session dumping is enabled.

    ``SIADA_SUBAGENT_DUMP`` takes precedence when set; otherwise the global
    ``DEBUG`` flag is used as a fallback.
    """
    explicit = os.getenv(_DUMP_ENV)
    if explicit is not None:
        return explicit.strip().lower() in _TRUTHY
    return os.getenv("DEBUG", "False").strip().lower() in _TRUTHY


def _dump_file_path(session_id: str) -> Optional[Path]:
    """Resolve the dump file path for *session_id*, creating the dir if needed."""
    try:
        dump_dir = Path(get_log_directory()) / _DUMP_SUBDIR
        dump_dir.mkdir(parents=True, exist_ok=True)
        return dump_dir / f"{session_id}.jsonl"
    except Exception as exc:  # pragma: no cover - defensive, dumping must never crash
        logger.warning("[sub_agent_compaction_filter] failed to prepare dump dir: %s", exc)
        return None


def _dump_session_items(
    session_id: str,
    items: List[Any],
    label: str,
    *,
    include_items: bool = True,
) -> Optional[str]:
    """Append a snapshot of *items* to the session dump file.

    When *include_items* is False, only metadata (item_count, label, ...) is
    written and the full item payload is omitted.  This keeps high-frequency
    dump points (e.g. ``filter-entry``, which runs before every model call)
    lightweight while still recording that the point was reached.

    Returns the dump file path on success, or None if dumping is disabled or
    failed.  Dumping must never raise into the caller.
    """
    if not _is_dump_enabled():
        return None

    # Wrap the whole body: dumping is a debugging aid and must never raise into
    # the caller, regardless of where it fails (path resolution or file write).
    try:
        path = _dump_file_path(session_id)
        if path is None:
            return None

        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "session_id": session_id,
            "label": label,
            "item_count": len(items),
        }
        if include_items:
            record["items"] = items
        line = json.dumps(record, ensure_ascii=False, default=str)

        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        logger.info(
            "[sub_agent_compaction_filter] dumped %d items (label=%s) -> %s",
            len(items),
            label,
            path,
        )
        return str(path)
    except Exception as exc:  # pragma: no cover - defensive, dumping must never crash
        logger.warning(
            "[sub_agent_compaction_filter] failed to dump session items: %s", exc
        )
        return None


# ---------------------------------------------------------------------------
# Content fingerprint helper
# ---------------------------------------------------------------------------

def _item_fingerprint(item: Any) -> str:
    """Return a stable MD5 hex digest of the serialised item content."""
    try:
        return hashlib.md5(
            json.dumps(item, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()
    except Exception:
        # Fallback: use repr, which is stable within a process.
        return repr(item)


# ---------------------------------------------------------------------------
# In-memory session
# ---------------------------------------------------------------------------

class InMemorySession:
    """Lightweight in-memory Session-protocol implementation for sub-agents.

    All conversation history lives in a plain Python list - no disk I/O.
    ``add_items`` deduplicates by content fingerprint so that, after compaction
    write-back, items already in the session are not re-added by
    ``save_result_to_session``.
    """

    # Satisfy the Session protocol (SessionSettings | None); not used at runtime.
    session_settings: Any = None

    def __init__(self) -> None:
        self.session_id: str = f"sub-agent-{uuid.uuid4().hex[:8]}"
        self._items: List[Any] = []
        self._fingerprints: set[str] = set()

    # -- Session protocol ---------------------------------------------------

    async def get_items(self, limit: int | None = None) -> list:
        """Return stored items, optionally capped to the latest *limit* entries."""
        if limit is not None:
            return list(self._items[-limit:])
        return list(self._items)

    async def add_items(self, items: list) -> None:
        """Append items, skipping those already present (content deduplication)."""
        for item in items:
            fp = _item_fingerprint(item)
            if fp not in self._fingerprints:
                self._fingerprints.add(fp)
                self._items.append(item)

    async def pop_item(self) -> Any:
        """Remove and return the most recent item, or None if empty."""
        if not self._items:
            return None
        item = self._items.pop()
        self._fingerprints.discard(_item_fingerprint(item))
        return item

    async def clear_session(self) -> None:
        """Remove all items from the session."""
        self._items.clear()
        self._fingerprints.clear()

    # -- Debugging ----------------------------------------------------------

    async def dump_items(self, label: str = "", *, include_items: bool = True) -> Optional[str]:
        """Dump the current session items to the debug dump file.

        This is a debugging aid: when dump mode is disabled (the default) it is
        a cheap no-op returning None.  When enabled it appends a JSON snapshot of
        the current items (tagged with *label*) and returns the dump file path.

        Args:
            label: Free-form tag describing the dump point (e.g. ``filter-entry``).
            include_items: When False, only metadata is written (no full item
                payload) - useful for high-frequency dump points.

        Returns:
            The dump file path on success, otherwise None.
        """
        if not _is_dump_enabled():
            return None
        return _dump_session_items(
            self.session_id, list(self._items), label, include_items=include_items
        )


# ---------------------------------------------------------------------------
# Hook factories
# ---------------------------------------------------------------------------

# Singleton strategy instance - stateless, safe to share across all hook calls.
_STRATEGY = SummarizeWithHeaderCompaction()


def make_sub_agent_session_input_callback(session: InMemorySession):
    """Return an async ``session_input_callback`` that seeds new input into *session*.

    The framework invokes the callback once per run as
    ``callback(history_items, new_items)`` with the two lists already separated.
    Its sole responsibility is to persist ``new_items`` into the session right
    away, so the compaction filter's ``session.get_items()`` (which runs before
    the framework's ``save_result_to_session``) already includes this run's new
    input and does not lose it.

    No compaction happens here - that is the filter's job.  ``add_items`` dedups
    by fingerprint, so re-seeding the same input across retries is harmless.

    Args:
        session: The ``InMemorySession`` tied to this sub-agent run.

    Returns:
        An async callable compatible with ``RunConfig.session_input_callback``.
    """

    async def _session_input_callback(
        history_items: list[TResponseInputItem],
        new_items: list[TResponseInputItem],
    ) -> list[TResponseInputItem]:
        # Seed this run's new input into the session so the filter sees it.
        await session.add_items(list(new_items))
        # Snapshot the seeded session state for debugging.
        await session.dump_items("session-input-callback")
        # Return the combined list for the framework's input bookkeeping.
        return list(history_items) + list(new_items)

    return _session_input_callback


def make_sub_agent_compaction_filter(
    model_run_config: "ModelRunConfig",
    session: InMemorySession,
):
    """Return an async ``call_model_input_filter`` for sub-agent context compaction.

    The filter runs before every model call.  It treats ``session.get_items()``
    as the authoritative, up-to-date context: seeded by the session input
    callback at run start and kept current per turn by the framework's
    ``save_result_to_session``.  When the context exceeds the token threshold it
    summarises, writes the compacted list back to the session, and returns it as
    the model input.

    Args:
        model_run_config: Model run config (context window, model name, provider).
        session: The ``InMemorySession`` tied to this sub-agent run.

    Returns:
        An async callable compatible with ``RunConfig.call_model_input_filter``.
    """

    async def _compaction_filter(data: CallModelData) -> ModelInputData:
        # The session is the source of truth for the (possibly compacted)
        # context.  Fall back to model_data.input only if the session is empty
        # (e.g. the callback was not wired), so we never send an empty input.
        effective_input: list = await session.get_items()
        if not effective_input:
            effective_input = list(data.model_data.input)

        # Snapshot the context the filter is about to evaluate.  This runs before
        # every model call, so only metadata is recorded (no full item payload)
        # to keep the dump file lightweight; the full context is captured at the
        # "after-compaction" point when compaction actually happens.
        _dump_session_items(
            session.session_id, effective_input, "filter-entry", include_items=False
        )

        model_name = model_run_config.model_name
        token_count = calculate_tokens(model_name, effective_input)

        logger.info(
            "[sub_agent_compaction_filter] tokens=%d  threshold=%.0f  "
            "window=%d  items=%d",
            token_count,
            model_run_config.context_window * _STRATEGY.token_threshold_ratio,
            model_run_config.context_window,
            len(effective_input),
        )

        if not _STRATEGY.should_compact(token_count, model_run_config):
            return ModelInputData(
                input=effective_input,
                instructions=data.model_data.instructions,
            )

        logger.info(
            "[sub_agent_compaction_filter] compaction triggered: "
            "tokens=%d / window=%d (threshold=%.0f%%)",
            token_count,
            model_run_config.context_window,
            _STRATEGY.token_threshold_ratio * 100,
        )

        # Snapshot the full pre-compaction context.  Compaction is infrequent, so
        # recording the complete item payload here is affordable and invaluable
        # for diagnosing what got summarised away.
        _dump_session_items(session.session_id, effective_input, "before-compaction")

        try:
            result = await _STRATEGY.compact(model_run_config, effective_input)
        except CompactionError as exc:
            logger.warning(
                "[sub_agent_compaction_filter] CompactionError: %s -- skipping compaction",
                exc,
            )
            return ModelInputData(
                input=effective_input,
                instructions=data.model_data.instructions,
            )
        except Exception as exc:
            logger.warning(
                "[sub_agent_compaction_filter] unexpected error during compaction: %s "
                "-- skipping compaction",
                exc,
            )
            return ModelInputData(
                input=effective_input,
                instructions=data.model_data.instructions,
            )

        compacted = result.messages

        # Write the compacted history back so subsequent model calls start from
        # the compressed baseline.  InMemorySession.add_items deduplicates by
        # fingerprint, so items the framework re-persists after the turn (already
        # present in compacted's history_to_keep) are silently skipped.
        await session.clear_session()
        await session.add_items(compacted)

        # Snapshot the compacted session state.
        await session.dump_items("after-compaction")

        logger.info(
            "[sub_agent_compaction_filter] compacted %d items -> %d items",
            len(effective_input),
            len(compacted),
        )

        return ModelInputData(
            input=compacted,
            instructions=data.model_data.instructions,
        )

    return _compaction_filter
