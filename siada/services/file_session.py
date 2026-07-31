from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Callable, Awaitable
from datetime import datetime

from agents.memory.session import SessionABC
from siada.foundation.logging import logger
from siada.services.session_signature import compute_last_item_signature

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
        # Tracks the pending IPC injection for cross-session routing.
        # Written by inject_items(), cleared by clear_inject_info().
        # Always read from disk — no in-memory state.
        self._inject_info_file = self.session_folder / "inject_info.json"
        
        # Initialize session file and metadata if not exists
        self._init_session_file()
        self._init_metadata()
        
        # Save project metadata if project_root is provided
        if project_root:
            self._save_project_metadata()

    def _init_session_file(self) -> None:
        """Pre-create the session file (api_history.json) with empty items if it doesn't exist.

        This ensures the session is immediately discoverable by external components
        (e.g. session_management listing) right after construction, rather than
        only after the first write via add_items/inject_items.
        """
        if not self.session_file.exists():
            self._write_session_data([])

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
            logger.warning("Failed to save project metadata: %s", e)
    
    @staticmethod
    def _is_injected(item) -> bool:
        """Check if an item is an injected cross-session message."""
        return isinstance(item, dict) and item.get('_injected') is True

    def _update_metadata(self, items: list) -> None:
        """Update metadata after items are added.
        
        Note: message_count only counts native messages (excludes injected items).
        """
        metadata = self._read_metadata()
        metadata['last_updated'] = datetime.now().isoformat()
        # Only count native messages, exclude injected items
        metadata['message_count'] = sum(
            1 for item in items if not self._is_injected(item)
        )
        
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
        """Write session data to file and update signature snapshot."""
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
        
        # Persist signature snapshot to file after successful write
        native_items = [i for i in items if not self._is_injected(i)]
        sig = compute_last_item_signature(native_items)
        self._write_signature_file(sig, len(native_items))

    def _write_signature_file(self, signature: str, native_count: int) -> None:
        """Persist signature and native item count to a sidecar file."""
        sig_file = self.session_folder / "signature.json"
        temp_file = sig_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"signature": signature, "native_item_count": native_count}, f)
            temp_file.replace(sig_file)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()

    def _read_signature_file(self) -> dict:
        """Read persisted signature from sidecar file.

        Returns:
            dict with keys 'signature' (str) and 'native_item_count' (int).
            Returns defaults if the file does not exist or is unreadable.
        """
        sig_file = self.session_folder / "signature.json"
        if not sig_file.exists():
            return {"signature": "", "native_item_count": 0}
        try:
            with open(sig_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"signature": "", "native_item_count": 0}

    @property
    def last_signature(self) -> str:
        """MD5 signature of the last native item, read from disk."""
        return self._read_signature_file()["signature"]

    @property
    def native_item_count(self) -> int:
        """Count of native (non-injected) items, read from disk."""
        return self._read_signature_file()["native_item_count"]

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the conversation history for this session.

        Injected messages (from cross-session injection) are filtered out.
        Use get_all_items() to include injected messages.

        Args:
            limit: Maximum number of items to retrieve. If None, retrieves all items.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of native input items (excluding injected messages)
        """
        def _get_items_sync():
            with self._lock:
                _t_start = time.perf_counter()
                items = self._read_session_data()
                _t_read = time.perf_counter()
                # Filter out injected messages from other sessions
                native_items = [
                    item for item in items
                    if not self._is_injected(item)
                ]
                _t_filter = time.perf_counter()
                logger.debug(
                    "[PERF][file_session.get_items] raw_items=%d native_items=%d "
                    "read=%.1fms filter=%.1fms total=%.1fms",
                    len(items), len(native_items),
                    (_t_read - _t_start) * 1000,
                    (_t_filter - _t_read) * 1000,
                    (_t_filter - _t_start) * 1000,
                )
                if limit is None:
                    return native_items
                else:
                    return native_items[-limit:] if len(native_items) > limit else native_items

        return await asyncio.to_thread(_get_items_sync)

    async def get_api_messages(self) -> tuple[list[TResponseInputItem] | None, int]:
        """Read the compressed API messages snapshot for this session.

        Reads ``api_messages.json``, which is the post-compaction snapshot
        persisted by ``ApiMessageTransferFilter`` immediately BEFORE each
        LLM call. Its ``last_index`` tracks the index in api_history
        (i.e. ``get_items()`` result) that was last sync'd into the snapshot.

        This is intentionally a thin reader. For the higher-level "what the
        model effectively saw plus the latest unsent turn" view, prefer
        ``get_effective_messages()``.

        Returns:
            Tuple of ``(api_messages, last_index)``:
              * ``api_messages`` — list of compressed items, or ``None`` if
                the file does not exist or is unreadable / malformed.
              * ``last_index`` — last sync'd index in api_history, ``-1`` if
                unknown or unavailable.
        """
        def _read_sync() -> tuple[list[TResponseInputItem] | None, int]:
            api_messages_file = self.session_folder / "api_messages.json"
            if not api_messages_file.exists():
                return None, -1
            try:
                with open(api_messages_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(
                    "read api_messages.json failed (session=%s): %s",
                    self.session_id, e,
                )
                return None, -1

            messages = data.get("api_messages")
            if not isinstance(messages, list):
                return None, -1

            try:
                last_index = int(data.get("last_index", -1))
            except (TypeError, ValueError):
                last_index = -1
            return messages, last_index

        return await asyncio.to_thread(_read_sync)

    async def get_effective_messages(self) -> list[TResponseInputItem]:
        """Return the "effective" message view for this session.

        Combines two on-disk artifacts produced by ``ApiMessageTransferFilter``:
          * ``api_messages.json`` — the post-compaction snapshot of what was
            actually sent to the LLM on the last call (always written BEFORE
            the call, so it lacks the most recent assistant turn).
          * ``api_history.json`` — the full conversation log; the items at
            indices > ``last_index`` are the "delta tail" that was appended
            after the last LLM call (typically the latest assistant /
            function_call / function_call_output trio).

        Resolution order:
          1. If a compressed snapshot exists → return ``snapshot + delta``.
          2. Otherwise → fall back to the raw api_history items
             (legacy / pre-compaction sessions).

        Edge cases:
          * snapshot empty → fall through to history.
          * ``last_index`` out of bounds vs current history → trust the
            snapshot only (no splice; history may have been truncated /
            reset since the snapshot was written).
          * empty delta → snapshot only.

        Injected cross-session items are filtered out (same semantics as
        ``get_items()``).

        Returns:
            Combined list of native input items, ready for downstream
            consumers (memory persistence, replay, debug views, ...).
        """
        history_items = await self.get_items()
        snapshot, last_index = await self.get_api_messages()

        # No snapshot OR empty snapshot → raw history is the best view.
        if not snapshot:
            return list(history_items)

        n_history = len(history_items)
        # Stale / invalid checkpoint → cannot safely splice.
        if last_index < 0 or last_index >= n_history:
            return list(snapshot)

        delta = history_items[last_index + 1:]
        if not delta:
            return list(snapshot)

        return list(snapshot) + list(delta)

    async def get_all_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the full conversation history including injected messages.

        Unlike get_items(), this method returns all messages including those
        injected from other sessions via inject_items().

        Args:
            limit: Maximum number of items to retrieve. If None, retrieves all items.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of all input items including injected messages
        """
        def _get_all_items_sync():
            with self._lock:
                items = self._read_session_data()
                if limit is None:
                    return items
                else:
                    return items[-limit:] if len(items) > limit else items

        return await asyncio.to_thread(_get_all_items_sync)

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

    def inject_items(
        self,
        items: list[TResponseInputItem],
        source_session_id: str,
        position: str = "append",
    ) -> None:
        """Inject external messages from another session into this session's history.

        Injected messages are tagged with metadata and stored inline in api_history.json.
        They are invisible to the agent system (filtered out by get_items()) but can be
        retrieved via get_all_items().

        This is a synchronous method, as the injection caller may operate from a
        different process/context.

        Args:
            items: List of input items to inject
            source_session_id: The session ID that produced these messages
            position: Where to insert items - "append" (end) or "prepend" (beginning)
        """
        if not items:
            return

        with self._lock:
            current_items = self._read_session_data()
            now_iso = datetime.now().isoformat()

            tagged_items = []
            for item in items:
                # Ensure item is a dict so we can add metadata tags
                if not isinstance(item, dict):
                    item = dict(item) if hasattr(item, '__iter__') else {"content": str(item)}
                else:
                    item = dict(item)  # shallow copy to avoid mutating caller's data

                if position == "prepend":
                    seq = len(tagged_items)
                else:
                    seq = len(current_items) + len(tagged_items)

                item['_injected'] = True
                item['_source_session_id'] = source_session_id
                item['_injected_at'] = now_iso
                item['_injected_seq'] = seq
                tagged_items.append(item)

            if position == "prepend":
                merged = tagged_items + current_items
                # Re-calculate _injected_seq for all injected items based on final positions
                seq_counter = 0
                for i, it in enumerate(merged):
                    if self._is_injected(it):
                        it['_injected_seq'] = i
            else:
                merged = current_items + tagged_items

            self._write_session_data(merged)
            self._update_metadata(merged)

            # Persist inject_info so cross-session routing survives restarts.
            # Only append changes the last item; prepend leaves it unchanged.
            if position == "append" and tagged_items:
                last = tagged_items[-1]
                self._write_inject_info(
                    last.get('_source_session_id', ''),
                    last.get('content'),
                )

    def _write_inject_info(self, source_session_id: str, content: object) -> None:
        """Persist IPC injection metadata to inject_info.json atomically.

        Uses tmp-file + os.replace for crash safety; falls back to default=str
        when content contains non JSON-serializable objects. Caller is expected
        to already hold ``self._lock``.
        """
        tmp = self._inject_info_file.with_suffix(".json.tmp")
        try:
            data = {"source_session_id": source_session_id, "content": content}
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    # fsync may fail on some filesystems; best-effort only
                    pass
            os.replace(tmp, self._inject_info_file)
        except Exception as e:
            logger.warning(
                "write inject_info failed (session=%s): %s",
                self.session_id, e,
            )
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def get_inject_info(self) -> Optional[tuple[str, Any]]:
        """Read pending IPC injection metadata from inject_info.json.

        Semantics: when present, the current session has a pending IPC
        injection and the next routing decision should route AWAY from it.

        Returns (source_session_id, content) if a valid inject_info file
        exists; None otherwise. A half-written / corrupt file is treated
        as "no pending info" and silently self-heals by being overwritten
        on the next successful write.
        """
        if not self._inject_info_file.exists():
            return None
        try:
            with open(self._inject_info_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_session_id = data.get("source_session_id", "")
            if not source_session_id:
                return None
            return source_session_id, data.get("content")
        except Exception as e:
            logger.warning(
                "read inject_info failed (session=%s): %s",
                self.session_id, e,
            )
            return None

    def _clear_inject_info_unlocked(self) -> None:
        """Internal helper — caller must hold ``self._lock``."""
        try:
            if self._inject_info_file.exists():
                self._inject_info_file.unlink()
        except Exception as e:
            logger.debug(
                "clear inject_info failed (session=%s): %s",
                self.session_id, e,
            )

    def _sync_inject_info_with_last_unlocked(self, items: list) -> None:
        """Re-sync inject_info.json with the current last item of ``items``.

        inject_info semantically means "the current tail of api_history is an
        injected IPC item".  After any mutation of api_history we must keep
        this invariant in one of two ways:

          * if the new last item is still injected → rewrite inject_info to
            reflect that item (source_session_id may have changed);
          * otherwise → clear inject_info (tail is no longer an injection).

        Caller must hold ``self._lock``.
        """
        if (
            items
            and isinstance(items[-1], dict)
            and items[-1].get("_injected") is True
        ):
            last = items[-1]
            self._write_inject_info(
                last.get("_source_session_id", ""),
                last.get("content"),
            )
        else:
            self._clear_inject_info_unlocked()


    def clear_inject_info(self) -> None:
        """Remove inject_info.json, marking any pending injection as consumed.

        Called in three situations (see module-level design note):
          1. After router has successfully routed away based on this info
             ("injection consumed").
          2. After user explicitly switches INTO this session ("acknowledged";
             prevents a stale injection from re-triggering routing on resume).
          3. After api_history has been mutated via add/pop/clear/reset
             ("data is now stale").
        """
        with self._lock:
            self._clear_inject_info_unlocked()


    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Add new items to the conversation history.

        Args:
            items: List of input items to add to the history
        """
        if not items:
            return

        def _add_items_sync():
            with self._lock:
                _t_start = time.perf_counter()
                current_items = self._read_session_data()
                _t_read = time.perf_counter()
                current_items.extend(items)
                current_items = FileSession._filter_invalid_tool_calls(current_items)
                _t_filter = time.perf_counter()
                self._write_session_data(current_items)
                _t_write = time.perf_counter()
                # Update metadata
                self._update_metadata(current_items)
                _t_metadata = time.perf_counter()
                # Keep inject_info in sync with the new tail. add_items from
                # the agent system normally breaks the "tail is injected"
                # invariant, but we still re-check in case the appended
                # batch happens to end with an injected item.
                self._sync_inject_info_with_last_unlocked(current_items)
                _t_sync_inject = time.perf_counter()
                logger.debug(
                    "[PERF][file_session.add_items] items=%d total_items=%d "
                    "read=%.1fms filter=%.1fms write=%.1fms metadata=%.1fms "
                    "sync_inject=%.1fms total=%.1fms",
                    len(items), len(current_items),
                    (_t_read - _t_start) * 1000,
                    (_t_filter - _t_read) * 1000,
                    (_t_write - _t_filter) * 1000,
                    (_t_metadata - _t_write) * 1000,
                    (_t_sync_inject - _t_metadata) * 1000,
                    (_t_sync_inject - _t_start) * 1000,
                )
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
                # After pop, a previously-hidden injected item may now be
                # the new tail — re-sync accordingly.
                self._sync_inject_info_with_last_unlocked(items)
                return popped_item

        return await asyncio.to_thread(_pop_item_sync)

    async def clear_session(self) -> None:
        """Clear all items for this session."""
        def _clear_session_sync():
            with self._lock:
                if self.session_file.exists():
                    self.session_file.unlink()
                # History wiped — any pending inject_info is stale.
                self._clear_inject_info_unlocked()

        await asyncio.to_thread(_clear_session_sync)

    async def safe_reset_items(self, items: list[TResponseInputItem]) -> None:
        """Reset the conversation history to a specific set of items.

        This method replaces the entire conversation history with the provided items,
        useful for restoring from checkpoints or resetting to a known state.

        Injected messages from the current file are preserved and re-inserted at
        their original positions (using _injected_seq).

        Args:
            items: List of input items to set as the new conversation history
        """
        def _reset_items_sync():
            with self._lock:
                # Preserve injected messages from the current file
                existing_items = self._read_session_data()
                injected_items = [
                    item for item in existing_items
                    if self._is_injected(item)
                ]

                if not injected_items:
                    self._write_session_data(items)
                    self._update_metadata(items)
                    # No injected items preserved — tail cannot be injected.
                    self._sync_inject_info_with_last_unlocked(items)
                    return

                # Re-insert injected messages at their original positions
                merged = list(items)
                for inj in sorted(injected_items, key=lambda x: x.get('_injected_seq', len(merged))):
                    seq = inj.get('_injected_seq', len(merged))
                    insert_pos = max(0, min(seq, len(merged)))
                    merged.insert(insert_pos, inj)

                self._write_session_data(merged)
                self._update_metadata(merged)
                # Re-sync with the new tail — if an injected item ended up
                # at the end after re-insertion, inject_info is refreshed
                # to match it; otherwise it is cleared.
                self._sync_inject_info_with_last_unlocked(merged)

        await asyncio.to_thread(_reset_items_sync)
        
        # Call the hook after items are reset
        if self.on_items_added:
            try:
                await self.on_items_added(items)
            except Exception as e:
                # Hook errors should not affect session operations
                import logging
                logging.debug(f"Error in on_items_added hook: {e}")
