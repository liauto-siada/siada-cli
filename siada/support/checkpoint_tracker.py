import asyncio
import copy
import dataclasses
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agents import TResponseInputItem
from siada.services.git_service import GitService
from siada.session.task_message_state import TaskMessageState
from siada.foundation.logging import logger
from siada.utils import DirectoryUtils

SUPPORT_CHECKPOINTS_TOOLS = ["edit_file", "run_cmd"]

@dataclasses.dataclass
class CheckPointData:
    timestamp: datetime
    last_commit_hash: str
    history: List[TResponseInputItem]
    use_tool_name: str
    modified_file_names: List[str]
    data: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """Convert checkpoint data to dictionary for JSON serialization"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'last_commit_hash': self.last_commit_hash,
            'history': self.history,  # TResponseInputItem inherits from TypedDict, already dict-like
            'use_tool_name': self.use_tool_name,
            'modified_file_names': self.modified_file_names,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CheckPointData':
        """Create CheckPointData instance from dictionary"""
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            last_commit_hash=data['last_commit_hash'],
            history=data['history'],
            use_tool_name=data['use_tool_name'],
            modified_file_names=data['modified_file_names'],
            data=data.get('data')
        )


class CheckPointTracker:

    def __init__(self, cwd: str, session_id):
        self.cwd = cwd
        self.session_id = session_id

        project_temp_dir = Path(DirectoryUtils.get_project_temp_dir(self.cwd))
        self.shadow_repo_dir = str(project_temp_dir / "shadow_repo")
        self.checkpoint_dir = str(
            Path(DirectoryUtils.get_project_checkpoint_dir(self.cwd)) / self.session_id
        )

        self.git_service = GitService(cwd, self.shadow_repo_dir)
        self.git_service.initialize()

    def _get_tool_placeholder(self, function_tool_name: str, arguments: str) -> Optional[str]:
        """
        Get tool placeholder based on function tool name and arguments.
        
        Args:
            function_tool_name: Name of the function tool
            arguments: JSON string of function arguments
            
        Returns:
            Tool placeholder string or None
        """
        try:
            arguments_dict = json.loads(arguments) if arguments else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse arguments JSON in _get_tool_placeholder: {e}")
            arguments_dict = {}

        if function_tool_name == "edit_file":
            command = arguments_dict.get("command", "view")
            # `view`, `create`, `str_replace`, `insert`, `undo_edit`.
            return command
        elif function_tool_name == "run_cmd":
            return "command"

        return None

    def _should_save_checkpoint(self, function_tool_name: str, arguments: str) -> bool:
        """
        Determine whether to save a checkpoint based on tool name and arguments.
        
        Args:
            function_tool_name: Name of the function tool
            arguments: JSON string of function arguments
            
        Returns:
            True if checkpoint should be saved, False otherwise
        """
        # Check if tool is supported for checkpointing
        if function_tool_name not in SUPPORT_CHECKPOINTS_TOOLS:
            logger.debug(f"Tool {function_tool_name} is not supported for checkpointing.")
            return False

        # Parse arguments for tool-specific logic
        try:
            arguments_dict = json.loads(arguments) if arguments else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse arguments JSON: {e}. Treating as empty dict.")
            arguments_dict = {}

        # Tool-specific logic
        if function_tool_name == "edit_file":
            command = arguments_dict.get("command", "view")
            # Skip view commands as they don't modify files
            if command == "view":
                logger.debug("View command, skipping checkpoint.")
                return False

        return True

    def start(self):
        message = f"start or continue checkpointing for session_id {self.session_id}"
        self.git_service.create_snapshot(message=message)

    def get_checkpoint_data_by_file_name(self, file_name: str) -> Optional[CheckPointData]:
        """
        Get checkpoint data by file name.

        Args:
            file_name: Name of the checkpoint file

        Returns:
            CheckPointData object or None if not found
        """
        checkpoint_file = Path(self.checkpoint_dir) / file_name
        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, "r", encoding='utf-8') as f:
            checkpoint_data = CheckPointData.from_dict(json.load(f))
        return checkpoint_data

    def _extract_tool_info_from_message(self, task_message_state: TaskMessageState) -> tuple[str, str]:
        """
        Extract tool name and arguments from the last message in task message state.
        
        Args:
            task_message_state: The task message state containing message history
            
        Returns:
            Tuple of (function_tool_name, arguments)
        """
        function_tool_name = "unknown"
        arguments = ""

        # Validate message history exists and is not empty
        if not task_message_state or not hasattr(task_message_state, 'message_history'):
            logger.warning("Task message state or message history is invalid.")
            return function_tool_name, arguments

        if len(task_message_state.message_history) >= 2:
            try:
                last_message = task_message_state.message_history[-2]
                # Check if the message is a function tool call by examining its structure
                if isinstance(last_message, dict) and "name" in last_message and "arguments" in last_message:
                    # Validate types before assignment
                    function_tool_name = str(last_message.get("name", "unknown"))
                    arguments = str(last_message.get("arguments", ""))
                elif hasattr(last_message, 'name') and hasattr(last_message, 'arguments'):
                    function_tool_name = str(getattr(last_message, 'name', 'unknown'))
                    arguments = str(getattr(last_message, 'arguments', ''))
            except (IndexError, TypeError, AttributeError) as e:
                logger.warning(f"Failed to extract tool information from message history: {e}")
                # Return defaults

        return function_tool_name, arguments

    async def _write_checkpoint_file_async(self, checkpoint_file: Path, checkpoint_data: CheckPointData):
        """Asynchronously write checkpoint data to file."""
        try:
            # Run the file writing operation in an executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: checkpoint_file.write_text(
                    json.dumps(checkpoint_data.to_dict(), ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
            )
            logger.info(f"Successfully saved checkpoint to {checkpoint_file.name}")
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to write checkpoint file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while saving checkpoint: {e}")

    def save_checkpoints(self, session_id: str, task_message_state: TaskMessageState):
        """Save checkpoint with comprehensive error handling"""

        # Create a copy of task_message_state to avoid modifying the original
        task_message_state_copy = copy.deepcopy(task_message_state)

        # Extract tool name and arguments from the copied message state
        function_tool_name, arguments = self._extract_tool_info_from_message(task_message_state_copy)

        # Check if we should save checkpoint
        if not self._should_save_checkpoint(function_tool_name, arguments):
            return

        try:
            # Create checkpoint directory
            checkpoint_dir_path = Path(self.checkpoint_dir)
            checkpoint_dir_path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create checkpoint directory: {e}")
            return

        # Get tool placeholder for later use
        tool_place_holder = self._get_tool_placeholder(function_tool_name, arguments)
        # Handle None case for tool_place_holder
        if tool_place_holder is None:
            tool_place_holder = "UNKNOWN"

        timestamp = datetime.now()
        try:
            # Get modified files from git service
            modified_file_names = self.git_service.get_modified_files()
        except Exception as e:
            logger.error(f"Failed to get modified files from git service: {e}")
            return

        if len(modified_file_names) == 0:
            logger.info("No modified files found, skipping snapshot.")
            return

        try:
            snapshot_commit_msg = f"snapshot for session: {session_id} at {timestamp.strftime('%Y_%m_%d_%H%M%S')} with {function_tool_name}"
            last_commit_hash = self.git_service.create_snapshot(snapshot_commit_msg)
        except Exception as e:
            logger.error(f"Failed to create git snapshot: {e}")
            return

        # Use the copied message history instead of the original
        checkpoint_data = CheckPointData(
            timestamp=timestamp,
            last_commit_hash=last_commit_hash,
            history=task_message_state_copy.message_history,
            use_tool_name=function_tool_name,
            modified_file_names=modified_file_names,
        )

        # Sanitize and limit file names for the filename
        modified_file_names_placeholder = "#".join(modified_file_names)
        # Remove potentially problematic characters from filename
        modified_file_names_placeholder = re.sub(r'[<>:"/\\|?*]', '_', modified_file_names_placeholder)

        # Only add truncation indicator if the filename was actually truncated
        if len(modified_file_names_placeholder) > 47:
            modified_file_names_placeholder = f"{modified_file_names_placeholder[:47]}_truncated"

        # Build checkpoint file directory and name
        checkpoint_file_name = f"{timestamp.strftime('%Y_%m_%d_%H%M%S')}__{tool_place_holder.upper()}__{modified_file_names_placeholder}.json"

        checkpoint_file = checkpoint_dir_path / checkpoint_file_name

        # Write checkpoint data to file asynchronously
        # Create and run the async task without blocking
        try:
            # Check if there's already an event loop running
            try:
                asyncio.get_running_loop()
                # Schedule the async write operation as a task
                asyncio.create_task(self._write_checkpoint_file_async(checkpoint_file, checkpoint_data))
            except RuntimeError:
                # No event loop is running, create a new one
                asyncio.run(self._write_checkpoint_file_async(checkpoint_file, checkpoint_data))
        except Exception as e:
            logger.error(f"Failed to initiate async checkpoint write: {e}")
            return

    def _clean_commit_hash(self, hash_str: str) -> str:
        """
        Helper method to clean commit hashes that might have a "HEAD " prefix.
        Used for backward compatibility with old tasks that stored hashes with the prefix.
        
        Args:
            hash_str: Commit hash string that may have "HEAD " prefix
            
        Returns:
            Clean commit hash without the prefix
        """
        return hash_str[5:] if hash_str.startswith("HEAD ") else hash_str

    def get_diff_set_hunks(self, lhs_hash: str, rhs_hash: Optional[str] = None) -> str:
        """
        Get diff between commits in git hunks format.
        Similar to TypeScript getDiffSet but returns hunks format instead of file-by-file data.
        
        Args:
            lhs_hash: Base commit hash (or with "HEAD " prefix for backward compatibility)
            rhs_hash: Optional target commit hash. If None, compare with working directory
            
        Returns:
            Standard git diff output with hunks format
            
        Raises:
            RuntimeError: If git operations fail or repository is not initialized
        """
        start_time = time.time()

        # Clean commit hashes to handle backward compatibility
        clean_lhs = self._clean_commit_hash(lhs_hash)
        clean_rhs = self._clean_commit_hash(rhs_hash) if rhs_hash else None

        logger.info(f"Getting diff between commits: {clean_lhs or 'initial'} -> {clean_rhs or 'working directory'}")

        try:
            if clean_rhs:
                # Compare between two specific commits
                # Use clean_rhs as target commit and clean_lhs as base commit
                diff_output = self.git_service.get_snapshot_diff(clean_rhs, clean_lhs)
            else:
                # Compare commit with working directory
                # Use clean_lhs as target commit, base_commit=None means compare with working directory
                diff_output = self.git_service.get_snapshot_diff(clean_lhs, None)

            duration_ms = round((time.time() - start_time) * 1000)
            logger.info(f"Diff generation completed in {duration_ms}ms")

            return diff_output

        except Exception as e:
            logger.error(f"Failed to get diff set hunks: {e}")
            raise RuntimeError(f"Failed to get diff set hunks: {e}")


def create_checkpoint_tracker(cwd: str, session_id: str) -> CheckPointTracker:
    try:
        return CheckPointTracker(cwd, session_id)
    except Exception as e:
        logger.error(f"Failed to create checkpoint tracker: {e}")
        return None
