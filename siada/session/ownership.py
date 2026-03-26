"""Session ownership management for CLI/Lark mutual exclusion.

Ensures that a session can only be actively used by one channel at a time:
- If Lark is running a task, CLI cannot resume the session
- If CLI has resumed the session, Lark cannot accept new messages for it

Ownership is tracked via `active_owner` field in session metadata.json:
- "lark": Lark agent task is in progress
- "cli": CLI has resumed this session
- None/missing: session is idle, can be claimed by either side
"""

import json
import logging
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Optional

from filelock import FileLock

logger = logging.getLogger(__name__)


class SessionOwner(str, Enum):
    """Who currently owns/controls the session."""
    LARK = "lark"
    CLI = "cli"


class OwnershipError(Exception):
    """Raised when ownership conflict prevents an operation."""
    def __init__(self, message: str, current_owner: Optional[str] = None):
        super().__init__(message)
        self.current_owner = current_owner


class SessionOwnershipManager:
    """Manages session ownership via metadata.json on disk.
    
    Thread/process-safe: uses file locks for atomic read-check-write operations.
    """

    FIELD_ACTIVE_OWNER = "active_owner"
    FIELD_SESSION_SOURCE = "session_source"

    @staticmethod
    def _get_lock(session_dir: Path) -> FileLock:
        """Get a file lock for the session directory."""
        return FileLock(session_dir / "metadata.lock", timeout=5)

    @staticmethod
    def _get_metadata_path(session_dir: Path) -> Path:
        return session_dir / "metadata.json"

    @staticmethod
    def _read_metadata(metadata_path: Path) -> dict:
        if not metadata_path.exists():
            return {}
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def _write_metadata(metadata_path: Path, metadata: dict) -> None:
        temp_file = metadata_path.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            temp_file.replace(metadata_path)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise

    @classmethod
    def get_active_owner(cls, session_dir: Path) -> Optional[str]:
        """Get the current active owner of a session."""
        metadata_path = cls._get_metadata_path(session_dir)
        metadata = cls._read_metadata(metadata_path)
        return metadata.get(cls.FIELD_ACTIVE_OWNER)

    @classmethod
    def set_active_owner(cls, session_dir: Path, owner: Optional[SessionOwner]) -> None:
        """Set the active owner of a session. Pass None to release ownership."""
        metadata_path = cls._get_metadata_path(session_dir)
        metadata = cls._read_metadata(metadata_path)
        if owner is None:
            metadata.pop(cls.FIELD_ACTIVE_OWNER, None)
        else:
            metadata[cls.FIELD_ACTIVE_OWNER] = owner.value
        cls._write_metadata(metadata_path, metadata)
        logger.debug(f"Session ownership set to {owner} for {session_dir.name}")

    @classmethod
    def set_session_source(cls, session_dir: Path, source: SessionOwner) -> None:
        """Record the original source that created this session."""
        metadata_path = cls._get_metadata_path(session_dir)
        metadata = cls._read_metadata(metadata_path)
        metadata[cls.FIELD_SESSION_SOURCE] = source.value
        cls._write_metadata(metadata_path, metadata)

    @classmethod
    def acquire_ownership(
        cls, session_dir: Path, requester: SessionOwner
    ) -> None:
        """Try to acquire ownership. Raises OwnershipError if already owned by another.
        
        Rules:
        - If no active_owner or same owner: grant
        - If different owner: reject with OwnershipError
        
        Uses file lock to prevent TOCTOU race between CLI and Lark.
        """
        lock = cls._get_lock(session_dir)
        with lock:
            current = cls.get_active_owner(session_dir)
            if current is not None and current != requester.value:
                raise OwnershipError(
                    f"Session is currently owned by '{current}', "
                    f"cannot be claimed by '{requester.value}'",
                    current_owner=current,
                )
            cls.set_active_owner(session_dir, requester)

    @classmethod
    def release_ownership(cls, session_dir: Path, owner: SessionOwner) -> None:
        """Release ownership only if current owner matches.
        
        Uses file lock to prevent race with concurrent acquire.
        """
        lock = cls._get_lock(session_dir)
        with lock:
            current = cls.get_active_owner(session_dir)
            if current == owner.value:
                cls.set_active_owner(session_dir, None)
            else:
                logger.debug(
                    f"Skip release: current owner is '{current}', "
                    f"requested release by '{owner.value}'"
                )

    @classmethod
    def is_im_session(cls, session_dir_or_session) -> bool:
        """Check if a session was created by IM (Lark) by reading session_source from metadata.

        Args:
            session_dir_or_session: Either a Path to session directory, or a RunningSession object.
                For RunningSession, extracts session_folder from openai_session automatically.

        Returns:
            True if the session was created by IM (Lark), False otherwise.
        """
        from siada.session.session_models import RunningSession
        if isinstance(session_dir_or_session, RunningSession):
            openai_session = session_dir_or_session.openai_session
            if openai_session and hasattr(openai_session, 'session_folder'):
                session_dir_or_session = openai_session.session_folder
            else:
                return False

        metadata_path = cls._get_metadata_path(session_dir_or_session)
        metadata = cls._read_metadata(metadata_path)
        return metadata.get(cls.FIELD_SESSION_SOURCE) == SessionOwner.LARK.value

    @classmethod
    @contextmanager
    def owned_turn(cls, session_dir: Optional[Path], owner: SessionOwner):
        """Context manager that holds ownership for the duration of a turn.

        Only applies to IM sessions. For non-IM sessions or None session_dir,
        this is a no-op passthrough.

        Raises OwnershipError if the session is owned by another channel.
        """
        if session_dir is None or not cls.is_im_session(session_dir):
            yield
            return
        cls.acquire_ownership(session_dir, owner)
        try:
            yield
        finally:
            cls.release_ownership(session_dir, owner)

    @classmethod
    def release_all_by_owner(cls, sessions_base: Path, owner: SessionOwner) -> int:
        """Release ownership for ALL sessions owned by the given owner under sessions_base.

        Useful for process shutdown cleanup: ensures no stale locks remain
        when a daemon or CLI process is killed.

        Returns the number of sessions released.
        """
        released = 0
        if not sessions_base.exists():
            return released
        for session_dir in sessions_base.iterdir():
            if not session_dir.is_dir():
                continue
            metadata_path = cls._get_metadata_path(session_dir)
            if not metadata_path.exists():
                continue
            try:
                current = cls.get_active_owner(session_dir)
                if current == owner.value:
                    cls.release_ownership(session_dir, owner)
                    released += 1
                    logger.info(
                        f"Released stale {owner.value} ownership for session {session_dir.name}"
                    )
            except Exception as e:
                logger.debug(f"Error releasing ownership for {session_dir.name}: {e}")
        return released

    @classmethod
    def get_session_dir_from_sessions_base(
        cls, sessions_base: Path, session_id: str
    ) -> Path:
        """Helper to construct session directory path."""
        return sessions_base / session_id
