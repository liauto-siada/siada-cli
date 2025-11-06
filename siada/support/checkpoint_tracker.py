import asyncio
import copy
import dataclasses
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
from siada.support.usage_utils import serialize_usage

SUPPORT_CHECKPOINTS_TOOLS = ["edit_file", "run_cmd"]

# Checkpoint cleanup constants
CLEANUP_THRESHOLD_BUFFER = 5  # Trigger cleanup when files exceed max + this value
CLEANUP_BATCH_SIZE = 5  # Number of oldest files to delete in each cleanup

@dataclasses.dataclass
class CheckPointData:
    timestamp: datetime
    last_commit_hash: str
    history: List[TResponseInputItem]
    use_tool_name: str
    modified_file_names: List[str]
    real_api_message: Optional[dict] = None
    usage: Optional[dict] = None
    data: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """Convert checkpoint data to dictionary for JSON serialization"""
        result = {
            'timestamp': self.timestamp.isoformat(),
            'last_commit_hash': self.last_commit_hash,
            'history': self.history,  # TResponseInputItem inherits from TypedDict, already dict-like
            'use_tool_name': self.use_tool_name,
            'modified_file_names': self.modified_file_names,
            'data': self.data
        }
        if self.real_api_message is not None:
            result['real_api_message'] = self.real_api_message
        if self.usage is not None:
            result['usage'] = self.usage
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CheckPointData':
        """Create CheckPointData instance from dictionary"""
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            last_commit_hash=data['last_commit_hash'],
            history=data['history'],
            use_tool_name=data['use_tool_name'],
            modified_file_names=data['modified_file_names'],
            real_api_message=data.get('real_api_message'),
            usage=data.get('usage'),
            data=data.get('data')
        )


class CheckPointTracker:

    def __init__(self, cwd: str, session_id, max_checkpoint_files: int = 50):
        """
        Initialize CheckPointTracker.
        
        Args:
            cwd: Current working directory
            session_id: Session identifier
            max_checkpoint_files: Maximum number of checkpoint files to retain (default: 50)
        """
        self.cwd = cwd
        self.session_id = session_id
        self.max_checkpoint_files = max_checkpoint_files
        self._is_initialized = False  # Track whether start() has been called

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
        """Initialize checkpoint snapshot. This should only be called once per tracker instance."""
        if self._is_initialized:
            logger.debug(f"Checkpoint tracker already initialized for session {self.session_id}")
            return
        
        message = f"start or continue checkpointing for session_id {self.session_id}"
        self.git_service.create_snapshot(message=message)
        self._is_initialized = True

    def create_snapshot(self, message: str) -> str:
        """
        Create a git snapshot with the given message.
        
        Args:
            message: Commit message for the snapshot
            
        Returns:
            Commit hash of the created snapshot
        """
        return self.git_service.create_snapshot(message)

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
        if not task_message_state or not hasattr(task_message_state, 'get_messages'):
            logger.warning("Task message state or get_messages method is invalid.")
            return function_tool_name, arguments

        messages = task_message_state.get_messages()
        if len(messages) >= 2:
            try:
                last_message = messages[-2]
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

    async def _write_checkpoint_and_cleanup_async(self, checkpoint_file: Path, checkpoint_data: CheckPointData):
        """
        Asynchronously write checkpoint data to file and then cleanup old checkpoints.
        This ensures the two operations happen in sequence.
        """
        try:
            # Step 1: Write checkpoint file
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: checkpoint_file.write_text(
                    json.dumps(checkpoint_data.to_dict(), ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
            )
            logger.info(f"Successfully saved checkpoint to {checkpoint_file.name}")
            
            # Step 2: Cleanup old checkpoints after successful write
            await self._cleanup_old_checkpoints_async()
            
        except (OSError, IOError, PermissionError) as e:
            logger.error(f"Failed to write checkpoint file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while saving checkpoint: {e}")

    def _cleanup_old_checkpoints_sync(self):
        """
        Synchronously clean up old checkpoint files when count exceeds limit.
        Delete oldest 5 files when total exceeds max_checkpoint_files + 5.
        Uses filename timestamp for sorting to ensure cross-platform consistency.
        """
        try:
            # Skip cleanup if max_checkpoint_files is disabled (<=0)
            if self.max_checkpoint_files <= 0:
                return
                
            checkpoint_dir_path = Path(self.checkpoint_dir)
            if not checkpoint_dir_path.exists():
                return
            
            # Get all checkpoint files sorted by filename (timestamp is in filename)
            # Filename format: YYYY_MM_DD_HHMMSS__{tool}__{files}.json
            checkpoint_files = sorted(
                checkpoint_dir_path.glob("*.json"),
                key=lambda p: p.name  # Sort by filename, timestamp is lexicographically sortable
            )
            
            total_files = len(checkpoint_files)
            
            # Only cleanup when exceeding threshold (max + CLEANUP_THRESHOLD_BUFFER)
            if total_files > self.max_checkpoint_files + CLEANUP_THRESHOLD_BUFFER:
                files_to_delete = checkpoint_files[:CLEANUP_BATCH_SIZE]  # Delete oldest files in batch
                
                for file_path in files_to_delete:
                    try:
                        file_path.unlink()
                        logger.info(f"Deleted old checkpoint: {file_path.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete checkpoint {file_path.name}: {e}")
                        
        except Exception as e:
            logger.error(f"Error during checkpoint cleanup: {e}")

    async def _cleanup_old_checkpoints_async(self):
        """
        Asynchronously clean up old checkpoint files when count exceeds limit.
        Delete oldest 5 files when total exceeds max_checkpoint_files + 5.
        Uses filename timestamp for sorting to ensure cross-platform consistency.
        """
        try:
            # Skip cleanup if max_checkpoint_files is disabled (<=0)
            if self.max_checkpoint_files <= 0:
                return
                
            checkpoint_dir_path = Path(self.checkpoint_dir)
            if not checkpoint_dir_path.exists():
                return
            
            # Get all checkpoint files sorted by filename (timestamp is in filename)
            # Filename format: YYYY_MM_DD_HHMMSS__{tool}__{files}.json
            checkpoint_files = sorted(
                checkpoint_dir_path.glob("*.json"),
                key=lambda p: p.name  # Sort by filename, timestamp is lexicographically sortable
            )
            
            total_files = len(checkpoint_files)
            
            # Only cleanup when exceeding threshold (max + CLEANUP_THRESHOLD_BUFFER)
            if total_files > self.max_checkpoint_files + CLEANUP_THRESHOLD_BUFFER:
                files_to_delete = checkpoint_files[:CLEANUP_BATCH_SIZE]  # Delete oldest files in batch
                
                loop = asyncio.get_event_loop()
                for file_path in files_to_delete:
                    try:
                        await loop.run_in_executor(None, file_path.unlink)
                        logger.info(f"Deleted old checkpoint: {file_path.name}")
                    except Exception as e:
                        logger.warning(f"Failed to delete checkpoint {file_path.name}: {e}")
                        
        except Exception as e:
            logger.error(f"Error during checkpoint cleanup: {e}")

    def save_checkpoints(self, session_id: str, task_message_state: TaskMessageState, usage=None):
        """
        Save checkpoint with comprehensive error handling
        
        Args:
            session_id: Session identifier
            task_message_state: Task message state containing conversation history
            usage: Optional Usage object to save with checkpoint
        """

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

        # Get RealApiMessage object and serialize it
        real_api_msg = task_message_state_copy._real_messages
        real_api_msg_dict = real_api_msg.to_dict() if real_api_msg else None
        
        # Serialize usage if provided using utility function
        usage_dict = serialize_usage(usage)

        # Use the copied message history instead of the original
        checkpoint_data = CheckPointData(
            timestamp=timestamp,
            last_commit_hash=last_commit_hash,
            history=task_message_state_copy.get_messages(),
            use_tool_name=function_tool_name,
            modified_file_names=modified_file_names,
            real_api_message=real_api_msg_dict,
            usage=usage_dict,
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

        # Schedule write and cleanup task asynchronously (in sequence, non-blocking)
        try:
            asyncio.get_running_loop()
            asyncio.create_task(self._write_checkpoint_and_cleanup_async(checkpoint_file, checkpoint_data))
        except RuntimeError:
            # No running loop, fall back to synchronous write and cleanup
            try:
                checkpoint_file.write_text(
                    json.dumps(checkpoint_data.to_dict(), ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                logger.info(f"Successfully saved checkpoint to {checkpoint_file.name}")
                
                # Execute cleanup synchronously after successful write
                self._cleanup_old_checkpoints_sync()
            except (OSError, IOError, PermissionError) as e:
                logger.error(f"Failed to write checkpoint file: {e}")
            except Exception as e:
                logger.error(f"Unexpected error while saving checkpoint: {e}")

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


def create_checkpoint_tracker(cwd: str, session_id: str, max_checkpoint_files: int = 50) -> CheckPointTracker:
    """
    Create a CheckPointTracker instance.
    
    Args:
        cwd: Current working directory
        session_id: Session identifier
        max_checkpoint_files: Maximum number of checkpoint files to retain (default: 50)
        
    Returns:
        CheckPointTracker instance or None if creation fails
    """
    try:
        return CheckPointTracker(cwd, session_id, max_checkpoint_files)
    except Exception as e:
        logger.error(f"Failed to create checkpoint tracker: {e}")
        return None
