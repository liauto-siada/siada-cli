"""
Save Task List Tool

Provides functionality to save discovered tasks to storage.
"""

import logging
import json
from typing import Optional

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.proactive.models import TaskList
from siada.agent_hub.proactive.task_storage import TaskStorage


logger = logging.getLogger(__name__)


SAVE_TASK_LIST_DOCS = """Save a list of discovered tasks to persistent storage.

Use this tool to save tasks you've discovered from memory analysis. Tasks are saved
to daily storage files and can be retrieved later by the user.

Args:
    task_list_json (str): JSON string containing the task list with the following structure:
        {
          "tasks": [
            {
              "title": "Task title",
              "description": "Detailed description",
              "priority": "high|medium|low",
              "category": "feature|bug|refactor|doc|test|other",
              "status": "pending|in_progress|completed|cancelled",
              "needs_confirmation": true|false,
              "source_memories": ["file1.md", "file2.md"],
              "suggested_actions": ["Step 1", "Step 2"],
              "confidence": 0.85
            }
          ]
        }
    date (str, optional): Date to save tasks for in "YYYY-MM-DD" format. 
                         Defaults to today if not specified.

Returns:
    str: Success message with count of saved tasks, or error message if save failed.

Examples:
    save_task_list(task_list_json='{"tasks": [...]}')
    save_task_list(task_list_json='{"tasks": [...]}', date="2024-03-05")

Note: This tool automatically creates Task objects with proper IDs and timestamps.
"""


# ---- Implementation Function --------------------------------

def save_task_list_impl(
    task_list_json: str,
    date: Optional[str] = None,
) -> str:
    """
    Internal implementation of save_task_list.
    
    This function performs the actual save logic and is intended to be tested directly.
    The public save_task_list function wraps this with the function_tool decorator.
    
    Args:
        task_list_json: JSON string containing task list
        date: Optional date string "YYYY-MM-DD" (defaults to today)
        
    Returns:
        Success or error message
    """
    try:
        # Parse JSON
        try:
            data = json.loads(task_list_json)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON format: {str(e)}"
        
        # Validate structure
        if not isinstance(data, dict) or "tasks" not in data:
            return 'Error: JSON must contain a "tasks" key with a list of tasks'
        
        if not isinstance(data["tasks"], list):
            return 'Error: "tasks" must be a list'
        
        # Create TaskList from task data
        try:
            from siada.agent_hub.proactive.models import Task
            
            task_list = TaskList()
            for task_data in data["tasks"]:
                # Use Task.create() to automatically generate id, timestamps
                task = Task.create(
                    title=task_data["title"],
                    description=task_data["description"],
                    priority=task_data["priority"],
                    category=task_data["category"],
                    status=task_data.get("status", "pending"),
                    needs_confirmation=task_data["needs_confirmation"],
                    source_memories=task_data["source_memories"],
                    suggested_actions=task_data["suggested_actions"],
                    confidence=task_data["confidence"]
                )
                task_list.add_task(task)
        except (ValueError, TypeError, KeyError) as e:
            return f"Error: Invalid task data structure: {str(e)}"
        
        # Save to storage
        storage = TaskStorage()
        success = storage.save(task_list, date=date)
        
        if not success:
            return f"Error: Failed to save task list to storage"
        
        # Build success message
        task_count = len(task_list.tasks)
        date_str = date if date else "today"
        
        if task_count == 0:
            return f"Saved empty task list for {date_str}"
        
        # Count by priority
        high_count = sum(1 for t in task_list.tasks if t.priority == "high")
        medium_count = sum(1 for t in task_list.tasks if t.priority == "medium")
        low_count = sum(1 for t in task_list.tasks if t.priority == "low")
        
        # Count needing confirmation
        needs_confirm = sum(1 for t in task_list.tasks if t.needs_confirmation)
        
        result = [
            f"Successfully saved {task_count} task(s) for {date_str}:",
            f"  • High priority: {high_count}",
            f"  • Medium priority: {medium_count}",
            f"  • Low priority: {low_count}",
        ]
        
        if needs_confirm > 0:
            result.append(f"  • Needs confirmation: {needs_confirm}")
        
        return "\n".join(result)
        
    except Exception as e:
        logger.error(f"Error saving task list: {e}", exc_info=True)
        return f"Error saving task list: {str(e)}"


# ---- Public Tool Function --------------------------------

@function_tool(
    name_override="save_task_list", description_override=SAVE_TASK_LIST_DOCS
)
def save_task_list(
    context: RunContextWrapper[CodeAgentContext],
    task_list_json: str,
    date: Optional[str] = None,
) -> str:
    return save_task_list_impl(task_list_json=task_list_json, date=date)
