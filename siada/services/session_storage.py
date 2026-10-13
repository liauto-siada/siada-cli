"""Durable primitives shared by FileSession's runtime and history views."""

from __future__ import annotations

import base64
import errno
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from filelock import FileLock


_ACTIVE_TRANSACTIONS = threading.local()


def _active_folders() -> dict[Path, tuple[str, ...]]:
    if not hasattr(_ACTIVE_TRANSACTIONS, "folders"):
        _ACTIVE_TRANSACTIONS.folders = {}
    return _ACTIVE_TRANSACTIONS.folders


class SessionStorageError(ValueError):
    """Session storage is damaged or requires explicit migration."""


class ContextVersionConflict(SessionStorageError):
    """The context changed while a replacement was being prepared."""


def session_storage_lock(folder: Path) -> FileLock:
    """Use the ownership lock too; nested writers in one thread are reentrant."""
    return FileLock(folder.resolve() / "metadata.lock", timeout=5, is_singleton=True)


def atomic_write(path: Path, content: bytes) -> None:
    """Replace a file using a unique, flushed temporary file in its directory."""
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(folder: Path) -> None:
    """Make rename/unlink boundaries durable on supported local filesystems."""
    if os.name == "nt":
        # Windows cannot open a directory handle for flushing; the rename and
        # the file-level flushes above already carry durability there.
        return
    fd = os.open(folder, os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            # Only filesystems that explicitly report directory flushing as
            # unsupported may be skipped; real I/O failures must still surface.
            if error.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL):
                raise
    finally:
        os.close(fd)


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def recover_transaction(folder: Path) -> None:
    """Roll back an interrupted mutation before exposing either file view.

    The caller must hold the shared session lock. Journal removal is the
    commit point; a surviving journal always means the old state wins.
    """
    journal = folder / ".storage-transaction.json"
    if folder.resolve() in _active_folders() or not journal.exists():
        return
    try:
        data = json.loads(journal.read_bytes())
        if (
            not isinstance(data, dict)
            or type(data.get("version")) is not int
            or data["version"] != 1
            or not isinstance(data.get("before"), dict)
        ):
            raise ValueError("invalid transaction journal")
        before = {}
        for name, content in data["before"].items():
            if name not in STORAGE_FILES:
                raise ValueError("invalid transaction target")
            before[name] = None if content is None else base64.b64decode(content, validate=True)
    except (ValueError, TypeError, KeyError) as error:
        raise SessionStorageError("Invalid session transaction journal") from error
    if data.get("project") is not None:
        _recover_project(folder, data["project"], before)
    for name, content in before.items():
        path = folder / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, content)
    journal.unlink()
    sync_directory(folder)


def enlist_project_restore(folder: Path, git_service, rollback_hash: str) -> None:
    """Add Git compensation before any destructive project write occurs."""
    if folder.resolve() not in _active_folders():
        raise SessionStorageError("Project restore requires an active session transaction")
    journal = folder / ".storage-transaction.json"
    data = json.loads(journal.read_bytes())
    data["project"] = {
        "root": str(git_service.project_root),
        "shadow_repo": str(git_service.shadow_repo_dir), "rollback_hash": rollback_hash,
    }
    write_json(journal, data)


def _recover_project(folder: Path, project: dict, before: dict) -> None:
    """Reject journal paths outside this session's recorded workspace."""
    from siada.services.git_service import GitService
    from siada.utils import DirectoryUtils

    try:
        metadata_bytes = before.get("metadata.json") or (folder / "metadata.json").read_bytes()
        metadata = json.loads(metadata_bytes)
        root = Path(metadata["project_root"]).resolve()
        shadow = (Path(DirectoryUtils.get_project_temp_dir(str(root))) / "shadow_repo").resolve()
        if (not isinstance(project, dict) or Path(project["root"]).resolve() != root
                or Path(project["shadow_repo"]).resolve() != shadow
                or not isinstance(project["rollback_hash"], str)
                or len(project["rollback_hash"]) != 40
                or any(char not in "0123456789abcdef" for char in project["rollback_hash"])):
            raise ValueError("invalid project restore identity")
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SessionStorageError("Invalid checkpoint project recovery journal") from error
    try:
        GitService(str(root), str(shadow)).restore_project_from_snapshot(project["rollback_hash"])
    except Exception as error:
        raise SessionStorageError("Checkpoint project rollback failed; journal retained for recovery") from error


STORAGE_FILES = (
    "api_history.json", "api_message.json", "api_messages.json",
    "metadata.json", "signature.json", "inject_info.json",
    "runtime_state.json", "goal.json",
)


@contextmanager
def storage_transaction(folder: Path, files: tuple[str, ...] = STORAGE_FILES) -> Iterator[None]:
    """Compensate failed multi-file writes, including process interruption."""
    if any(name not in STORAGE_FILES for name in files):
        raise ValueError("Unsupported session transaction target")
    with session_storage_lock(folder):
        key = folder.resolve()
        if key in _active_folders():
            if not set(files).issubset(_active_folders()[key]):
                raise SessionStorageError("Nested mutation targets exceed the active transaction")
            yield
            return
        recover_transaction(folder)
        journal = folder / ".storage-transaction.json"
        before = {
            name: base64.b64encode((folder / name).read_bytes()).decode("ascii")
            if (folder / name).exists() else None
            for name in files
        }
        write_json(journal, {"version": 1, "before": before})
        _active_folders()[key] = files
        try:
            yield
        except BaseException:
            del _active_folders()[key]
            recover_transaction(folder)
            raise
        else:
            del _active_folders()[key]
            committed_journal = journal.read_bytes()
            # Legacy writers do not fsync their own files yet. Flush every
            # surviving target before publishing the journal-removal commit.
            try:
                for name in files:
                    path = folder / name
                    if path.exists():
                        # "r+b" keeps the handle writable so Windows can flush it.
                        with path.open("r+b") as stream:
                            os.fsync(stream.fileno())
                sync_directory(folder)
                journal.unlink()
                sync_directory(folder)
            except BaseException:
                # A failed final directory flush must not report failure while
                # leaving the new views committed. Readers still hold this lock.
                if not journal.exists():
                    atomic_write(journal, committed_journal)
                recover_transaction(folder)
                raise


def invalidate_prepared_context(folder: Path, session_id: str) -> None:
    """Fence a prepared context whenever a legacy writer changes its source."""
    path = folder / "api_message.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_bytes())
        if (
            not isinstance(data, dict)
            or data.get("session_id") != session_id
            or type(data.get("format_version")) is not int
            or data["format_version"] != 1
            or type(data.get("context_version")) is not int
            or data["context_version"] < 0
        ):
            raise ValueError("invalid prepared context")
    except (OSError, ValueError, TypeError) as error:
        raise SessionStorageError("Cannot invalidate damaged prepared context") from error
    data["preparation_invalidated"] = True
    data["context_version"] += 1
    write_json(path, data)
