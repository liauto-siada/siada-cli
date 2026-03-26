from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Callable, Awaitable
from datetime import datetime

from agents.memory.session import SessionABC

if TYPE_CHECKING:
    from agents.items import TResponseInputItem


class FileSession(SessionABC):
    """File-based implementation of session storage.

    This implementation stores conversation history in JSON files.
    Each session is stored as a separate file in the specified directory.
    
    File structure:
    - sessions_dir/<session_id>/api_history.json      # 完整对话历史
    - sessions_dir/<session_id>/api_messages.json     # 压缩后的消息（由 ApiMessageTransferFilter 管理）
    - sessions_dir/<session_id>/metadata.json         # 会话元数据
    """

    def __init__(
        self,
        session_id: str,
        sessions_dir: str | Path = ".siada_sessions",
        on_items_added: Optional[Callable[[list], Awaitable[None]]] = None,
        project_root: Optional[str] = None,
    ):
        """Initialize the file session.

        Args:
            session_id: Unique identifier for the conversation session
            sessions_dir: Directory to store session files. Defaults to '.siada_sessions'
            on_items_added: Optional async callback function called after items are added to session
            project_root: Project root directory for metadata storage
        """
        self.session_id = session_id
        self.sessions_dir = Path(sessions_dir)
        self._lock = threading.Lock()
        self.on_items_added = on_items_added
        self.project_root = project_root
        
        # Create session-specific directory
        self.session_folder = self.sessions_dir / session_id
        self.session_folder.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.session_file = self.session_folder / "api_history.json"
        self.metadata_file = self.session_folder / "metadata.json"
        
        # Initialize metadata if not exists
        self._init_metadata()
        
        # Save project metadata if project_root is provided
        if project_root:
            self._save_project_metadata()

    def _init_metadata(self) -> None:
        """Initialize metadata file if it doesn't exist."""
        if not self.metadata_file.exists():
            metadata = {
                'session_id': self.session_id,
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat(),
                'message_count': 0,
                'first_user_message': None,
                'model_name': None,
                'project_root': None
            }
            self._write_metadata(metadata)
    
    def _read_metadata(self) -> dict:
        """Read metadata from file."""
        if not self.metadata_file.exists():
            self._init_metadata()
        
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Return default metadata if file is corrupted
            return {
                'session_id': self.session_id,
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat(),
                'message_count': 0
            }
    
    def _write_metadata(self, metadata: dict) -> None:
        """Write metadata to file."""
        temp_file = self.metadata_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.metadata_file)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def _save_project_metadata(self) -> None:
        """Save project metadata to parent directory."""
        if not self.project_root:
            return
        
        # Get project directory (parent of sessions directory)
        project_dir = self.sessions_dir.parent
        metadata_file = project_dir / "project_metadata.json"
        
        # Check if already exists and update last_accessed
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    existing_metadata = json.load(f)
                existing_metadata['last_accessed'] = datetime.now().isoformat()
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_metadata, f, indent=2, ensure_ascii=False)
                return
            except Exception:
                pass  # Fall through to create new
        
        # Create new metadata
        metadata = {
            'project_root': self.project_root,
            'project_name': Path(self.project_root).name,
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat()
        }
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Log warning but don't fail session creation
            print(f"Warning: Failed to save project metadata: {e}")
    
    def _update_metadata(self, items: list) -> None:
        """Update metadata after items are added."""
        metadata = self._read_metadata()
        metadata['last_updated'] = datetime.now().isoformat()
        metadata['message_count'] = len(items)
        
        # Extract first user message if not set
        if not metadata.get('first_user_message'):
            for item in items:
                if item.get('role') == 'user':
                    content = item.get('content', '')
                    if isinstance(content, str):
                        metadata['first_user_message'] = content[:100]
                        break
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get('type') == 'text':
                                metadata['first_user_message'] = part.get('text', '')[:100]
                                break
                        if metadata.get('first_user_message'):
                            break
        
        self._write_metadata(metadata)

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
        instance.metadata_file = session_file.parent / "metadata.json"
        instance._lock = threading.Lock()
        instance.on_items_added = None
        
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

    @staticmethod
    def _filter_invalid_tool_calls(items: list) -> list:
        """Filter out the last function_call if its arguments are invalid JSON, along with its output."""
        import json as _json
        # Find the last function_call from the tail
        for i in range(len(items) - 1, -1, -1):
            item = items[i]
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            # Found the last function_call - check if arguments are valid JSON
            if not isinstance(item.get("arguments"), str):
                break
            try:
                _json.loads(item["arguments"])
            except (_json.JSONDecodeError, ValueError):
                # Invalid - remove this function_call and any following function_call_output with same call_id
                call_id = item.get("call_id")
                return [
                    x for x in items[:i]
                    if not (isinstance(x, dict) and x.get("type") == "function_call_output" and x.get("call_id") == call_id)
                ] + [
                    x for x in items[i + 1:]
                    if not (isinstance(x, dict) and x.get("type") == "function_call_output" and x.get("call_id") == call_id)
                ]
            break
        return items

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
                current_items = FileSession._filter_invalid_tool_calls(current_items)
                self._write_session_data(current_items)
                # Update metadata
                self._update_metadata(current_items)
                return current_items

        updated_items = await asyncio.to_thread(_add_items_sync)
        
        # Call the hook after items are added
        if self.on_items_added:
            try:
                await self.on_items_added(items)
            except Exception as e:
                # Hook errors should not affect session operations
                import logging
                logging.debug(f"Error in on_items_added hook: {e}")

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
                # Update metadata
                self._update_metadata(items)

        await asyncio.to_thread(_reset_items_sync)
        
        # Call the hook after items are reset
        if self.on_items_added:
            try:
                await self.on_items_added(items)
            except Exception as e:
                # Hook errors should not affect session operations
                import logging
                logging.debug(f"Error in on_items_added hook: {e}")
