"""
Proactive Task Models

Data models for task discovery and management.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import json


@dataclass
class Task:
    """
    Task model representing a discovered pending task.
    
    Attributes:
        id: Unique task identifier (UUID)
        title: Task title (brief description)
        description: Detailed task description
        priority: Task priority (high/medium/low)
        status: Task status (pending/in_progress/completed/cancelled)
        needs_confirmation: Whether task needs human confirmation before execution
        source_memories: List of memory file paths where this task was discovered
        created_at: ISO format timestamp when task was created
        updated_at: ISO format timestamp when task was last updated
    """
    
    id: str
    title: str
    description: str
    priority: str  # "high", "medium", "low"
    status: str  # "pending", "in_progress", "completed", "cancelled"
    needs_confirmation: bool
    source_memories: List[str]
    created_at: str
    updated_at: str
    
    def __post_init__(self):
        """Validate task data after initialization."""
        # Validate priority
        valid_priorities = ["high", "medium", "low"]
        if self.priority not in valid_priorities:
            raise ValueError(
                f"Invalid priority '{self.priority}'. Must be one of: {valid_priorities}"
            )
        
        # Validate status
        valid_statuses = ["pending", "in_progress", "completed", "cancelled"]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of: {valid_statuses}"
            )
        
        # Validate lists
        if not isinstance(self.source_memories, list):
            raise ValueError("source_memories must be a list")
        
        # Validate timestamp format (ISO 8601)
        try:
            datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"Invalid created_at timestamp '{self.created_at}'. Must be ISO 8601 format"
            )
    
    @classmethod
    def create(
        cls,
        title: str,
        description: str,
        priority: str,
        needs_confirmation: bool,
        source_memories: List[str],
        task_id: Optional[str] = None,
        status: str = "pending"
    ) -> "Task":
        """
        Create a new Task with auto-generated ID and timestamp.
        
        Args:
            title: Task title
            description: Task description
            priority: Task priority (high/medium/low)
            needs_confirmation: Whether task needs confirmation
            source_memories: List of source memory file paths
            task_id: Optional task ID (will be auto-generated if not provided)
            status: Task status (default: "pending")
            
        Returns:
            Task: New task instance
        """
        task_id = task_id or str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        return cls(
            id=task_id,
            title=title,
            description=description,
            priority=priority,
            status=status,
            needs_confirmation=needs_confirmation,
            source_memories=source_memories,
            created_at=timestamp,
            updated_at=timestamp
        )
    
    def update_status(self, new_status: str) -> None:
        """
        Update task status and timestamp.
        
        Args:
            new_status: New status (pending/in_progress/completed/cancelled)
        """
        valid_statuses = ["pending", "in_progress", "completed", "cancelled"]
        if new_status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{new_status}'. Must be one of: {valid_statuses}"
            )
        
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def to_dict(self) -> dict:
        """
        Convert task to dictionary.
        
        Returns:
            dict: Task data as dictionary
        """
        return asdict(self)
    
    def to_json(self) -> str:
        """
        Convert task to JSON string.
        
        Returns:
            str: Task data as JSON string
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """
        Create Task from dictionary with backward compatibility.
        
        Handles old JSON data by removing deprecated fields and providing
        defaults for missing required fields.
        
        Args:
            data: Task data dictionary
            
        Returns:
            Task: Task instance
        """
        # Remove deprecated fields (if they exist in old data)
        data.pop('category', None)
        data.pop('suggested_actions', None)
        data.pop('confidence', None)
        data.pop('completed_at', None)
        
        # Provide defaults for missing required fields
        data.setdefault('priority', 'medium')
        data.setdefault('needs_confirmation', True)
        data.setdefault('source_memories', [])
        
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Task":
        """
        Create Task from JSON string.
        
        Args:
            json_str: JSON string containing task data
            
        Returns:
            Task: Task instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class TaskList:
    """
    Container for multiple tasks with metadata.
    
    Attributes:
        version: Schema version
        last_updated: ISO format timestamp of last update
        tasks: List of Task objects
    """
    
    version: str = "1.0"
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    tasks: List[Task] = field(default_factory=list)
    
    def add_task(self, task: Task) -> None:
        """
        Add a task to the list.
        
        Args:
            task: Task to add
        """
        self.tasks.append(task)
        self.last_updated = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def remove_task(self, task_id: str) -> bool:
        """
        Remove a task by ID.
        
        Args:
            task_id: ID of task to remove
            
        Returns:
            bool: True if task was removed, False if not found
        """
        original_length = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.id != task_id]
        
        if len(self.tasks) < original_length:
            self.last_updated = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.
        
        Args:
            task_id: ID of task to retrieve
            
        Returns:
            Task if found, None otherwise
        """
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def filter_by_priority(self, priority: str) -> List[Task]:
        """
        Filter tasks by priority.
        
        Args:
            priority: Priority to filter by (high/medium/low)
            
        Returns:
            List of tasks with specified priority
        """
        return [t for t in self.tasks if t.priority == priority]
    
    def filter_by_category(self, category: str) -> List[Task]:
        """
        Filter tasks by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of tasks with specified category
        """
        return [t for t in self.tasks if t.category == category]
    
    def filter_by_status(self, status: str) -> List[Task]:
        """
        Filter tasks by status.
        
        Args:
            status: Status to filter by (pending/in_progress/completed/cancelled)
            
        Returns:
            List of tasks with specified status
        """
        return [t for t in self.tasks if t.status == status]
    
    def filter_by_confidence(self, min_confidence: float) -> List[Task]:
        """
        Filter tasks by minimum confidence score.
        
        Args:
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            List of tasks with confidence >= min_confidence
        """
        return [t for t in self.tasks if t.confidence >= min_confidence]
    
    def sort_by_priority(self) -> List[Task]:
        """
        Sort tasks by priority (high -> medium -> low).
        
        Returns:
            Sorted list of tasks
        """
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(self.tasks, key=lambda t: priority_order.get(t.priority, 3))
    
    def sort_by_confidence(self, reverse: bool = True) -> List[Task]:
        """
        Sort tasks by confidence score.
        
        Args:
            reverse: If True, sort descending (highest first)
            
        Returns:
            Sorted list of tasks
        """
        return sorted(self.tasks, key=lambda t: t.confidence, reverse=reverse)
    
    def to_dict(self) -> dict:
        """
        Convert task list to dictionary.
        
        Returns:
            dict: Task list data as dictionary
        """
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "tasks": [task.to_dict() for task in self.tasks]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """
        Convert task list to JSON string.
        
        Args:
            indent: JSON indentation (default: 2)
            
        Returns:
            str: Task list as JSON string
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TaskList":
        """
        Create TaskList from dictionary.
        
        Args:
            data: Task list data dictionary
            
        Returns:
            TaskList: TaskList instance
        """
        tasks = [Task.from_dict(task_data) for task_data in data.get("tasks", [])]
        return cls(
            version=data.get("version", "1.0"),
            last_updated=data.get("last_updated", datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')),
            tasks=tasks
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "TaskList":
        """
        Create TaskList from JSON string.
        
        Args:
            json_str: JSON string containing task list data
            
        Returns:
            TaskList: TaskList instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def __len__(self) -> int:
        """Return number of tasks."""
        return len(self.tasks)
    
    def __iter__(self):
        """Iterate over tasks."""
        return iter(self.tasks)


@dataclass
class CronTask:
    """
    Crontab task model for scheduled proactive agent execution.
    
    Attributes:
        id: Unique task identifier (UUID)
        name: Task name/description
        cron_expr: Crontab expression (5-field format: minute hour day month weekday)
        instruction: Task instruction passed to ProactiveAgent
        enabled: Whether task is enabled
        created_at: ISO format timestamp when task was created
        updated_at: ISO format timestamp when task was last updated
        last_run: ISO format timestamp of last execution (None if never run)
        next_run: ISO format timestamp of next scheduled execution (None if disabled)
    """
    
    id: str
    name: str
    cron_expr: str
    instruction: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    
    def __post_init__(self):
        """Validate cron task data after initialization."""
        # Validate cron expression format (5 fields)
        fields = self.cron_expr.split()
        if len(fields) != 5:
            raise ValueError(
                f"Invalid cron expression '{self.cron_expr}'. Must have 5 fields: minute hour day month weekday"
            )
        
        # Validate timestamps
        for field_name in ['created_at', 'updated_at']:
            timestamp = getattr(self, field_name)
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                raise ValueError(
                    f"Invalid {field_name} timestamp '{timestamp}'. Must be ISO 8601 format"
                )
        
        # Validate last_run if present
        if self.last_run is not None:
            try:
                datetime.fromisoformat(self.last_run.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                raise ValueError(
                    f"Invalid last_run timestamp '{self.last_run}'. Must be ISO 8601 format"
                )
        
        # Validate next_run if present
        if self.next_run is not None:
            try:
                datetime.fromisoformat(self.next_run.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                raise ValueError(
                    f"Invalid next_run timestamp '{self.next_run}'. Must be ISO 8601 format"
                )
    
    @classmethod
    def create(
        cls,
        name: str,
        cron_expr: str,
        instruction: str,
        enabled: bool = True,
        task_id: Optional[str] = None
    ) -> "CronTask":
        """
        Create a new CronTask with auto-generated ID and timestamp.
        
        Args:
            name: Task name
            cron_expr: Crontab expression (5-field format)
            instruction: Task instruction for ProactiveAgent
            enabled: Whether task is enabled (default: True)
            task_id: Optional task ID (will be auto-generated if not provided)
            
        Returns:
            CronTask: New cron task instance
        """
        task_id = task_id or str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        return cls(
            id=task_id,
            name=name,
            cron_expr=cron_expr,
            instruction=instruction,
            enabled=enabled,
            created_at=timestamp,
            updated_at=timestamp,
            last_run=None,
            next_run=None
        )
    
    def update_timestamps(
        self,
        last_run: Optional[str] = None,
        next_run: Optional[str] = None
    ) -> None:
        """
        Update execution timestamps.
        
        Args:
            last_run: Last execution timestamp
            next_run: Next execution timestamp
        """
        if last_run is not None:
            self.last_run = last_run
        if next_run is not None:
            self.next_run = next_run
        self.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def update(
        self,
        name: Optional[str] = None,
        cron_expr: Optional[str] = None,
        instruction: Optional[str] = None,
        enabled: Optional[bool] = None,
        last_run: Optional[str] = None,
        next_run: Optional[str] = None
    ) -> None:
        """
        Update cron task fields.
        
        Args:
            name: New task name
            cron_expr: New crontab expression
            instruction: New task instruction
            enabled: New enabled status
            last_run: Last execution timestamp (ISO 8601)
            next_run: Next execution timestamp (ISO 8601)
        """
        if name is not None:
            self.name = name
        if cron_expr is not None:
            # Validate new cron expression
            fields = cron_expr.split()
            if len(fields) != 5:
                raise ValueError(
                    f"Invalid cron expression '{cron_expr}'. Must have 5 fields"
                )
            self.cron_expr = cron_expr
        if instruction is not None:
            self.instruction = instruction
        if enabled is not None:
            self.enabled = enabled
        if last_run is not None:
            self.last_run = last_run
        if next_run is not None:
            self.next_run = next_run
        
        self.updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    def to_dict(self) -> dict:
        """
        Convert cron task to dictionary.
        
        Returns:
            dict: Cron task data as dictionary
        """
        return asdict(self)
    
    def to_json(self) -> str:
        """
        Convert cron task to JSON string.
        
        Returns:
            str: Cron task data as JSON string
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "CronTask":
        """
        Create CronTask from dictionary.
        
        Args:
            data: Cron task data dictionary
            
        Returns:
            CronTask: CronTask instance
        """
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "CronTask":
        """
        Create CronTask from JSON string.
        
        Args:
            json_str: JSON string containing cron task data
            
        Returns:
            CronTask: CronTask instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
