import json
import os
from datetime import datetime
import pathlib
from typing import List, Optional, Dict, Any

from siada.utils import DirectoryUtils
from siada.foundation.logging import logger


class CheckpointFile:
    """Checkpoint file information class"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self._parse_filename()
        self._data = None
    
    def _parse_filename(self):
        """Parse filename to get basic information"""
        # Filename format: {timestamp}__{tool_placeholder}__{modified_file_names_placeholder}.json
        name_without_ext = self.file_name.replace('.json', '')
        parts = name_without_ext.split('__', 2)
        
        if len(parts) >= 3:
            self.timestamp_str = parts[0]
            self.tool_placeholder = parts[1]
            self.modified_files_placeholder = parts[2]
        else:
            self.timestamp_str = ""
            self.tool_placeholder = ""
            self.modified_files_placeholder = ""
    
    @property
    def timestamp(self) -> Optional[datetime]:
        """Get timestamp"""
        try:
            return datetime.strptime(self.timestamp_str, '%Y%m%d%H%M%S')
        except ValueError:
            return None
    
    def load_data(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint file data"""
        if self._data is not None:
            return self._data
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
            return self._data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load checkpoint file {self.file_path}: {e}")
            return None
    
    def matches_query(self, query: str) -> bool:
        """Check if matches query string (prefix matching)"""
        if not query:
            return True
        
        query_lower = query.lower()
        
        if query_lower in self.file_name.lower():
            return True
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        data = self.load_data()
        return {
            'file_path': self.file_path,
            'file_name': self.file_name,
            'timestamp_str': self.timestamp_str,
            'tool_placeholder': self.tool_placeholder,
            'modified_files_placeholder': self.modified_files_placeholder,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'data': data
        }


class CheckPointRecommendEngine:
    """Checkpoint file search service"""

    def __init__(self, cwd: str):
        self.cwd = cwd

        # Calculate checkpoint directory path, referring to checkpoint_tracker.py logic
        self.checkpoint_dir = pathlib.Path(DirectoryUtils.get_project_checkpoint_dir(self.cwd))
    def get_checkpoint_dir(self) -> str:
        """Get checkpoint directory path"""
        return str(self.checkpoint_dir)

    def list_checkpoint_files(self, session_id: str) -> List[CheckpointFile]:
        """List all checkpoint files"""
        checkpoint_files = []

        real_checkpoint_dir = self.checkpoint_dir / session_id

        if not real_checkpoint_dir.exists():
            logger.info(f"Checkpoint directory does not exist: {real_checkpoint_dir}")
            return checkpoint_files

        try:
            for file_path in real_checkpoint_dir.glob("*.json"):
                if file_path.is_file():
                    checkpoint_files.append(CheckpointFile(str(file_path)))
        except Exception as e:
            logger.error(f"Error listing checkpoint files: {e}")

        # Sort by timestamp (newest first)
        checkpoint_files.sort(key=lambda x: x.timestamp or datetime.min, reverse=True)

        return checkpoint_files

    def _is_complete_file_path(self, path: str) -> bool:
        """
        Check if path corresponds to a complete existing file

        Args:
            path: Path to check (without @ prefix)

        Returns:
            bool: True if path points to an existing file
        """
        import os

        if not path:
            return False

        # Check in all search directories
        full_path = os.path.join(self.checkpoint_dir, path)
        if os.path.isfile(full_path):
            return True

        return False

    def get_suggestions(
        self, session_id: str, query: str = "", limit: Optional[int] = None
    ) -> List[CheckpointFile]:
        """
        Search checkpoint files

        Args:
            query: Query string, supports searching filenames, tool names, modified filenames, history content, etc.
            limit: Limit on number of results to return

        Returns:
            List of matching checkpoint files, sorted by timestamp in descending order
        """
        real_checkpoint_dir = self.checkpoint_dir / session_id
        if not real_checkpoint_dir.exists():
            logger.info(f"Checkpoint directory does not exist: {real_checkpoint_dir}")
            return []

        all_files = self.list_checkpoint_files(session_id)

        if not query:
            # If no query condition, return all files
            matched_files = all_files
        else:
            # Filter matching files
            matched_files = [f for f in all_files if f.matches_query(query)]

        # Apply quantity limit
        if limit is not None and limit > 0:
            matched_files = matched_files[:limit]

        return matched_files


def create_checkpoint_recommend_engine(cwd: str) -> CheckPointRecommendEngine:
    """Create checkpoint service instance"""
    try:
        return CheckPointRecommendEngine(cwd)
    except Exception as e:
        logger.error(f"Failed to create checkpoint service: {e}")
        return None
