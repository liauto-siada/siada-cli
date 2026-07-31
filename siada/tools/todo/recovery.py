"""
Recover the last todo list from the message history (for --resume scenarios).
"""
import json
from typing import List

from siada.tools.todo.models import TodoItem


def extract_todos_from_messages(messages: List) -> List[TodoItem]:
    """
    Scan message history in reverse order to find the last todo_write call
    and reconstruct the todo list from its arguments.

    Args:
        messages: list returned by task_message_state.get_messages()

    Returns:
        The most recent todo list, or [] if none found.
    """
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call" and item.get("name") == "todo_write":
            try:
                args = item.get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                raw_todos = args.get("todos", [])
                return [TodoItem(**t) for t in raw_todos]
            except Exception:
                return []
    return []
