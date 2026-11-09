import json

import pytest

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


def test_extract_camel_case_active_form_from_legacy_history():
    msgs = [_todo_call([{
        "content": "Continue task", "activeForm": "Continuing task", "status": "in_progress",
    }])]

    result = extract_todos_from_messages(msgs)

    assert len(result) == 1
    assert result[0].active_form == "Continuing task"
    assert result[0].model_dump() == {
        "content": "Continue task", "active_form": "Continuing task", "status": "in_progress",
    }


@pytest.mark.parametrize("previous", [False, True])
def test_extract_skips_recorded_failed_todo_write(previous):
    msgs = [_todo_call([{
        "content": "Saved task", "active_form": "Working on saved task", "status": "in_progress",
    }])] if previous else []
    msgs.extend([
        {**_todo_call([{
            "content": "Rejected task", "activeForm": "Working on rejected task", "status": "in_progress",
        }]), "call_id": "failed-todo"},
        {"type": "function_call_output", "call_id": "failed-todo",
         "output": "An error occurred while running the tool. Error: Invalid JSON input for tool todo_write"},
    ])

    result = extract_todos_from_messages(msgs)

    assert [item.content for item in result] == (["Saved task"] if previous else [])
