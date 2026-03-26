"""
Task Storage Module

Provides thread-safe storage for task lists with atomic write operations.
Stores tasks in daily files with date suffixes (tasks_YYYY-MM-DD.json).
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional
from threading import Lock
from datetime import datetime, timezone

from siada.agent_hub.proactive.models import TaskList, Task


logger = logging.getLogger(__name__)


class TaskStorage:
    """
    Thread-safe storage for task lists with daily file rotation.
    
    Stores tasks in separate files for each day: tasks_YYYY-MM-DD.json
    Located in: ~/.siada-cli/workspace/task/
    
    Provides atomic write operations using temporary files and rename,
    ensuring data integrity even in case of crashes or concurrent access.
    
    Attributes:
        storage_dir: Directory containing all task files
        _lock: Thread lock for synchronization
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize task storage.
        
        Args:
            storage_dir: Directory for task files. If None, uses default
                        (~/.siada-cli/workspace/task/)
        """
        if storage_dir is None:
            default_dir = Path.home() / ".siada-cli" / "workspace" / "task"
            storage_dir = str(default_dir)
        
        self.storage_dir = Path(storage_dir)
        self._lock = Lock()
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[TaskStorage] Initialized with directory: {self.storage_dir}")
    
    def _get_storage_path(self, date: Optional[str] = None) -> Path:
        """
        Get storage path for a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format. If None, uses today.
            
        Returns:
            Path to the task file for the specified date
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        return self.storage_dir / f"tasks_{date}.json"
    
    def save(self, task_list: TaskList, date: Optional[str] = None) -> bool:
        """
        Save task list to storage with atomic write.
        
        Uses temporary file + rename to ensure atomic operation.
        Thread-safe through lock.
        
        Args:
            task_list: TaskList to save
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            True if save succeeded, False otherwise
        """
        with self._lock:
            try:
                storage_path = self._get_storage_path(date)
                
                # Convert task list to JSON
                json_data = task_list.to_json(indent=2)
                
                # Write to temporary file in the same directory
                # This ensures rename is atomic (same filesystem)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.storage_dir,
                    prefix=".tasks_",
                    suffix=".tmp"
                )
                
                try:
                    # Write JSON data to temporary file
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        f.write(json_data)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure data is written to disk
                    
                    # Atomic rename (replaces existing file if present)
                    temp_path_obj = Path(temp_path)
                    temp_path_obj.replace(storage_path)
                    
                    logger.info(
                        f"[TaskStorage] Saved {len(task_list)} tasks to {storage_path}"
                    )
                    return True
                    
                except Exception as e:
                    # Clean up temporary file on error
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                    raise e
                    
            except Exception as e:
                logger.error(f"[TaskStorage] Failed to save task list: {e}", exc_info=True)
                return False
    
    def load(self, date: Optional[str] = None) -> Optional[TaskList]:
        """
        Load task list from storage for a specific date.
        
        Thread-safe through lock.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            TaskList if file exists and is valid, None otherwise
        """
        with self._lock:
            try:
                storage_path = self._get_storage_path(date)
                
                if not storage_path.exists():
                    logger.debug(f"[TaskStorage] Storage file does not exist: {storage_path}")
                    return None
                
                # Read JSON data
                with open(storage_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                
                # Parse and return task list
                task_list = TaskList.from_json(json_data)
                
                logger.info(
                    f"[TaskStorage] Loaded {len(task_list)} tasks from {storage_path}"
                )
                return task_list
                
            except json.JSONDecodeError as e:
                logger.error(f"[TaskStorage] Invalid JSON in storage file: {e}")
                return None
            except Exception as e:
                logger.error(f"[TaskStorage] Failed to load task list: {e}", exc_info=True)
                return None
    
    def add_task(self, task: Task, date: Optional[str] = None) -> bool:
        """
        Add a task to today's storage.
        
        Loads existing task list, adds the task, and saves atomically.
        Thread-safe through lock.
        
        Args:
            task: Task to add
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            True if task was added successfully, False otherwise
        """
        with self._lock:
            try:
                storage_path = self._get_storage_path(date)
                
                # Load existing task list or create new one (within lock)
                if not storage_path.exists():
                    task_list = TaskList()
                else:
                    with open(storage_path, 'r', encoding='utf-8') as f:
                        json_data = f.read()
                    task_list = TaskList.from_json(json_data)
                
                # Add task
                task_list.add_task(task)
                
                # Save updated list (within lock)
                json_data = task_list.to_json(indent=2)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.storage_dir,
                    prefix=".tasks_",
                    suffix=".tmp"
                )
                
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        f.write(json_data)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    Path(temp_path).replace(storage_path)
                    logger.info(f"[TaskStorage] Added task {task.id} to {storage_path}")
                    return True
                    
                except Exception as e:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                    raise e
                
            except Exception as e:
                logger.error(f"[TaskStorage] Failed to add task: {e}", exc_info=True)
                return False
    
    def remove_task(self, task_id: str, date: Optional[str] = None) -> bool:
        """
        Remove a task from storage by ID for a specific date.
        
        Thread-safe through lock.
        
        Args:
            task_id: ID of task to remove
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            True if task was removed, False if not found or error
        """
        with self._lock:
            try:
                storage_path = self._get_storage_path(date)
                
                # Load existing task list (within lock)
                if not storage_path.exists():
                    logger.warning(f"[TaskStorage] No tasks to remove (file does not exist)")
                    return False
                
                with open(storage_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                task_list = TaskList.from_json(json_data)
                
                # Remove task
                removed = task_list.remove_task(task_id)
                
                if not removed:
                    logger.warning(f"[TaskStorage] Task {task_id} not found")
                    return False
                
                # Save updated list (within lock)
                json_data = task_list.to_json(indent=2)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.storage_dir,
                    prefix=".tasks_",
                    suffix=".tmp"
                )
                
                try:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        f.write(json_data)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    Path(temp_path).replace(storage_path)
                    logger.info(f"[TaskStorage] Removed task {task_id} from {storage_path}")
                    return True
                    
                except Exception as e:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                    raise e
                
            except Exception as e:
                logger.error(f"[TaskStorage] Failed to remove task: {e}", exc_info=True)
                return False
    
    def get_task(self, task_id: str, date: Optional[str] = None) -> Optional[Task]:
        """
        Get a task by ID for a specific date.
        
        Args:
            task_id: ID of task to retrieve
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            Task if found, None otherwise
        """
        task_list = self.load(date)
        if task_list is None:
            return None
        
        return task_list.get_task(task_id)
    
    def clear(self, date: Optional[str] = None) -> bool:
        """
        Clear all tasks from storage for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            True if storage was cleared, False otherwise
        """
        try:
            # Save empty task list
            empty_list = TaskList()
            return self.save(empty_list, date)
            
        except Exception as e:
            logger.error(f"[TaskStorage] Failed to clear storage: {e}", exc_info=True)
            return False
    
    def delete(self, date: Optional[str] = None) -> bool:
        """
        Delete the storage file for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            True if file was deleted, False otherwise
        """
        with self._lock:
            try:
                storage_path = self._get_storage_path(date)
                if storage_path.exists():
                    storage_path.unlink()
                    logger.info(f"[TaskStorage] Deleted storage file: {storage_path}")
                    return True
                else:
                    logger.debug(f"[TaskStorage] Storage file does not exist: {storage_path}")
                    return True  # Already deleted
                    
            except Exception as e:
                logger.error(f"[TaskStorage] Failed to delete storage file: {e}", exc_info=True)
                return False
    
    def exists(self, date: Optional[str] = None) -> bool:
        """
        Check if storage file exists for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            True if storage file exists, False otherwise
        """
        storage_path = self._get_storage_path(date)
        return storage_path.exists()
    
    def get_task_count(self, date: Optional[str] = None) -> int:
        """
        Get the number of tasks in storage for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            Number of tasks, or 0 if storage is empty or error
        """
        task_list = self.load(date)
        if task_list is None:
            return 0
        return len(task_list)
    
    def filter_by_priority(self, priority: str, date: Optional[str] = None) -> list[Task]:
        """
        Get tasks filtered by priority for a specific date.
        
        Args:
            priority: Priority to filter by (high/medium/low)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            List of tasks with specified priority
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.filter_by_priority(priority)
    
    def filter_by_category(self, category: str, date: Optional[str] = None) -> list[Task]:
        """
        Get tasks filtered by category for a specific date.
        
        Args:
            category: Category to filter by
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            List of tasks with specified category
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.filter_by_category(category)
    
    def filter_by_status(self, status: str, date: Optional[str] = None) -> list[Task]:
        """
        Get tasks filtered by status for a specific date.
        
        Args:
            status: Status to filter by (pending/in_progress/completed/cancelled)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            List of tasks with specified status
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.filter_by_status(status)
    
    def filter_by_confidence(self, min_confidence: float, date: Optional[str] = None) -> list[Task]:
        """
        Get tasks filtered by minimum confidence for a specific date.
        
        Args:
            min_confidence: Minimum confidence threshold
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            List of tasks with confidence >= min_confidence
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.filter_by_confidence(min_confidence)
    
    def get_sorted_by_priority(self, date: Optional[str] = None) -> list[Task]:
        """
        Get all tasks sorted by priority for a specific date.
        
        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.
        
        Returns:
            List of tasks sorted by priority (high -> medium -> low)
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.sort_by_priority()
    
    def get_sorted_by_confidence(self, reverse: bool = True, date: Optional[str] = None) -> list[Task]:
        """
        Get all tasks sorted by confidence for a specific date.
        
        Args:
            reverse: If True, sort descending (highest first)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            List of tasks sorted by confidence
        """
        task_list = self.load(date)
        if task_list is None:
            return []
        
        return task_list.sort_by_confidence(reverse=reverse)
