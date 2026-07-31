"""Per-session JSON persistence for Goal state.

Stores exactly one Goal per session at <session_dir>/goal.json, sibling to
api_history.json / api_messages.json / metadata.json (see FileSession).

Atomic-write pattern (temp file + fsync + os.replace) copied from
CronTaskStorage.save_all (siada/agent_hub/proactive/cron_task_storage.py),
simplified to a single object instead of a list.

goal.json only ever holds the CURRENT goal — a goal can be overwritten by a
new /goal <objective> at any time, regardless of its status (active,
blocked, or complete), and every overwrite/clear resets the slate for a
fresh goal. So callers that replace or clear a goal (SlashCommands.cmd_goal,
Controller._maybe_reset_goal_on_new_turn) archive the outgoing goal to
<session_dir>/goal_history.jsonl (append-only, one JSON object per line)
via append_goal_history() BEFORE overwriting/clearing goal.json, so the
full lifecycle of every goal that ever existed in this session is still
recoverable even though only the latest one is "live".
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from siada.foundation.logging import logger
from siada.services.goal.models import Goal, _now_iso

GOAL_FILE_NAME = "goal.json"
GOAL_HISTORY_FILE_NAME = "goal_history.jsonl"


def _goal_file_path(session_dir: Path) -> Path:
    return Path(session_dir) / GOAL_FILE_NAME


def _goal_history_file_path(session_dir: Path) -> Path:
    return Path(session_dir) / GOAL_HISTORY_FILE_NAME



def save_goal(session_dir: Path, goal: Goal) -> bool:
    """Atomically write ``goal`` to ``<session_dir>/goal.json``.

    Returns True on success, False on failure (best-effort — callers should
    not crash the turn loop if a goal write fails).
    """
    goal_file = _goal_file_path(session_dir)
    try:
        goal_file.parent.mkdir(parents=True, exist_ok=True)
        json_data = goal.model_dump_json(indent=2)

        temp_fd, temp_path = tempfile.mkstemp(
            dir=goal_file.parent,
            prefix=".goal_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())
            Path(temp_path).replace(goal_file)
            return True
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.error(f"[goal_storage] Failed to save goal to {goal_file}: {e}")
        return False


def load_goal(session_dir: Path) -> Optional[Goal]:
    """Read the persisted Goal from ``<session_dir>/goal.json``.

    Returns None if the file does not exist, is unreadable, or fails
    validation (e.g. corrupted / from an incompatible schema version).
    """
    goal_file = _goal_file_path(session_dir)
    if not goal_file.exists():
        return None
    try:
        with open(goal_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Goal.model_validate(data)
    except Exception as e:
        logger.warning(f"[goal_storage] Failed to load goal from {goal_file}: {e}")
        return None


def clear_goal(session_dir: Path) -> None:
    """Remove the persisted goal file, if present. Best-effort."""
    goal_file = _goal_file_path(session_dir)
    try:
        if goal_file.exists():
            goal_file.unlink()
    except Exception as e:
        logger.warning(f"[goal_storage] Failed to clear goal file {goal_file}: {e}")


def append_goal_history(session_dir: Path, goal: Goal) -> None:
    """Append ``goal``'s final state to ``<session_dir>/goal_history.jsonl``.

    Call this BEFORE overwriting or clearing ``goal.json`` (see cmd_goal /
    Controller._maybe_reset_goal_on_new_turn) so the goal being replaced
    isn't lost — goal.json only ever holds the current goal, so this
    append-only log is the only place a session's full goal lifecline
    (every objective ever set, and the status it ended on) is recoverable.

    Best-effort: a history-write failure must not block the goal
    replace/clear it's recording.
    """
    history_file = _goal_history_file_path(session_dir)
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        record = goal.model_dump()
        record["archived_at"] = _now_iso()
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(
            f"[goal_storage] Failed to append goal history to {history_file}: {e}"
        )


def load_goal_history(session_dir: Path) -> List[dict]:
    """Read every archived goal from ``<session_dir>/goal_history.jsonl``,
    oldest first. Returns an empty list if the file is missing or unreadable;
    malformed individual lines are skipped rather than failing the whole read.
    """
    history_file = _goal_history_file_path(session_dir)
    if not history_file.exists():
        return []
    records: List[dict] = []
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    logger.warning(
                        f"[goal_storage] Skipping malformed goal_history line in {history_file}"
                    )
    except Exception as e:
        logger.warning(
            f"[goal_storage] Failed to load goal history from {history_file}: {e}"
        )
    return records

