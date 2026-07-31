import json
from siada.tools.todo.recovery import extract_todos_from_messages


def _todo_call(todos):
    return {
        "type": "function_call",
        "name": "todo_write",
        "arguments": json.dumps({"todos": todos}),
    }


def test_extract_from_messages_found():
    msgs = [
        {"type": "message", "role": "user", "content": "hello"},
        _todo_call([{"content": "Fix bug", "active_form": "Fixing bug", "status": "pending"}]),
    ]
    result = extract_todos_from_messages(msgs)
    assert len(result) == 1
    assert result[0].content == "Fix bug"
    assert result[0].status == "pending"


def test_extract_returns_last_call():
    msgs = [
        _todo_call([{"content": "Old", "active_form": "Old-ing", "status": "pending"}]),
        _todo_call([{"content": "New", "active_form": "New-ing", "status": "in_progress"}]),
    ]
    result = extract_todos_from_messages(msgs)
    assert result[0].content == "New"


def test_extract_no_todo_write_returns_empty():
    msgs = [{"type": "message", "role": "user", "content": "hi"}]
    assert extract_todos_from_messages(msgs) == []


def test_extract_empty_messages():
    assert extract_todos_from_messages([]) == []


def test_extract_malformed_arguments_returns_empty():
    msgs = [{"type": "function_call", "name": "todo_write", "arguments": "not json"}]
    assert extract_todos_from_messages(msgs) == []
