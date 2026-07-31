"""
todo_write_tool: LLM-callable tool for writing/updating the session's todo list.

Two-layer design (mirrors memory_write_tool.py pattern):
- todo_write_impl: pure business logic, directly testable
- todo_write: @function_tool wrapper, reads/writes context.todos
"""
from typing import List

from agents import RunContextWrapper, function_tool

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.todo.models import TodoItem

TODO_WRITE_DOCS = """\
Update the todo list for the current session. Use proactively to track progress
on complex multi-step tasks.

WHEN TO USE:
- Task requires 3 or more distinct steps
- Non-trivial task requiring careful planning or multiple operations
- User explicitly requests todo tracking
- User provides multiple tasks (numbered list or comma-separated)
- After receiving new instructions — immediately capture requirements as todos
- Before starting a task — mark it in_progress BEFORE actually executing it
- After completing a task — immediately mark it completed and add any newly
  discovered follow-up tasks

WHEN NOT TO USE:
- Single, simple tasks completable in one step
- Trivial tasks where tracking adds no organizational value
- Pure conversational or informational requests

ORDERING (items must be listed in execution order):
- Items that need to be done FIRST must appear EARLIER in the list
- Think of the list as a sequential pipeline: top items are what you work on
  now, bottom items are what comes later
- When you complete an item and advance the next one to in_progress, it
  should already be the next item in the list — no reordering needed

TASK STATE RULES (strictly enforced):
- Exactly ONE task must be in_progress at any time (never zero when tasks exist, never two)
- Mark tasks complete IMMEDIATELY after finishing — do NOT batch completions
- ONLY mark completed when FULLY accomplished; keep in_progress if errors occur or tests fail
- Delete todo items that are no longer relevant

Args:
    todos: Complete, full todo list (replaces previous list entirely — NOT incremental).
           Each item requires:
             content     — imperative form, e.g. "Fix authentication bug"
             active_form — present continuous, e.g. "Fixing authentication bug"
             status      — "pending" | "in_progress" | "completed"
           Both content and active_form are REQUIRED — never omit either.
"""

_SUCCESS_TEXT = (
    "Todos have been modified successfully. Ensure that you continue to use the "
    "todo list to track your progress. Please proceed with the current tasks if applicable.\n"
    "Note: the system will periodically inject a hidden reminder message showing the current "
    "contents of your todo list — treat that as the authoritative state when you see it."
)


def _push_todo_state_via_acp(todos: List[TodoItem]) -> None:
    """Push current todo state to frontend via ACP custom notification (best-effort)."""
    try:
        from siada.foundation.global_cache import get_global_cache, ACP_LEGACY_ADAPTER
        adapter = get_global_cache(ACP_LEGACY_ADAPTER)
        if adapter is None or not adapter.acp_enabled:
            return
        todo_dicts = [
            {"content": t.content, "status": t.status}
            for t in todos
        ]
        adapter._send_if_acp(
            adapter.builder.build_custom_notification,
            method="context/todoState",
            params={"todos": todo_dicts},
        )
    except Exception:
        pass  # ACP push is best-effort; never break tool execution


def todo_write_impl(context: CodeAgentContext, todos: List[TodoItem]) -> str:
    """Business logic layer — update context.todos, apply all-done rule, return result text."""
    all_done = all(t.status == "completed" for t in todos) if todos else False
    context.todos = [] if all_done else list(todos)
    context.todo_turns_since_write = 0
    context.todo_turns_since_reminder = 0
    _push_todo_state_via_acp(context.todos)
    return _SUCCESS_TEXT


@function_tool(name_override="todo_write", description_override=TODO_WRITE_DOCS)
async def todo_write(
    run_ctx: RunContextWrapper[CodeAgentContext],
    todos: List[TodoItem],
) -> str:
    return todo_write_impl(run_ctx.context, todos)
