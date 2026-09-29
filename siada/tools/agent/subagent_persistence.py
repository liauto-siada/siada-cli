"""
On-disk persistence for recursive sub-agent conversations.

Gated entirely behind ``sub_agent.allow_recursive_subagents`` (conf.yaml,
default False) — callers only invoke this module when that switch is on;
when it's off, sub-agent runs are not persisted here at all (matching the
pre-existing, unpersisted behaviour exactly).

Storage layout, alongside the main agent's own session directory so it's
easy for a user to find (``DirectoryUtils.get_global_sessions_dir``):

    <sessions_dir>/<root_session_id>/subagents/
        index.json          # lifecycle/status table for every agent in the tree
        <agent_id>.log       # one human-readable transcript per agent

``index.json`` is the single source of truth consulted on resume: any entry
still ``status == "running"`` when the main agent process last touched it
means that agent's work was interrupted (main agent crashed/was killed) and
its progress needs to be surfaced back to the user (see ``scan_unfinished``).

The ``.log`` files reuse the same three message kinds already pushed to the
ACP sub-agent detail view (``tool_call`` / ``tool_output`` / ``thinking`` /
``message``), formatted the same readable way as the existing
``LoggerTracingProcessor`` trace logs, so a user opening one of these files
gets a familiar, easy-to-scan transcript.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from siada.foundation.logging import logger

# One lock per index.json path, guarding the read-modify-write cycle against
# concurrent sub-agents running as interleaved asyncio tasks (and, more
# importantly, against tool coroutines that hop onto worker threads via
# asyncio.to_thread, e.g. run_cmd).
_INDEX_LOCKS: dict[str, threading.Lock] = {}
_INDEX_LOCKS_GUARD = threading.Lock()


def _lock_for(index_path: Path) -> threading.Lock:
    key = str(index_path)
    with _INDEX_LOCKS_GUARD:
        lock = _INDEX_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _INDEX_LOCKS[key] = lock
        return lock


def subagents_dir(root_dir: str, root_session_id: str) -> Path:
    """Resolve ``<sessions_dir>/<root_session_id>/subagents`` from a project root path.

    Used by the live run path (``run_subtask_impl``), where the caller has
    ``CodeAgentContext.root_dir`` (the actual project root string) on hand.
    """
    from siada.utils import DirectoryUtils

    sessions_dir = Path(DirectoryUtils.get_global_sessions_dir(root_dir))
    return sessions_dir / root_session_id / "subagents"


def subagents_dir_from_session_path(session_path: Path) -> Path:
    """Resolve ``<session_path>/subagents`` directly from a known session directory.

    Used by the resume path (``ResumeService``), which already has the
    concrete on-disk session directory (``<sessions_dir>/<session_id>``) and
    would otherwise have no way to recover the original project root string
    from it (the sessions dir name is a one-way hash of that root).
    """
    return session_path / "subagents"


def _index_path(base_dir: Path) -> Path:
    return base_dir / "index.json"


def _log_path(base_dir: Path, agent_id: str) -> Path:
    return base_dir / f"{agent_id}.log"


def _now() -> str:
    return datetime.now().isoformat()


def _read_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {"agents": {}}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("agents", {})
            return data
    except Exception as e:
        logger.warning(f"[subagent_persistence] failed to read {index_path}: {e}")
        return {"agents": {}}


def _write_index(index_path: Path, data: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = index_path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(index_path)
    except Exception as e:
        logger.warning(f"[subagent_persistence] failed to write {index_path}: {e}")


def record_start(
    root_dir: str,
    root_session_id: str,
    *,
    agent_id: str,
    parent_id: Optional[str],
    depth: int,
    title: str,
    instruction: str,
) -> None:
    """Register a new agent as ``running`` in ``index.json`` and start its log file."""
    base_dir = subagents_dir(root_dir, root_session_id)
    index_path = _index_path(base_dir)
    with _lock_for(index_path):
        data = _read_index(index_path)
        data["root_session_id"] = root_session_id
        data["agents"][agent_id] = {
            "id": agent_id,
            "parent_id": parent_id,
            "depth": depth,
            "title": title,
            "instruction": instruction,
            "status": "running",
            "summary": "",
            "log_file": f"{agent_id}.log",
            "started_at": _now(),
            "updated_at": _now(),
            "finished_at": None,
        }
        _write_index(index_path, data)

    log_path = _log_path(base_dir, agent_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== Sub-agent {agent_id} (depth={depth}, parent={parent_id or 'main-agent'}) ===\n")
            f.write(f"Started: {_now()}\n")
            f.write(f"Instruction:\n{instruction}\n")
            f.write("=" * 60 + "\n\n")
    except Exception as e:
        logger.warning(f"[subagent_persistence] failed to init log {log_path}: {e}")


def append_log(
    root_dir: str,
    root_session_id: str,
    agent_id: str,
    kind: str,
    text: str,
    *,
    tool_name: Optional[str] = None,
) -> None:
    """Append one readable transcript entry to ``<agent_id>.log``."""
    log_path = _log_path(subagents_dir(root_dir, root_session_id), agent_id)
    label = {
        "tool_call": f"🔧 TOOL CALL{f' [{tool_name}]' if tool_name else ''}",
        "tool_output": "📤 TOOL OUTPUT",
        "thinking": "💭 THINKING",
        "message": "💬 FINAL MESSAGE",
    }.get(kind, kind.upper())
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{_now()}] {label}\n{text}\n\n")
    except Exception as e:
        logger.warning(f"[subagent_persistence] failed to append log {log_path}: {e}")


def record_finish(
    root_dir: str,
    root_session_id: str,
    agent_id: str,
    status: str,
    summary: str,
) -> None:
    """Mark an agent's entry ``completed``/``failed`` in ``index.json``."""
    base_dir = subagents_dir(root_dir, root_session_id)
    index_path = _index_path(base_dir)
    with _lock_for(index_path):
        data = _read_index(index_path)
        entry = data["agents"].get(agent_id)
        if entry is None:
            entry = {"id": agent_id}
            data["agents"][agent_id] = entry
        entry["status"] = status
        entry["summary"] = summary
        entry["updated_at"] = _now()
        entry["finished_at"] = _now()
        _write_index(index_path, data)

    log_path = _log_path(base_dir, agent_id)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"=== Finished: {status} at {_now()} ===\n{summary}\n")
    except Exception as e:
        logger.warning(f"[subagent_persistence] failed to finalize log {log_path}: {e}")


def _scan_unfinished_in_dir(base_dir: Path) -> list[dict[str, Any]]:
    index_path = _index_path(base_dir)
    if not index_path.exists():
        return []
    data = _read_index(index_path)
    return [
        entry for entry in data.get("agents", {}).values()
        if entry.get("status") == "running"
    ]


def scan_unfinished(root_dir: str, root_session_id: str) -> list[dict[str, Any]]:
    """Return every agent entry still ``status == "running"`` (live-run path).

    Called on session resume when the caller has a project root string on
    hand. Any matching entry means the main agent process ended (crash /
    kill) before that sub-agent's run_subtask call returned, so its
    work-in-progress needs to be surfaced back to the user/main agent.
    """
    return _scan_unfinished_in_dir(subagents_dir(root_dir, root_session_id))


def scan_unfinished_from_session_path(session_path: Path) -> list[dict[str, Any]]:
    """Same as ``scan_unfinished``, but resolved from a known session directory.

    Used by ``ResumeService``, which has the concrete on-disk session
    directory but not the original project root string (see
    ``subagents_dir_from_session_path``).
    """
    return _scan_unfinished_in_dir(subagents_dir_from_session_path(session_path))


def read_log_tail(root_dir: str, root_session_id: str, agent_id: str, max_chars: int = 2000) -> str:
    """Return the last ``max_chars`` characters of an agent's log file (best-effort)."""
    log_path = _log_path(subagents_dir(root_dir, root_session_id), agent_id)
    try:
        text = log_path.read_text(encoding="utf-8")
        return text[-max_chars:]
    except Exception:
        return ""
