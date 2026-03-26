"""
Crontab Task Management Tool

Unified tool for managing crontab scheduled tasks through different actions.
Supports create, update, delete, and list operations.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from agents import function_tool

from siada.agent_hub.proactive.models import CronTask
from siada.agent_hub.proactive.cron_task_storage import CronTaskStorage


logger = logging.getLogger(__name__)


# Signal file path for notifying scheduler to reload
SIGNAL_FILE = Path.home() / ".siada-cli" / "cron_tasks.reload"


# Tool documentation
MANAGE_CRON_TASK_DOCS = """Manage crontab scheduled tasks (create, update, delete, list).

Unified tool for managing periodic scheduled tasks executed by ProactiveAgent.

Args:
    action: Operation type - "create", "update", "delete", or "list"
    task_id: Task ID (required for update/delete)
    name: Task name (required for create, optional for update)
    cron_expr: Crontab expression in 5-field format (required for create, optional for update)
        Examples: "0 9 * * *" (daily 9AM), "*/15 * * * *" (every 15min), "0 9 * * 1-5" (weekday 9AM)
    instruction: Task instruction for ProactiveAgent (required for create, optional for update)
    enabled: Enable/disable task (optional, default True)
    enabled_only: Show only enabled tasks (for list action, default False)
    sort_by: Sort field - "name", "created_at", or "next_run" (for list action, default "next_run")

Returns:
    - create/update: JSON of created/updated task
    - delete: Success message with task ID and name
    - list: Formatted table of tasks

Examples:
    # Create daily report task
    manage_cron_task(action="create", name="Daily Report", 
                     cron_expr="0 9 * * 1-5", instruction="Generate daily summary")
    
    # Update task schedule
    manage_cron_task(action="update", task_id="abc-123", cron_expr="0 18 * * *")
    
    # Disable task
    manage_cron_task(action="update", task_id="abc-123", enabled=False)
    
    # Delete task
    manage_cron_task(action="delete", task_id="abc-123")
    
    # List enabled tasks
    manage_cron_task(action="list", enabled_only=True, sort_by="next_run")
"""


def _validate_cron_expr(cron_expr: str) -> bool:
    """
    Validate crontab expression using APScheduler's CronTrigger.
    
    Args:
        cron_expr: Crontab expression in 5-field format
        
    Returns:
        True if valid, raises ValueError if invalid
    """
    try:
        # Try to create a CronTrigger to validate the expression
        CronTrigger.from_crontab(cron_expr)
        return True
    except Exception as e:
        raise ValueError(f"Invalid cron expression '{cron_expr}': {e}")


def _notify_scheduler() -> None:
    """
    Notify scheduler to reload cron tasks by creating signal file.
    """
    try:
        SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SIGNAL_FILE.touch()
        logger.info(f"[manage_cron_task] Created signal file: {SIGNAL_FILE}")
    except Exception as e:
        logger.warning(f"[manage_cron_task] Failed to create signal file: {e}")


def _calculate_next_run(cron_expr: str) -> Optional[str]:
    """
    Calculate next run time for a cron expression.
    
    Args:
        cron_expr: Crontab expression
        
    Returns:
        ISO 8601 formatted next run time, or None if calculation fails
    """
    try:
        trigger = CronTrigger.from_crontab(cron_expr)
        now = datetime.now(timezone.utc)
        next_time = trigger.get_next_fire_time(None, now)
        if next_time:
            return next_time.isoformat().replace('+00:00', 'Z')
        return None
    except Exception as e:
        logger.warning(f"[manage_cron_task] Failed to calculate next run: {e}")
        return None


def _format_task_list(tasks: List[CronTask], sort_by: str = "next_run") -> str:
    """
    Format task list for display.
    
    Args:
        tasks: List of CronTask objects
        sort_by: Field to sort by (name, created_at, next_run)
        
    Returns:
        Formatted table string
    """
    if not tasks:
        return "No cron tasks found."
    
    # Sort tasks
    if sort_by == "name":
        tasks = sorted(tasks, key=lambda t: t.name.lower())
    elif sort_by == "created_at":
        tasks = sorted(tasks, key=lambda t: t.created_at)
    elif sort_by == "next_run":
        # Calculate next_run for sorting
        tasks_with_next = []
        for task in tasks:
            next_run = _calculate_next_run(task.cron_expr) if task.enabled else None
            tasks_with_next.append((task, next_run or "9999"))  # Disabled tasks go last
        tasks_with_next.sort(key=lambda x: x[1])
        tasks = [t for t, _ in tasks_with_next]
    
    # Build table
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'ID':<38} {'Name':<20} {'Cron Expression':<15} {'Status':<8} {'Next Run':<20}")
    lines.append("=" * 100)
    
    for task in tasks:
        status = "Enabled" if task.enabled else "Disabled"
        next_run = _calculate_next_run(task.cron_expr) if task.enabled else "N/A"
        if next_run and next_run != "N/A":
            # Format to readable time
            try:
                dt = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                next_run = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        
        lines.append(
            f"{task.id:<38} {task.name[:20]:<20} {task.cron_expr:<15} {status:<8} {next_run:<20}"
        )
    
    lines.append("=" * 100)
    lines.append(f"Total: {len(tasks)} task(s)")
    
    return "\n".join(lines)


def manage_cron_task_impl(
    action: str,
    task_id: Optional[str] = None,
    name: Optional[str] = None,
    cron_expr: Optional[str] = None,
    instruction: Optional[str] = None,
    enabled: Optional[bool] = None,
    enabled_only: bool = False,
    sort_by: str = "next_run",
    storage_path: Optional[str] = None
) -> str:
    """
    Implementation layer for cron task management.
    
    Args:
        action: Operation type (create/update/delete/list)
        task_id: Task ID (required for update/delete)
        name: Task name (required for create, optional for update)
        cron_expr: Crontab expression in 5-field format (required for create, optional for update)
        instruction: Task instruction for ProactiveAgent (required for create, optional for update)
        enabled: Whether task is enabled (optional for create/update, default True)
        enabled_only: Show only enabled tasks (for list action)
        sort_by: Sort field for list action (name/created_at/next_run, default next_run)
        storage_path: Custom storage path (for testing)
        
    Returns:
        Result message or formatted data based on action
        
    Raises:
        ValueError: For invalid parameters or operations
    """
    # Initialize storage
    storage = CronTaskStorage(storage_path) if storage_path else CronTaskStorage()
    
    # Validate action
    valid_actions = ["create", "update", "delete", "list"]
    if action not in valid_actions:
        raise ValueError(f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}")
    
    # CREATE operation
    if action == "create":
        # Validate required parameters
        if not name:
            raise ValueError("Parameter 'name' is required for create action")
        if not cron_expr:
            raise ValueError("Parameter 'cron_expr' is required for create action")
        if not instruction:
            raise ValueError("Parameter 'instruction' is required for create action")
        
        # Validate cron expression
        _validate_cron_expr(cron_expr)
        
        # Create task
        task = CronTask.create(
            name=name,
            cron_expr=cron_expr,
            instruction=instruction,
            enabled=enabled if enabled is not None else True
        )
        
        # Save to storage
        success = storage.add(task)
        if not success:
            raise ValueError(f"Failed to create task. Task with ID {task.id} might already exist.")
        
        # Notify scheduler
        _notify_scheduler()
        
        logger.info(f"[manage_cron_task] Created cron task: {task.id} ({task.name})")
        return f"Successfully created cron task:\n{task.to_json()}"
    
    # UPDATE operation
    elif action == "update":
        # Validate required parameters
        if not task_id:
            raise ValueError("Parameter 'task_id' is required for update action")
        
        # Check if task exists
        existing_task = storage.get(task_id)
        if not existing_task:
            raise ValueError(f"Task with ID '{task_id}' not found")
        
        # Validate cron expression if provided
        if cron_expr:
            _validate_cron_expr(cron_expr)
        
        # Build update dict
        updates = {}
        if name is not None:
            updates['name'] = name
        if cron_expr is not None:
            updates['cron_expr'] = cron_expr
        if instruction is not None:
            updates['instruction'] = instruction
        if enabled is not None:
            updates['enabled'] = enabled
        
        if not updates:
            raise ValueError("At least one field must be provided for update (name, cron_expr, instruction, enabled)")
        
        # Update task
        success = storage.update(task_id, **updates)
        if not success:
            raise ValueError(f"Failed to update task '{task_id}'")
        
        # Notify scheduler
        _notify_scheduler()
        
        # Get updated task
        updated_task = storage.get(task_id)
        
        logger.info(f"[manage_cron_task] Updated cron task: {task_id}")
        return f"Successfully updated cron task:\n{updated_task.to_json()}"
    
    # DELETE operation
    elif action == "delete":
        # Validate required parameters
        if not task_id:
            raise ValueError("Parameter 'task_id' is required for delete action")
        
        # Check if task exists
        existing_task = storage.get(task_id)
        if not existing_task:
            raise ValueError(f"Task with ID '{task_id}' not found")
        
        # Delete task
        success = storage.delete(task_id)
        if not success:
            raise ValueError(f"Failed to delete task '{task_id}'")
        
        # Notify scheduler
        _notify_scheduler()
        
        logger.info(f"[manage_cron_task] Deleted cron task: {task_id}")
        return f"Successfully deleted cron task: {task_id} ({existing_task.name})"
    
    # LIST operation
    elif action == "list":
        # Load tasks
        if enabled_only:
            tasks = storage.get_enabled()
        else:
            tasks = storage.load_all()
        
        # Validate sort_by parameter
        valid_sort_fields = ["name", "created_at", "next_run"]
        if sort_by not in valid_sort_fields:
            raise ValueError(f"Invalid sort_by '{sort_by}'. Must be one of: {', '.join(valid_sort_fields)}")
        
        # Format and return
        return _format_task_list(tasks, sort_by=sort_by)


@function_tool(description_override=MANAGE_CRON_TASK_DOCS)
def manage_cron_task(
    action: str,
    task_id: Optional[str] = None,
    name: Optional[str] = None,
    cron_expr: Optional[str] = None,
    instruction: Optional[str] = None,
    enabled: Optional[bool] = None,
    enabled_only: bool = False,
    sort_by: str = "next_run"
) -> str:
    return manage_cron_task_impl(
        action=action,
        task_id=task_id,
        name=name,
        cron_expr=cron_expr,
        instruction=instruction,
        enabled=enabled,
        enabled_only=enabled_only,
        sort_by=sort_by
    )
