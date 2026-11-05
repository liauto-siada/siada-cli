"""
Recover the last todo list from the message history (for --resume scenarios).
"""
import json
from typing import List

from siada.tools.todo.models import TodoItem


def extract_todos_from_messages(messages: List) -> List[TodoItem]:
    """
    Recover the latest todo_write call without a recorded tool failure.
    Call-only legacy histories remain supported.

    Args:
        messages: list returned by task_message_state.get_messages()

    Returns:
        The most recent todo list, or [] if none found.
    """
    failed_call_ids: set[str] = set()
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        call_id = item.get("call_id")
        if item.get("type") == "function_call_output":
            output = item.get("output")
            if (isinstance(call_id, str) and isinstance(output, str)
                    and output.startswith("An error occurred while running the tool.")):
                failed_call_ids.add(call_id)
            continue
        if item.get("type") == "function_call" and item.get("name") == "todo_write":
            if isinstance(call_id, str) and call_id in failed_call_ids:
                continue
            try:
                args = item.get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                raw_todos = args.get("todos", [])
                return [TodoItem(**t) for t in raw_todos]
            except Exception:
                return []
    return []
