import pytest
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.todo.models import TodoItem
from siada.tools.todo.todo_write_tool import todo_write_impl, _SUCCESS_TEXT


def _make_item(status="pending"):
    return TodoItem(content="Fix bug", active_form="Fixing bug", status=status)


def test_todo_write_impl_stores_todos():
    ctx = CodeAgentContext()
    items = [_make_item("pending"), _make_item("in_progress")]
    result = todo_write_impl(ctx, items)
    assert len(ctx.todos) == 2
    assert result == _SUCCESS_TEXT


def test_todo_write_impl_resets_counters():
    ctx = CodeAgentContext()
    ctx.todo_turns_since_write = 5
    ctx.todo_turns_since_reminder = 7
    todo_write_impl(ctx, [_make_item()])
    assert ctx.todo_turns_since_write == 0
    assert ctx.todo_turns_since_reminder == 0


def test_todo_write_impl_all_done_clears_list():
    ctx = CodeAgentContext()
    items = [_make_item("completed"), _make_item("completed")]
    todo_write_impl(ctx, items)
    assert ctx.todos == []


def test_todo_write_impl_partial_done_keeps_list():
    ctx = CodeAgentContext()
    items = [_make_item("completed"), _make_item("in_progress")]
    todo_write_impl(ctx, items)
    assert len(ctx.todos) == 2


def test_todo_write_impl_empty_list():
    ctx = CodeAgentContext()
    todo_write_impl(ctx, [])
    assert ctx.todos == []
