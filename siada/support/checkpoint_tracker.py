import dataclasses
import json
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
        arguments_dict = json.loads(arguments) if arguments else {}

        if function_tool_name == "edit_file":
            command = arguments_dict.get("command", "view")
            # `view`, `create`, `str_replace`, `insert`, `undo_edit`.
            return command
        elif function_tool_name == "run_cmd":
            return arguments_dict.get("command", "")
            # TODO: identify common write commands

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
        arguments_dict = json.loads(arguments) if arguments else {}

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

    def save_checkpoints(self, task_id: str, task_message_state: TaskMessageState):
        """Save checkpoint"""
        # Create checkpoint directory
        checkpoint_dir_path = Path(self.checkpoint_dir)
        checkpoint_dir_path.mkdir(parents=True, exist_ok=True)

        # Extract tool name and arguments from the last message
        function_tool_name = "unknown"
        arguments = ""
        if task_message_state.message_history:
            last_message = task_message_state.message_history[-1]
            # Check if the message is a function tool call by examining its structure
            if isinstance(last_message, dict) and "name" in last_message and "arguments" in last_message:
                function_tool_name = last_message["name"]
                arguments = last_message["arguments"]
            elif hasattr(last_message, 'name') and hasattr(last_message, 'arguments'):
                function_tool_name = last_message.name
                arguments = last_message.arguments

        # Check if we should save checkpoint
        if not self._should_save_checkpoint(function_tool_name, arguments):
            return

        # Get tool placeholder for later use
        tool_place_holder = self._get_tool_placeholder(function_tool_name, arguments)

        snapshot_commit_msg = f"Snapshot for task {task_id} at {datetime.now()} with {function_tool_name}"

        # Get modified files from git service
        modified_file_names = self.git_service.get_modified_files()

        if len(modified_file_names) == 0:
            logger.info("No modified files found, skipping snapshot.")
            return

        last_commit_hash = self.git_service.create_snapshot(snapshot_commit_msg)

        timestamp = datetime.now()
        checkpoint_data = CheckPointData(
            timestamp=timestamp,
            last_commit_hash=last_commit_hash,
            history=task_message_state.message_history,
            use_tool_name=function_tool_name,
            modified_file_names=modified_file_names,
        )
        # get the modified file contents placeholder, join the modified file names, and get the max 50 chars
        modified_file_names_placeholder = "#".join(modified_file_names)
        modified_file_names_placeholder = modified_file_names_placeholder[:50]

        # Build checkpoint file directory and name
        checkpoint_file_name = f"{timestamp.strftime('%Y_%m_%d_%H%M%S')}__{tool_place_holder}__{modified_file_names_placeholder}.json"
        checkpoint_file = checkpoint_dir_path / checkpoint_file_name

        # Write checkpoint data to file
        with open(checkpoint_file, "w", encoding='utf-8') as f:
            json.dump(checkpoint_data.to_dict(), f, ensure_ascii=False, indent=2)


def create_checkpoint_tracker(cwd: str, session_id: str) -> CheckPointTracker:
    try:
        return CheckPointTracker(cwd, session_id)
    except Exception as e:
        logger.error(f"Failed to create checkpoint tracker: {e}")
        return None
