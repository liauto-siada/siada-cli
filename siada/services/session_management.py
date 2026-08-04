"""
Session management service.
Responsible for listing, loading, and deleting sessions.
"""

import json
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from siada.utils import DirectoryUtils
from siada.foundation.logging import logger


@dataclass
class SessionInfo:
    """Summary information for a session."""
    session_id: str
    session_path: Path
    created_at: str
    last_updated: str
    message_count: int
    first_user_message: str
    project_root: str  # Project root path
    project_name: str  # Project name
    model_name: Optional[str] = None
    index: int = 0  # Display index (sorted by time)


@dataclass
class SessionData:
    """Complete session data."""
    session_id: str
    items: List[dict]  # items in api_history.json
    metadata: dict
    api_messages: Optional[List[dict]] = None  # compressed messages in api_messages.json
    api_messages_tokens: Optional[int] = None  # tokens_count at save time, restored to usage on resume
    last_index: int = -1  # last_index for incremental update tracking
    last_signature: str = ""  # last_signature for incremental update tracking
    session_path: Optional[Path] = None  # Session directory path
    project_root: Optional[str] = None  # Project root path that the session belongs to


class SessionManager:
    """Session manager."""

    def __init__(self, project_root: str):
        """
        Initialize the session manager.

        Args:
            project_root: Project root directory
        """
        self.project_root = project_root
        self.sessions_dir = Path(DirectoryUtils.get_global_sessions_dir(project_root))
        self.project_name = Path(project_root).name  # Get project name from path
    
    def list_sessions(self, scope: str = 'current') -> List[SessionInfo]:
        """
        List available sessions.

        Args:
            scope: 'current' to list only current project sessions,
                   'all' to list sessions across all projects

        Returns:
            List of session info sorted by time (oldest first, newest has the highest index)
        """
        if scope == 'all':
            return self._list_all_projects_sessions()
        else:
            return self._list_current_project_sessions()
    
    def _list_current_project_sessions(self) -> List[SessionInfo]:
        """List sessions for the current project."""
        sessions = []
        
        if not self.sessions_dir.exists():
            return sessions
        
        # Iterate over all session directories
        for session_dir in self.sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            
            session_id = session_dir.name
            api_history_file = session_dir / "api_history.json"
            metadata_file = session_dir / "metadata.json"
            
            # At least api_history.json is required
            if not api_history_file.exists():
                continue
            
            try:
                # Read metadata
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                else:
                    # If no metadata file, extract from api_history.json
                    with open(api_history_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    metadata = self._extract_metadata_from_history(session_id, data.get('items', []))
                
                session_info = SessionInfo(
                    session_id=session_id,
                    session_path=session_dir,
                    created_at=metadata.get('created_at', ''),
                    last_updated=metadata.get('last_updated', ''),
                    message_count=metadata.get('message_count', 0),
                    first_user_message=self._strip_task_tags(metadata.get('first_user_message') or 'Untitled Session'),
                    project_root=self.project_root,
                    project_name=self.project_name,
                    model_name=metadata.get('model_name')
                )
                sessions.append(session_info)
                
            except Exception as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                continue
        
        # Sort by creation time
        sessions.sort(key=lambda s: s.created_at)
        
        # Assign index numbers (1-based)
        for idx, session in enumerate(sessions, 1):
            session.index = idx
        
        logger.info(f"Found {len(sessions)} sessions in {self.sessions_dir}")
        return sessions
    
    def _list_all_projects_sessions(self) -> List[SessionInfo]:
        """List sessions across all projects."""
        all_sessions = []
        global_temp_dir = Path(DirectoryUtils.get_global_temp_dir())
        
        if not global_temp_dir.exists():
            return all_sessions
        
        # Iterate over all project hash directories
        for project_dir in global_temp_dir.iterdir():
            if not project_dir.is_dir():
                continue
            
            sessions_dir = project_dir / "sessions"
            if not sessions_dir.exists():
                continue
            
            # Load project metadata
            project_metadata = self._load_project_metadata(project_dir)
            project_root = project_metadata.get('project_root', 'Unknown')
            project_name = project_metadata.get('project_name', Path(project_root).name if project_root != 'Unknown' else 'Unknown')
            
            # Iterate over all sessions for this project
            for session_dir in sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                
                session_id = session_dir.name
                api_history_file = session_dir / "api_history.json"
                metadata_file = session_dir / "metadata.json"
                
                if not api_history_file.exists():
                    continue
                
                try:
                    # Read metadata
                    if metadata_file.exists():
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    else:
                        with open(api_history_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        metadata = self._extract_metadata_from_history(session_id, data.get('items', []))
                    
                    session_info = SessionInfo(
                        session_id=session_id,
                        session_path=session_dir,
                        created_at=metadata.get('created_at', ''),
                        last_updated=metadata.get('last_updated', ''),
                        message_count=metadata.get('message_count', 0),
                        first_user_message=self._strip_task_tags(metadata.get('first_user_message') or 'Untitled Session'),
                        project_root=project_root,
                        project_name=project_name,
                        model_name=metadata.get('model_name')
                    )
                    all_sessions.append(session_info)
                    
                except Exception as e:
                    logger.warning(f"Failed to load session {session_id} from {project_name}: {e}")
                    continue
        
        # Sort by creation time
        all_sessions.sort(key=lambda s: s.created_at)
        
        # Assign index numbers (1-based)
        for idx, session in enumerate(all_sessions, 1):
            session.index = idx
        
        logger.info(f"Found {len(all_sessions)} sessions across all projects")
        return all_sessions
    
    def find_session(self, identifier: str, scope: str = 'all') -> Optional[SessionInfo]:
        """
        Find a specific session.

        Args:
            identifier: Session identifier ("latest", an index number, or a session_id)
            scope: 'current' to search only the current project,
                   'all' to search across all projects

        Returns:
            Matching session info, or None if not found
        """
        # First search in current project
        sessions = self.list_sessions(scope='current')
        
        if not sessions:
            sessions = []
        
        # Handle "latest"
        if identifier.lower() == 'latest':
            # Skip empty placeholder sessions: every process eagerly creates a
            # session directory at startup, so the process doing the resume (and
            # any aborted run) leaves behind a newer 0-message session that would
            # otherwise win "latest" and resume an empty history — losing the
            # conversation and forcing a full refresh on the next LLM call.
            for session in reversed(sessions):
                if session.message_count > 0:
                    return session
            return sessions[-1] if sessions else None
        
        # Try as index number
        try:
            index = int(identifier)
            if 1 <= index <= len(sessions):
                return sessions[index - 1]
        except ValueError:
            pass
        
        # Try as session_id (in current project)
        for session in sessions:
            if session.session_id == identifier or session.session_id.startswith(identifier):
                return session
        
        # If not found in current project and scope='all', search in all projects
        if scope == 'all':
            all_sessions = self.list_sessions(scope='all')
            for session in all_sessions:
                if session.session_id == identifier or session.session_id.startswith(identifier):
                    return session
        
        return None
    
    def load_session(self, session_id: str, session_path: Optional[Path] = None) -> SessionData:
        """
        Load complete session data.

        Args:
            session_id: Session ID
            session_path: Session directory path (optional; used directly if provided,
                          otherwise the current project directory is searched)

        Returns:
            Complete session data

        Raises:
            FileNotFoundError: Session does not exist
        """
        if session_path:
            session_dir = session_path
        else:
            session_dir = self.sessions_dir / session_id
        
        if not session_dir.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        
        api_history_file = session_dir / "api_history.json"
        metadata_file = session_dir / "metadata.json"
        api_messages_file = session_dir / "api_messages.json"
        
        if not api_history_file.exists():
            raise FileNotFoundError(f"Session history file not found: {api_history_file}")
        
        try:
            # Load full history
            with open(api_history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # Load metadata
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = self._extract_metadata_from_history(
                    session_id, 
                    history_data.get('items', [])
                )
            
            # Load compressed messages (if present)
            api_messages = None
            api_messages_tokens = None
            if api_messages_file.exists():
                with open(api_messages_file, 'r', encoding='utf-8') as f:
                    api_messages_data = json.load(f)
                    api_messages = api_messages_data.get('api_messages', [])
                    api_messages_tokens = api_messages_data.get('tokens_count') or None

            session_data = SessionData(
                session_id=session_id,
                items=history_data.get('items', []),
                metadata=metadata,
                api_messages=api_messages,
                api_messages_tokens=api_messages_tokens,
                last_index=api_messages_data.get('last_index', -1) if api_messages_file.exists() else -1,
                last_signature=api_messages_data.get('last_signature', '') if api_messages_file.exists() else '',
                session_path=session_dir,
            )
            
            logger.info(f"Loaded session {session_id} with {len(session_data.items)} items")
            return session_data
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            raise
    
    @staticmethod
    def resolve_session_path(workspace: str, session_id: str) -> Path:
        """
        Resolve the on-disk session directory path for a given workspace + session id.

        Centralizes the "<global sessions dir>/<session_id>" convention so callers
        don't have to repeat the path assembly and Path import.
        """
        return Path(DirectoryUtils.get_global_sessions_dir(workspace)) / session_id

    @staticmethod
    def resolve_api_messages_file(workspace: str, session_id: str) -> Path:
        """Resolve the api_messages.json path for a given workspace + session id."""
        return SessionManager.resolve_session_path(workspace, session_id) / "api_messages.json"

    @staticmethod
    def sync_api_messages(
        session_path: Path,
        session_id: str,
        api_messages: List[dict],
        tokens_count: int = 0,
        last_index: int = -1,
        last_signature: str = "",
    ) -> None:
        """
        Write (overwrite) api_messages.json with the provided real API messages and tracking info.

        Used after checkpoint undo/restore to persist the restored in-memory state to disk.

        Args:
            session_path: Path to the session directory
            session_id: Session ID (written into the JSON payload)
            api_messages: List of real API message dicts to persist
            tokens_count: Token count at the time of this save
            last_index: Last processed message index for incremental tracking
            last_signature: Last processed message signature for incremental tracking
        """
        api_messages_file = session_path / "api_messages.json"
        api_messages_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(api_messages_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "session_id": session_id,
                        "tokens_count": tokens_count,
                        "last_index": last_index,
                        "last_signature": last_signature,
                        "api_messages": api_messages,
                    },
                    f,
                    ensure_ascii=False,
                    indent=4,
                )
            logger.info(f"Synced api_messages.json for session {session_id}")
        except OSError as e:
            logger.error(f"Failed to sync api_messages.json for session {session_id}: {e}")
            raise

    @staticmethod
    def update_api_messages_tracking(session_path: Path, last_index: int, last_signature: str) -> None:
        """Update last_index and last_signature in api_messages.json"""
        api_messages_file = session_path / "api_messages.json"
        if not api_messages_file.exists():
            return
        try:
            with open(api_messages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['last_index'] = last_index
            data['last_signature'] = last_signature
            with open(api_messages_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"Updated api_messages.json: last_index={last_index}")
        except Exception as e:
            logger.warning(f"Failed to update api_messages.json: {e}")

    def delete_session(self, session_id: str) -> None:
        """
        Delete a session.

        Args:
            session_id: Session ID
        """
        session_dir = self.sessions_dir / session_id
        
        if not session_dir.exists():
            logger.warning(f"Session directory not found: {session_dir}")
            return
        
        try:
            import shutil
            shutil.rmtree(session_dir)
            logger.info(f"Deleted session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise
    
    def _load_project_metadata(self, project_dir: Path) -> dict:
        """
        Load project metadata.

        Args:
            project_dir: Project directory (hash directory)

        Returns:
            Project metadata dict
        """
        metadata_file = project_dir / "project_metadata.json"
        
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load project metadata from {metadata_file}: {e}")
        
        # Return default value
        return {
            'project_root': 'Unknown',
            'project_name': 'Unknown',
            'created_at': datetime.now().isoformat()
        }
    
    def _save_project_metadata(self, project_dir: Path, project_root: str) -> None:
        """
        Save project metadata.

        Args:
            project_dir: Project directory (hash directory)
            project_root: Project root path
        """
        metadata_file = project_dir / "project_metadata.json"
        
        metadata = {
            'project_root': project_root,
            'project_name': Path(project_root).name,
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat()
        }
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved project metadata to {metadata_file}")
        except Exception as e:
            logger.warning(f"Failed to save project metadata to {metadata_file}: {e}")
    
    def _strip_task_tags(self, text: str) -> str:
        """Strip the <task>...</task> wrapper added by the agent."""
        import re
        text = re.sub(r'^\s*<task>\s*', '', text)
        text = re.sub(r'\s*</task>.*$', '', text, flags=re.DOTALL)
        return text.strip()

    def _extract_metadata_from_history(self, session_id: str, items: List[dict]) -> dict:
        """Extract metadata from session history items."""
        first_user_message = "Untitled Session"
        
        for item in items:
            if item.get('role') == 'user':
                content = item.get('content', '')
                if isinstance(content, str):
                    first_user_message = self._strip_task_tags(content)[:100]
                    break
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            first_user_message = self._strip_task_tags(part.get('text', ''))[:100]
                            break
                    if first_user_message != "Untitled Session":
                        break
        
        # Try to get timestamp from filesystem
        session_dir = self.sessions_dir / session_id
        if session_dir.exists():
            stat = session_dir.stat()
            created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
            last_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()
        else:
            now = datetime.now().isoformat()
            created_at = now
            last_updated = now
        
        return {
            'session_id': session_id,
            'created_at': created_at,
            'last_updated': last_updated,
            'message_count': len(items),
            'first_user_message': first_user_message
        }
