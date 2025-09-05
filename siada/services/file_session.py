from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from agents.memory.session import SessionABC

if TYPE_CHECKING:
    from agents.items import TResponseInputItem


class FileSession(SessionABC):
    """File-based implementation of session storage.

    This implementation stores conversation history in JSON files.
    Each session is stored as a separate file in the specified directory.
    """

    def __init__(
        self,
        session_id: str,
        sessions_dir: str | Path = ".siada_sessions",
    ):
        """Initialize the file session.

        Args:
            session_id: Unique identifier for the conversation session
            sessions_dir: Directory to store session files. Defaults to '.siada_sessions'
        """
        self.session_id = session_id
        self.sessions_dir = Path(sessions_dir)
        self._lock = threading.Lock()
        
        # Create session-specific directory
        self.session_folder = self.sessions_dir / session_id
        self.session_folder.mkdir(parents=True, exist_ok=True)
        
        # Session file path: session_dir/session_id/api_history.json
        self.session_file = self.session_folder / "api_history.json"

    @classmethod
    def from_file(cls, session_file: str | Path) -> "FileSession":
        """Create a FileSession instance from an existing session file.

        Args:
            session_file: Path to an existing api_history.json file to load from

        Returns:
            FileSession instance initialized from the existing file

        Raises:
            FileNotFoundError: If the session file doesn't exist
            ValueError: If the session file is not api_history.json or missing session_id
        """
        session_file = Path(session_file)
        if not session_file.exists():
            raise FileNotFoundError(f"Session file not found: {session_file}")
        
        if session_file.name != "api_history.json":
            raise ValueError(f"Expected api_history.json, got {session_file.name}")
        
        # Get session_id from parent folder name
        session_id = session_file.parent.name
        
        # Try to read session_id from file content as verification
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                file_session_id = data.get('session_id')
                if file_session_id and file_session_id != session_id:
                    raise ValueError(f"Session ID mismatch: folder={session_id}, file={file_session_id}")
        except (json.JSONDecodeError, IOError):
            # File might be corrupted, but we can still use folder name
            pass
        
        # Create instance with extracted session_id
        instance = cls.__new__(cls)
        instance.session_id = session_id
        instance.session_folder = session_file.parent
        instance.sessions_dir = session_file.parent.parent
        instance.session_file = session_file
        instance._lock = threading.Lock()
        
        return instance

    def _read_session_data(self) -> list[TResponseInputItem]:
        """Read session data from file."""
        if not self.session_file.exists():
            return []
        
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('items', [])
        except (json.JSONDecodeError, IOError):
            # Return empty list if file is corrupted or unreadable
            return []

    def _write_session_data(self, items: list[TResponseInputItem]) -> None:
        """Write session data to file."""
        session_data = {
            'session_id': self.session_id,
            'items': items
        }
        
        # Write to temporary file first, then rename for atomic operation
        temp_file = self.session_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            # Atomic rename
            temp_file.replace(self.session_file)
        except Exception:
            # Clean up temp file if something went wrong
            if temp_file.exists():
                temp_file.unlink()
            raise

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the conversation history for this session.

        Args:
            limit: Maximum number of items to retrieve. If None, retrieves all items.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of input items representing the conversation history
        """
        def _get_items_sync():
            with self._lock:
                items = self._read_session_data()
                
                if limit is None:
                    return items
                else:
                    # Return the latest N items in chronological order
                    return items[-limit:] if len(items) > limit else items

        return await asyncio.to_thread(_get_items_sync)

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Add new items to the conversation history.

        Args:
            items: List of input items to add to the history
        """
        if not items:
            return

        def _add_items_sync():
            with self._lock:
                current_items = self._read_session_data()
                current_items.extend(items)
                self._write_session_data(current_items)

        await asyncio.to_thread(_add_items_sync)

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recent item from the session.

        Returns:
            The most recent item if it exists, None if the session is empty
        """
        def _pop_item_sync():
            with self._lock:
                items = self._read_session_data()
                
                if not items:
                    return None
                
                # Remove and return the last item
                popped_item = items.pop()
                self._write_session_data(items)
                
                return popped_item

        return await asyncio.to_thread(_pop_item_sync)

    async def clear_session(self) -> None:
        """Clear all items for this session."""
        def _clear_session_sync():
            with self._lock:
                if self.session_file.exists():
                    self.session_file.unlink()

        await asyncio.to_thread(_clear_session_sync)

    async def reset_items(self, items: list[TResponseInputItem]) -> None:
        """Reset the conversation history to a specific set of items.

        This method replaces the entire conversation history with the provided items,
        useful for restoring from checkpoints or resetting to a known state.

        Args:
            items: List of input items to set as the new conversation history
        """
        def _reset_items_sync():
            with self._lock:
                self._write_session_data(items)

        await asyncio.to_thread(_reset_items_sync)
