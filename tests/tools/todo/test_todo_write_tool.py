import json

import pytest
from agents.tool_context import ToolContext

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.todo.models import TodoItem
from siada.tools.todo.todo_write_tool import todo_write, todo_write_impl, _SUCCESS_TEXT


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


@pytest.mark.asyncio
@pytest.mark.parametrize("active_form_key", ["active_form", "activeForm"])
async def test_todo_write_accepts_active_form_spellings(active_form_key, monkeypatch):
    monkeypatch.setattr("siada.tools.todo.todo_write_tool._push_todo_state_via_acp", lambda _: None)
    ctx = CodeAgentContext()
    arguments = json.dumps({"todos": [{
        "content": "Fix bug",
        active_form_key: "Fixing bug",
        "status": "in_progress",
    }]})
    tool_context = ToolContext(
        context=ctx, tool_name="todo_write", tool_call_id="todo-alias", tool_arguments=arguments,
    )

    result = await todo_write.on_invoke_tool(tool_context, arguments)

    assert result == _SUCCESS_TEXT
    assert ctx.todos == [_make_item("in_progress")]
    assert ctx.todos[0].model_dump() == {
        "content": "Fix bug", "active_form": "Fixing bug", "status": "in_progress",
    }


def test_todo_schema_keeps_active_form_canonical():
    schema = todo_write.params_json_schema["$defs"]["TodoItem"]
    assert set(schema["properties"]) == {"content", "active_form", "status"}
    assert set(schema["required"]) == {"content", "active_form", "status"}


@pytest.mark.asyncio
@pytest.mark.parametrize("item", [
    {"content": "Invalid task", "status": "in_progress"},
    {"content": "Invalid task", "activeForm": "Working", "status": "unknown"},
])
async def test_invalid_todo_arguments_preserve_previous_state(item, monkeypatch):
    monkeypatch.setattr("siada.tools.todo.todo_write_tool._push_todo_state_via_acp", lambda _: None)
    ctx = CodeAgentContext(todos=[_make_item("in_progress")])
    ctx.todo_turns_since_write = 6
    ctx.todo_turns_since_reminder = 7
    arguments = json.dumps({"todos": [item]})
    tool_context = ToolContext(
        context=ctx, tool_name="todo_write", tool_call_id="todo-invalid", tool_arguments=arguments,
    )

    result = await todo_write.on_invoke_tool(tool_context, arguments)

    assert "Invalid JSON input for tool todo_write" in result
    assert ctx.todos == [_make_item("in_progress")]
    assert (ctx.todo_turns_since_write, ctx.todo_turns_since_reminder) == (6, 7)
