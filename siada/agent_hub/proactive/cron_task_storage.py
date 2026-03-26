"""
Cron Task Storage Module

Provides thread-safe storage for crontab tasks with atomic write operations.
Stores all cron tasks in a single JSON file: ~/.siada-cli/cron_tasks.json
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, List
from threading import Lock
from datetime import datetime, timezone

from siada.agent_hub.proactive.models import CronTask


logger = logging.getLogger(__name__)


class CronTaskStorage:
    """
    Thread-safe storage for crontab tasks.
    
    Stores all cron tasks in a single file: cron_tasks.json
    Located in: ~/.siada-cli/workspace/
    
    Provides atomic write operations using temporary files and rename,
    ensuring data integrity even in case of crashes or concurrent access.
    
    Attributes:
        storage_path: Path to the cron tasks JSON file
        _lock: Thread lock for synchronization
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize cron task storage.
        
        Args:
            storage_path: Path to cron tasks file. If None, uses default
                         (~/.siada-cli/workspace/cron_tasks.json)
        """
        if storage_path is None:
            default_path = Path.home() / ".siada-cli" / "workspace" / "cron_tasks.json"
            storage_path = str(default_path)
        
        self.storage_path = Path(storage_path)
        self._lock = Lock()
        
        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[CronTaskStorage] Initialized with path: {self.storage_path}")
    
    def _build_storage_data(self, tasks: List[CronTask]) -> dict:
        """
        Build storage data structure.
        
        Args:
            tasks: List of CronTask objects
            
        Returns:
            dict: Storage data structure
        """
        return {
            "version": "1.0",
            "last_updated": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "tasks": [task.to_dict() for task in tasks]
        }
    
    def save_all(self, tasks: List[CronTask]) -> bool:
        """
        Save all cron tasks to storage with atomic write.
        
        Uses temporary file + rename to ensure atomic operation.
        Thread-safe through lock.
        
        Args:
            tasks: List of CronTask objects to save
            
        Returns:
            True if save succeeded, False otherwise
        """
        with self._lock:
            try:
                # Build storage data
                data = self._build_storage_data(tasks)
                json_data = json.dumps(data, ensure_ascii=False, indent=2)
                
                # Write to temporary file in the same directory
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self.storage_path.parent,
                    prefix=".cron_tasks_",
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
                    temp_path_obj.replace(self.storage_path)
                    
                    logger.info(
                        f"[CronTaskStorage] Saved {len(tasks)} cron tasks to {self.storage_path}"
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
                logger.error(f"[CronTaskStorage] Failed to save cron tasks: {e}", exc_info=True)
                return False
    
    def load_all(self) -> List[CronTask]:
        """
        Load all cron tasks from storage.
        
        Thread-safe through lock.
        
        Returns:
            List of CronTask objects (empty list if file doesn't exist or error)
        """
        with self._lock:
            try:
                if not self.storage_path.exists():
                    logger.debug(f"[CronTaskStorage] Storage file does not exist: {self.storage_path}")
                    return []
                
                # Read JSON data
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Parse tasks
                tasks = []
                for task_data in data.get("tasks", []):
                    try:
                        task = CronTask.from_dict(task_data)
                        tasks.append(task)
                    except Exception as e:
                        logger.warning(f"[CronTaskStorage] Failed to parse task: {e}")
                        continue
                
                logger.info(
                    f"[CronTaskStorage] Loaded {len(tasks)} cron tasks from {self.storage_path}"
                )
                return tasks
                
            except json.JSONDecodeError as e:
                logger.error(f"[CronTaskStorage] Invalid JSON in storage file: {e}")
                return []
            except Exception as e:
                logger.error(f"[CronTaskStorage] Failed to load cron tasks: {e}", exc_info=True)
                return []
    
    def add(self, task: CronTask) -> bool:
        """
        Add a cron task to storage.
        
        Loads existing tasks, adds the new task, and saves atomically.
        Thread-safe through lock.
        
        Args:
            task: CronTask to add
            
        Returns:
            True if task was added successfully, False otherwise
        """
        try:
            # Load existing tasks (lock is handled by load_all and save_all)
            tasks = self.load_all()
            
            # Check for duplicate ID
            if any(t.id == task.id for t in tasks):
                logger.warning(f"[CronTaskStorage] Task with ID {task.id} already exists")
                return False
            
            # Add task
            tasks.append(task)
            
            # Save updated list
            success = self.save_all(tasks)
            if success:
                logger.info(f"[CronTaskStorage] Added cron task {task.id} ({task.name})")
            return success
            
        except Exception as e:
            logger.error(f"[CronTaskStorage] Failed to add cron task: {e}", exc_info=True)
            return False
    
    def update(self, task_id: str, **updates) -> bool:
        """
        Update a cron task by ID.
        
        Thread-safe through lock.
        
        Args:
            task_id: ID of task to update
            **updates: Fields to update (name, cron_expr, instruction, enabled)
            
        Returns:
            True if task was updated, False if not found or error
        """
        try:
            # Load existing tasks
            tasks = self.load_all()
            
            # Find and update task
            task_found = False
            for task in tasks:
                if task.id == task_id:
                    task.update(**updates)
                    task_found = True
                    break
            
            if not task_found:
                logger.warning(f"[CronTaskStorage] Task {task_id} not found")
                return False
            
            # Save updated list
            success = self.save_all(tasks)
            if success:
                logger.info(f"[CronTaskStorage] Updated cron task {task_id}")
            return success
            
        except Exception as e:
            logger.error(f"[CronTaskStorage] Failed to update cron task: {e}", exc_info=True)
            return False
    
    def delete(self, task_id: str) -> bool:
        """
        Delete a cron task by ID.
        
        Thread-safe through lock.
        
        Args:
            task_id: ID of task to delete
            
        Returns:
            True if task was deleted, False if not found or error
        """
        try:
            # Load existing tasks
            tasks = self.load_all()
            
            # Filter out the task to delete
            original_count = len(tasks)
            tasks = [t for t in tasks if t.id != task_id]
            
            if len(tasks) == original_count:
                logger.warning(f"[CronTaskStorage] Task {task_id} not found")
                return False
            
            # Save updated list
            success = self.save_all(tasks)
            if success:
                logger.info(f"[CronTaskStorage] Deleted cron task {task_id}")
            return success
            
        except Exception as e:
            logger.error(f"[CronTaskStorage] Failed to delete cron task: {e}", exc_info=True)
            return False
    
    def get(self, task_id: str) -> Optional[CronTask]:
        """
        Get a cron task by ID.
        
        Args:
            task_id: ID of task to retrieve
            
        Returns:
            CronTask if found, None otherwise
        """
        tasks = self.load_all()
        for task in tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_enabled(self) -> List[CronTask]:
        """
        Get all enabled cron tasks.
        
        Returns:
            List of enabled CronTask objects
        """
        tasks = self.load_all()
        return [t for t in tasks if t.enabled]
    
    def clear(self) -> bool:
        """
        Clear all cron tasks from storage.
        
        Returns:
            True if storage was cleared, False otherwise
        """
        try:
            return self.save_all([])
        except Exception as e:
            logger.error(f"[CronTaskStorage] Failed to clear storage: {e}", exc_info=True)
            return False
    
    def delete_file(self) -> bool:
        """
        Delete the storage file.
        
        Returns:
            True if file was deleted or doesn't exist, False on error
        """
        with self._lock:
            try:
                if self.storage_path.exists():
                    self.storage_path.unlink()
                    logger.info(f"[CronTaskStorage] Deleted storage file: {self.storage_path}")
                return True
            except Exception as e:
                logger.error(f"[CronTaskStorage] Failed to delete storage file: {e}", exc_info=True)
                return False
    
    def exists(self) -> bool:
        """
        Check if storage file exists.
        
        Returns:
            True if storage file exists, False otherwise
        """
        return self.storage_path.exists()
    
    def count(self) -> int:
        """
        Get the number of cron tasks in storage.
        
        Returns:
            Number of cron tasks
        """
        tasks = self.load_all()
        return len(tasks)
    
    def count_enabled(self) -> int:
        """
        Get the number of enabled cron tasks.
        
        Returns:
            Number of enabled cron tasks
        """
        enabled_tasks = self.get_enabled()
        return len(enabled_tasks)
