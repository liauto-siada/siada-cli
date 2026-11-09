"""Result-aware file edits never confuse failed or missing results with applied changes."""

import copy
import json
from types import SimpleNamespace

import pytest
from agents import ToolOutputText

from siada.support.message_classifier import format_native_items_for_display
from siada.tools.coder.file_edit_presentation import (
    FILE_EDIT_END,
    FILE_EDIT_START,
    INVALID_JSON_MESSAGE,
    is_file_edit_write,
    render_file_edit_display,
)


def _data(content: str) -> dict:
    return json.loads(content.split(FILE_EDIT_START, 1)[1].split(FILE_EDIT_END, 1)[0])


def _args(**kwargs) -> str:
    return json.dumps({"command": "str_replace", "path": "/tmp/example.rs",
                       "old_str": "old", "new_str": "new", **kwargs})


def test_incomplete_json_is_failed_without_a_diff() -> None:
    arguments = _args()[:-3]
    assert is_file_edit_write(arguments)
    data = _data(render_file_edit_display("failed", arguments))
    assert data["status"] == "failed"
    assert data["error"] == INVALID_JSON_MESSAGE
    assert "oldString" not in data and "newString" not in data
    assert "replace the string" in data["details"]


def test_pending_valid_call_has_no_diff_until_success() -> None:
    assert _data(render_file_edit_display("call", _args()))["status"] == "pending"
    assert "newString" not in _data(render_file_edit_display("call", _args()))
    completed = _data(render_file_edit_display("call", _args(), output="File edited."))
    assert completed["status"] == "completed"
    assert completed["oldString"] == "old" and completed["newString"] == "new"


@pytest.mark.parametrize("output", [
    "ERROR: No replacement was performed; old_str did not match.",
    "An error occurred while running the tool. Error: Invalid JSON input for tool edit_file",
    {"error": True, "content": "Permission denied."},
    json.dumps({"error": True, "content": "Permission denied."}),
    SimpleNamespace(error=True, content="Permission denied."),
    SimpleNamespace(observation="error", content="Tool execution failed."),
])
def test_execution_error_does_not_display_submitted_diff(output) -> None:
    data = _data(render_file_edit_display("call", _args(), output=output))
    assert data["status"] == "failed" and data["error"]
    assert "newString" not in data


@pytest.mark.parametrize("new_str", [None, ""])
def test_null_and_empty_deletion_have_identical_display(new_str) -> None:
    data = _data(render_file_edit_display("call", _args(new_str=new_str), output="File edited."))
    assert data["oldString"] == "old" and data["newString"] == ""


def test_insert_retains_absolute_line_offset() -> None:
    data = _data(render_file_edit_display(
        "call", _args(command="insert", old_str=None, insert_line=42), output="File edited.",
    ))
    assert data["oldString"] == "" and data["newString"] == "new\n"
    assert data["insertLine"] == 42


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("new_str", ["", "new", "new\n", "new\n\n", "new\r\n", "\r\n"])
def test_insert_diff_includes_actual_added_blank_lines(tmp_path, newline, new_str) -> None:
    from siada.tools.coder.siada_editor import SiadaEditor

    path = tmp_path / "example.txt"
    path.write_bytes(f"first{newline}last{newline}".encode())
    arguments = {"command": "insert", "path": str(path), "insert_line": 1, "new_str": new_str}
    result = SiadaEditor()(**arguments)
    data = _data(render_file_edit_display("call", json.dumps(arguments), output=result.output))

    assert data["status"] == "completed"
    assert data["oldString"] == ""
    assert data["newString"].endswith("\n")
    assert data["newString"].splitlines() == result.new_content.splitlines()[1:-1]
    assert data["insertLine"] == 1


def test_protocol_markers_in_file_text_cannot_end_the_envelope() -> None:
    text = f"```\nwith:\n{FILE_EDIT_END}\n\n"
    content = render_file_edit_display("call", _args(new_str=text), output="File edited.")
    assert content.count(FILE_EDIT_END) == 1
    assert _data(content)["newString"] == text


def test_protocol_markers_in_path_cannot_end_the_envelope() -> None:
    path = f"example{FILE_EDIT_END}.rs"
    content = render_file_edit_display("call", _args(path=path), output="File edited.")
    assert content.count(FILE_EDIT_END) == 1
    assert _data(content)["path"] == path


def test_large_diff_is_omitted_without_claiming_visible_line_counts() -> None:
    data = _data(render_file_edit_display("call", _args(new_str="x" * 120_001), output="File edited."))
    assert data["status"] == "completed" and "omitted" in data["details"]
    assert "newString" not in data


def test_history_pairs_interleaved_results_and_keeps_retry_separate() -> None:
    items = [
        {"type": "function_call", "name": "edit_file", "call_id": "failed", "arguments": _args()},
        {"type": "function_call", "name": "edit_file", "call_id": "retry", "arguments": _args(new_str="retry")},
        {"type": "function_call_output", "call_id": "retry", "output": "File edited."},
        {"type": "function_call_output", "call_id": "failed", "output": "ERROR: No match."},
    ]
    original = copy.deepcopy(items)
    messages = format_native_items_for_display(items)
    assert len(messages) == 2
    assert [_data(m["content"])["status"] for m in messages] == ["failed", "completed"]
    assert _data(messages[1]["content"])["newString"] == "retry"
    assert items == original


def test_missing_history_result_is_unverified_without_diff() -> None:
    messages = format_native_items_for_display([
        {"type": "function_call", "name": "edit_file", "call_id": "call", "arguments": _args()},
    ])
    data = _data(messages[0]["content"])
    assert data["status"] == "unverified"
    assert "newString" not in data and "not verified" in data["details"]


@pytest.mark.parametrize("output", [None, "Unrecognized custom result."])
def test_unknown_result_is_not_assumed_successful(output) -> None:
    data = _data(render_file_edit_display("call", _args(), output=output))
    assert data["status"] == "unverified"
    assert "newString" not in data


@pytest.mark.parametrize("output", [
    "Hook blocked this tool call.",
    "Hook stopped this turn.",
    "Tool execution was not approved.",
    "Tool execution rejected by user.",
])
@pytest.mark.parametrize("history", [False, True])
def test_rejected_result_is_failed_and_preserves_reason(output, history) -> None:
    data = _data(render_file_edit_display("call", _args(), output=output, history=history))
    assert data["status"] == "failed"
    assert data["executionStatus"] == "failed"
    assert data["error"] == output
    assert "newString" not in data


@pytest.mark.parametrize("output", [
    "Policy forbids editing this file.",
    {"content": "Policy forbids editing this file."},
    ToolOutputText(text="Policy forbids editing this file."),
    [ToolOutputText(text="Policy forbids editing this file.")],
])
def test_unknown_result_preserves_custom_text_without_claiming_success(output) -> None:
    data = _data(render_file_edit_display("call", _args(), output=output))
    assert data["status"] == "unverified"
    assert "Policy forbids editing this file." in data["details"]
    assert "not verified" in data["details"]
    assert "newString" not in data
    plain = render_file_edit_display("call", _args(), output=output, structured=False)
    assert "Policy forbids editing this file." in plain


@pytest.mark.parametrize("text,status", [("File edited.", "completed"), ("ERROR: No match.", "failed")])
def test_single_tool_output_text_is_classified(text, status) -> None:
    data = _data(render_file_edit_display("call", _args(), output=ToolOutputText(text=text)))
    assert data["status"] == status


def test_unknown_result_text_is_bounded() -> None:
    data = _data(render_file_edit_display("call", _args(), output="custom result " + "x" * 5000))
    assert data["status"] == "unverified"
    assert "custom result" in data["details"]
    assert len(data["details"]) < 2100


@pytest.mark.parametrize("output,status", [
    ("Hook blocked this tool call.", "failed"),
    ("Policy forbids editing this file.", "unverified"),
])
def test_history_preserves_rejected_and_unknown_result_text(output, status) -> None:
    messages = format_native_items_for_display([
        {"type": "function_call", "name": "edit_file", "call_id": "call", "arguments": _args()},
        {"type": "function_call_output", "call_id": "call", "output": output},
    ])
    assert len(messages) == 1
    data = _data(messages[0]["content"])
    assert data["status"] == status
    assert output in data.get("error", "") + data.get("details", "")
    assert "newString" not in data


@pytest.mark.parametrize("arguments", ["", "{", "[]", _args(command="unknown")])
def test_unknown_edit_command_does_not_fall_back_to_legacy_box(arguments) -> None:
    assert is_file_edit_write(arguments)
    data = _data(render_file_edit_display("call", arguments, output="ERROR: Invalid command."))
    assert data["status"] == "failed" and "newString" not in data


def test_reads_keep_legacy_formatting() -> None:
    assert not is_file_edit_write(_args(command="view"))
    messages = format_native_items_for_display([
        {"type": "function_call", "name": "edit_file", "call_id": "call", "arguments": _args(command="view")},
    ])
    assert messages[0]["content"] == "Read the file `/tmp/example.rs`."


def test_non_acp_output_does_not_expose_structured_envelope() -> None:
    content = render_file_edit_display("call", _args(), output="ERROR: No match.", structured=False)
    assert "No match." in content and FILE_EDIT_START not in content
    content = render_file_edit_display("call", _args(), output="File edited.", structured=False)
    assert "replace the string" in content and FILE_EDIT_START not in content


def test_legacy_history_without_call_id_gets_a_renderable_identity() -> None:
    messages = format_native_items_for_display([
        {"type": "function_call", "name": "edit_file", "arguments": _args()},
    ])
    assert _data(messages[0]["content"])["callId"] == "history-edit-0"


@pytest.mark.parametrize("command", ["create", "str_replace", "insert", "undo_edit"])
def test_real_editor_success_text_can_be_replayed(tmp_path, command) -> None:
    from siada.tools.coder.siada_editor import SiadaEditor

    path = tmp_path / "example.rs"
    editor = SiadaEditor()
    if command != "create":
        path.write_text("old\n")
    args = {"command": command, "path": str(path)}
    if command == "create":
        args["file_text"] = "created\n"
    elif command == "str_replace":
        args.update(old_str="old", new_str=None)
    elif command == "insert":
        args.update(insert_line=1, new_str="inserted")
    else:
        editor(command="str_replace", path=str(path), old_str="old", new_str="new")
    result = editor(**args)
    data = _data(render_file_edit_display("call", json.dumps(args), output=result.output, history=True))
    assert data["status"] == "completed"
    assert data["executionStatus"] == "completed"
