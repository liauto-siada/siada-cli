"""Runtime Git snapshot injected as hidden user metadata.

The snapshot gives the model the workspace's branch, HEAD and a bounded
worktree summary at a known capture time, as a hidden ``input_text`` part on
the user's turn. Older sessions may contain a standalone ``role=user`` item.
It never carries workspace rules, memory or skills — those stay in the system
prompt — and it is explicitly marked as possibly stale, so it cannot replace
a live check before edits or destructive Git operations.

Lifecycle (driven by the callers, see CodeGenAgent and
ApiMessageTransferFilter): captured once when the effective history has no
snapshot (new session or resumed session without one) and refreshed after a
successful compaction. Consecutive tool calls reuse the snapshot already in
history, so the disk is not rescanned on every model call. At most one snapshot
is kept in the effective history: older versions are removed before a new one
is merged into a user message.

Every field is serialized as an escaped JSON string with the characters
that could forge a block boundary (``[``, ``]``, ``<``, ``>``) escaped as
``\\uXXXX``, and the listing is bounded, so branch names or paths can
neither fake the snapshot/reminder tags nor bloat the context.

This module only depends on the standard library so every layer (agent,
context filters, display helpers) can use its detection helpers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

GIT_SNAPSHOT_OPEN_PREFIX = "[Siada Git snapshot |"
GIT_SNAPSHOT_CLOSE_TAG = "[/Siada Git snapshot]"
GIT_SNAPSHOT_ENV = "SIADA_GIT_SNAPSHOT"

_GIT_TIMEOUT_SECONDS = 3
# Bounds keep a huge dirty worktree from flooding the context.
MAX_LISTED_PATHS = 20
MAX_FIELD_CHARS = 200

_BOUNDARY_ESCAPES = {
    "[": "\\u005b",
    "]": "\\u005d",
    "<": "\\u003c",
    ">": "\\u003e",
}


def git_snapshot_enabled() -> bool:
    """Allow disabling the shared snapshot independently of model-specific prompts."""
    return os.environ.get(GIT_SNAPSHOT_ENV, "").strip().lower() not in (
        "0", "false", "no", "off", "legacy", "disabled"
    )


@dataclass(frozen=True)
class GitSnapshot:
    """Structured Git state captured at one point in time."""

    branch: str  # "" when HEAD is detached
    head: str  # abbreviated commit, "" when the repository has no commits
    upstream: str  # "" when no upstream is configured
    ahead: int
    behind: int
    # (porcelain XY status, path) pairs, at most MAX_LISTED_PATHS of them.
    entries: Tuple[Tuple[str, str], ...]
    total_changes: int
    staged: int
    unstaged: int
    untracked: int
    captured_at: str  # ISO-8601 UTC, second precision


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #

def _run_git(cwd: str, args: List[str]) -> Optional[str]:
    """Run a read-only git command; return decoded stdout or None on failure."""
    env = os.environ.copy()
    # Never block on credential prompts, and never take the optional index
    # lock: a snapshot must not interfere with the user's own git commands.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    kwargs: dict = dict(
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=_GIT_TIMEOUT_SECONDS,
        env=env,
    )
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(["git", *args], **kwargs)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("git %s failed: %s", args[0] if args else "", e)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def _parse_branch_header(header: str) -> Tuple[str, str, int, int]:
    """Parse a porcelain v1 ``## ...`` header into (branch, upstream, ahead, behind)."""
    text = header[3:] if header.startswith("## ") else header
    ahead = behind = 0
    if text.endswith("]") and " [" in text:
        text, _, tracking = text.rpartition(" [")
        for part in tracking.rstrip("]").split(","):
            key, _, count = part.strip().partition(" ")
            if count.isdigit():
                if key == "ahead":
                    ahead = int(count)
                elif key == "behind":
                    behind = int(count)
    for prefix in ("No commits yet on ", "Initial commit on "):
        if text.startswith(prefix):
            return text[len(prefix):], "", 0, 0
    if text.startswith("HEAD (no branch)"):
        return "", "", 0, 0
    branch, _, upstream = text.partition("...")
    return branch, upstream, ahead, behind


def capture_git_snapshot(
    workspace: Optional[str], *, now: Optional[datetime] = None
) -> Optional[GitSnapshot]:
    """Capture the Git state of ``workspace``; None when it is not a repository.

    Runs two short read-only git commands with a timeout. Any failure
    (git missing, not a repository, timeout) yields None so the caller
    simply omits the snapshot. Blocking — call it off the event loop
    (``asyncio.to_thread``) from async code.
    """
    if not workspace or not os.path.isdir(workspace):
        return None
    status = _run_git(
        workspace,
        ["status", "--porcelain=v1", "--branch", "-z", "--untracked-files=normal"],
    )
    if status is None:
        return None

    records = status.split("\0")
    branch = upstream = ""
    ahead = behind = 0
    entries: List[Tuple[str, str]] = []
    total = staged = unstaged = untracked = 0
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if record.startswith("## "):
            branch, upstream, ahead, behind = _parse_branch_header(record)
            continue
        if len(record) < 4:
            continue
        xy, path = record[:2], record[3:]
        if "R" in xy or "C" in xy:
            # Renames/copies carry the source path as the next record.
            index += 1
        total += 1
        if xy == "??":
            untracked += 1
        else:
            if xy[0] not in (" ", "?"):
                staged += 1
            if xy[1] not in (" ", "?"):
                unstaged += 1
        if len(entries) < MAX_LISTED_PATHS:
            entries.append((xy, path))

    head = (_run_git(workspace, ["rev-parse", "--short", "HEAD"]) or "").strip()
    captured = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return GitSnapshot(
        branch=branch,
        head=head,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        entries=tuple(entries),
        total_changes=total,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        captured_at=captured.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _quote(value: str) -> str:
    """Serialize one runtime field as a bounded, boundary-safe JSON string."""
    if len(value) > MAX_FIELD_CHARS:
        value = value[:MAX_FIELD_CHARS] + "…"
    encoded = json.dumps(value, ensure_ascii=False)
    for char, escape in _BOUNDARY_ESCAPES.items():
        encoded = encoded.replace(char, escape)
    return encoded


def _summary_lines(snapshot: GitSnapshot) -> List[str]:
    lines = [
        f"branch: {_quote(snapshot.branch)}" if snapshot.branch else "branch: (detached HEAD)",
        f"head: {_quote(snapshot.head)}" if snapshot.head else "head: (no commits)",
    ]
    if snapshot.upstream:
        lines.append(
            f"upstream: {_quote(snapshot.upstream)} "
            f"(ahead {snapshot.ahead}, behind {snapshot.behind})"
        )
    if not snapshot.total_changes:
        lines.append("worktree: clean")
        return lines
    lines.append(
        f"worktree: {snapshot.total_changes} changed path(s); "
        f"{snapshot.staged} staged, {snapshot.unstaged} unstaged, "
        f"{snapshot.untracked} untracked"
    )
    lines.append(
        f"changed paths (first {len(snapshot.entries)} of {snapshot.total_changes}):"
    )
    for xy, path in snapshot.entries:
        # XY comes from git's fixed porcelain alphabet; only the path is
        # user-controlled and therefore quoted.
        lines.append(f"- {xy} {_quote(path)}")
    return lines


def render_git_snapshot_text(snapshot: GitSnapshot) -> str:
    """Render the snapshot user text; the id versions the captured content."""
    summary = _summary_lines(snapshot)
    digest = hashlib.sha256(
        "\n".join([snapshot.captured_at, *summary]).encode("utf-8")
    ).hexdigest()[:12]
    return "\n".join([
        "<system-reminder>",
        f"{GIT_SNAPSHOT_OPEN_PREFIX} source=runtime | snapshot={digest}]",
        "This is runtime context, not a new user request or a replacement for "
        "workspace instructions in system_instructions.",
        "",
        f"GIT SNAPSHOT (captured_at={snapshot.captured_at}; may be stale)",
        *summary,
        "",
        "Recheck the worktree before edits or destructive Git operations.",
        GIT_SNAPSHOT_CLOSE_TAG,
        "</system-reminder>",
    ])


def build_git_snapshot_item(snapshot: GitSnapshot) -> dict:
    """Build a snapshot item for legacy history or content-part merging."""
    return {"role": "user", "content": render_git_snapshot_text(snapshot)}


# --------------------------------------------------------------------------- #
# Detection and history maintenance
# --------------------------------------------------------------------------- #

def is_git_snapshot_text(text: Any) -> bool:
    """Whether ``text`` is, as a whole, one Git snapshot block."""
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    # Accept pre-wrapper snapshots from sessions persisted by older versions.
    return (
        stripped.startswith(f"<system-reminder>\n{GIT_SNAPSHOT_OPEN_PREFIX}")
        and stripped.endswith(f"{GIT_SNAPSHOT_CLOSE_TAG}\n</system-reminder>")
    ) or (
        stripped.startswith(GIT_SNAPSHOT_OPEN_PREFIX)
        and stripped.endswith(GIT_SNAPSHOT_CLOSE_TAG)
    )


def _is_git_snapshot_part(part: Any) -> bool:
    return (
        isinstance(part, dict)
        and part.get("type") in ("input_text", "text")
        and is_git_snapshot_text(part.get("text"))
    )


def is_git_snapshot_item(item: Any) -> bool:
    """Whether ``item`` is a user message consisting only of a Git snapshot.

    Recognize standalone items in both the plain-string and content-part
    shapes, including sessions persisted before content-part merging.
    """
    if not isinstance(item, dict) or item.get("role") != "user":
        return False
    content = item.get("content")
    if isinstance(content, str):
        return is_git_snapshot_text(content)
    if isinstance(content, list) and content:
        return all(_is_git_snapshot_part(part) for part in content)
    return False


def has_git_snapshot(items: Optional[List[Any]]) -> bool:
    """Whether a user item in history carries a snapshot-only content part."""
    for item in items or ():
        if is_git_snapshot_item(item):
            return True
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, list) and any(_is_git_snapshot_part(part) for part in content):
                return True
    return False


def merge_git_snapshot_into_input(user_input: Any, snapshot_item: dict) -> Any:
    """Append a hidden snapshot part to the last user message, like /goal.

    A fresh turn stays a single user message. Preserve earlier items and all
    existing content parts (including images and goal reminders) unchanged.
    """
    snapshot_part = {"type": "input_text", "text": snapshot_item["content"]}
    if isinstance(user_input, str):
        return [{"role": "user", "content": [
            {"type": "input_text", "text": user_input}, snapshot_part,
        ]}]
    if not isinstance(user_input, list):
        return user_input

    items = list(user_input)
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts = [{"type": "input_text", "text": content}]
        elif isinstance(content, list):
            parts = list(content)
        else:
            parts = []
        items[index] = {**item, "content": [*parts, snapshot_part]}
        return items

    items.append({"role": "user", "content": [snapshot_part]})
    return items


def replace_git_snapshot(items: List[Any], snapshot_item: dict) -> List[Any]:
    """Replace old snapshot parts without removing their human messages.

    Legacy standalone items are discarded; new content-part snapshots are
    removed from their containing user messages before merging the refresh.
    """
    kept = []
    for item in items:
        if is_git_snapshot_item(item):
            continue
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, list):
                parts = [part for part in content if not _is_git_snapshot_part(part)]
                if len(parts) != len(content):
                    kept.append({**item, "content": parts})
                    continue
        kept.append(item)
    return merge_git_snapshot_into_input(kept, snapshot_item)
