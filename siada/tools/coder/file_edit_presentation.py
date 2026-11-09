"""Result-aware edit_file presentation shared by live output and history replay."""

from __future__ import annotations

import json
import re
from typing import Any

from partial_json_parser import loads

from siada.tools.tool_call_format.formatters import FileEditFormatter


FILE_EDIT_START = "<!-- siada-file-edit:start -->"
FILE_EDIT_END = "<!-- siada-file-edit:end -->"
INVALID_JSON_MESSAGE = "Invalid JSON arguments; no changes applied."
RESULT_UNAVAILABLE = object()
_MAX_TEXT_CHARS = 120_000


def _arguments(arguments: str) -> tuple[dict[str, Any], bool]:
    try:
        parsed = json.loads(arguments)
        return (parsed, True) if isinstance(parsed, dict) else ({}, False)
    except (TypeError, ValueError):
        try:
            parsed = loads(arguments)
            return (parsed if isinstance(parsed, dict) else {}), False
        except Exception:
            return {}, False


def is_file_edit_write(arguments: str) -> bool:
    """Only known reads use the legacy path; malformed writes need a status row."""
    args, _ = _arguments(arguments)
    return args.get("command") != "view"


def _output_text(output: Any) -> str:
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return _output_text(parsed)
        return output.strip()[:2000]
    if isinstance(output, dict):
        return _output_text(output.get("output") or output.get("content") or output.get("text") or "")
    if isinstance(output, list):
        return "\n".join(_output_text(item) for item in output)[:2000]
    return _output_text(getattr(output, "text", None) or getattr(output, "content", None) or "")


def _output_error(output: Any) -> str | None:
    """Accept both live observations and persisted model-facing result text."""
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return _output_error(parsed)
        text = output.strip()
        if text.startswith(("ERROR:", "Error:", "An error occurred", "**ErrorObservation**")):
            return text[:2000]
        if re.match(
            r"(?:Hook (?:blocked|stopped|rejected)\b|"
            r"Tool (?:execution|call) (?:was not approved|(?:was )?rejected)\b)",
            text, re.IGNORECASE,
        ):
            return text[:2000]
        return None
    if isinstance(output, dict):
        if output.get("error"):
            return str(output.get("content") or output["error"])[:2000]
        return _output_error(output.get("output") or output.get("content") or output.get("text") or "")
    if getattr(output, "error", False) or getattr(output, "observation", None) == "error":
        return str(getattr(output, "content", "File operation failed."))[:2000]
    if isinstance(output, list):
        for item in output:
            error = _output_error(getattr(item, "text", item))
            if error:
                return error
    text = getattr(output, "text", None)
    if isinstance(text, str):
        return _output_error(text)
    return None


def _output_succeeded(output: Any) -> bool:
    """Require a positive editor result; rejection/custom text is not success."""
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return _output_succeeded(parsed)
        return bool(re.match(
            r"(?:File edited\.|File created successfully at:|The file .+ has been edited\.|"
            r"Last edit to .+ undone successfully|\[New file .+ is created|\[Existing file .+ is edited)",
            output.strip(),
        ))
    if isinstance(output, dict):
        if output.get("error") is False:
            return True
        return _output_succeeded(output.get("output") or output.get("content") or output.get("text") or "")
    if getattr(output, "error", None) is False:
        return True
    if isinstance(output, list):
        return any(_output_succeeded(getattr(item, "text", item)) for item in output)
    text = getattr(output, "text", None)
    if isinstance(text, str):
        return _output_succeeded(text)
    return False


def render_file_edit_display(
    call_id: str,
    arguments: str,
    *,
    output: Any = RESULT_UNAVAILABLE,
    history: bool = False,
    structured: bool = True,
) -> str:
    """Show a diff only after execution succeeds, without changing stored tool items.

    Diffs are snippet-relative submitted edits, not reconstructed full files.
    Missing historical results are explicitly unverified, never assumed applied.
    The JSON envelope travels as ordinary ACP text, like native patch previews.
    """
    args, valid = _arguments(arguments)
    command = args.get("command")
    action = "create" if command == "create" else "undo" if command == "undo_edit" else "update"
    path = args.get("path") if isinstance(args.get("path"), str) else "file"
    output_error = None if output is RESULT_UNAVAILABLE else _output_error(output)
    error = output_error if valid else INVALID_JSON_MESSAGE
    if output is RESULT_UNAVAILABLE:
        execution_status = "unknown" if history else "pending"
    elif output_error:
        execution_status = "failed"
    elif _output_succeeded(output):
        execution_status = "completed"
    else:
        execution_status = "unknown"
    if error:
        status = "failed"
    elif execution_status == "unknown":
        status = "unverified"
    else:
        status = execution_status
    payload: dict[str, Any] = {
        "callId": call_id,
        "action": action,
        "path": path,
        "status": status,
        "argumentsComplete": valid,
        "executionStatus": execution_status,
    }
    if error:
        payload["error"] = error
    if status == "unverified":
        result_text = "" if output is RESULT_UNAVAILABLE else _output_text(output)
        payload["details"] = (
            f"Tool result not recognized; changes not verified.\n{result_text}"
            if result_text else "Tool result unavailable; changes not verified."
        )
    if status == "failed":
        preview, _ = FileEditFormatter().format_input(call_id, "edit_file", arguments)
        payload["details"] = preview[:2000] or "Tool arguments could not be displayed."
    if status == "completed":
        old_text = args.get("old_str") if command == "str_replace" else ""
        new_text = args.get("file_text") if command == "create" else args.get("new_str")
        if command == "insert" and isinstance(new_text, str):
            new_text = new_text.replace("\r\n", "\n") + "\n"
        if command == "undo_edit":
            payload["details"] = "Edit reverted."
        elif not isinstance(old_text, str) or (new_text is not None and not isinstance(new_text, str)):
            payload["details"] = "Applied without a displayable text diff."
        elif len(old_text) + len(new_text or "") > _MAX_TEXT_CHARS:
            payload["details"] = "Diff omitted to keep the display responsive."
        else:
            payload.update(oldString=old_text, newString=new_text or "")
            if command == "insert":
                payload["insertLine"] = args.get("insert_line")
    if not structured:
        if status == "completed":
            content, _ = FileEditFormatter().format_input(call_id, "edit_file", arguments)
            return content or f"{action.title()} {path}: Applied."
        return f"{action.title()} {path}\n{error or payload.get('details') or 'Waiting for tool result...'}"
    # Escape marker-like file content so it cannot terminate the envelope.
    body = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    heading_path = path.replace("<", "\\u003c")
    return f"File edit: {action} {heading_path}\n{FILE_EDIT_START}\n{body}\n{FILE_EDIT_END}"
