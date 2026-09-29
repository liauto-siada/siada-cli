"""Presentation data and text rendering for native Responses ``apply_patch``.

The OpenAI Agents SDK deliberately keeps ``ApplyPatchTool`` model-facing: its
``apply_patch_call_output`` contains only a compact result string.  Siada's
editor records the actual before/after text while it owns the file operation,
then attaches JSON-compatible display data through the SDK's
``custom_data_extractor`` hook.

ACP keeps transporting ordinary tool-use text.  The renderer below emits a
stable, human-readable block that old clients and logs can read directly, and
which the CLI UI can recognise to render multi-file diffs.  This avoids making
ACP's persisted message schema depend on a particular native tool protocol.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import difflib
from typing import Any, Mapping, Sequence

from agents.tool import ApplyPatchToolCustomDataContext


APPLY_PATCH_CUSTOM_DATA_KEY = "siada_apply_patch"
APPLY_PATCH_DISPLAY_START = "<!-- siada-apply-patch:start -->"
APPLY_PATCH_DISPLAY_END = "<!-- siada-apply-patch:end -->"
APPLY_PATCH_HISTORY_PREVIEW = "<!-- siada-apply-patch:history-preview -->"

# Keep a single lifecycle payload from making the terminal client unusable.
# The complete operation data remains SDK-local in ``ToolCallOutputItem``;
# only the text display is capped.
MAX_DIFF_CHARS_PER_OPERATION = 40_000
MAX_DIFF_CHARS_TOTAL = 120_000


@dataclass(frozen=True)
class PatchOperationPresentation:
    """Actual file state associated with one native patch operation."""

    action: str
    path: str
    move_to: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    status: str = "completed"
    error: str | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


class PatchPresentationRecorder:
    """Collect operation state during local editor execution.

    ``ApplyPatchOperation`` is slots-based in current Agents SDK versions, so
    attaching Siada state to it is not safe.  The recorder instead keys state
    by object identity; the SDK passes the exact same operation instances to
    the editor and then to ``custom_data_extractor``.
    """

    def __init__(self) -> None:
        self._presentations: dict[int, PatchOperationPresentation] = {}

    def record_completed(
        self,
        operation: Any,
        *,
        old_text: str,
        new_text: str,
        action: str | None = None,
    ) -> None:
        move_to = getattr(operation, "move_to", None)
        self._presentations[id(operation)] = PatchOperationPresentation(
            action=action or ("move" if move_to else str(getattr(operation, "type", "update"))),
            path=str(getattr(operation, "path", "")),
            move_to=str(move_to) if move_to else None,
            old_text=old_text,
            new_text=new_text,
        )

    def record_failed(self, operation: Any, error: Exception | str) -> None:
        move_to = getattr(operation, "move_to", None)
        self._presentations[id(operation)] = PatchOperationPresentation(
            action="move" if move_to else str(getattr(operation, "type", "update")),
            path=str(getattr(operation, "path", "")),
            move_to=str(move_to) if move_to else None,
            status="failed",
            error=str(error),
        )

    def extract_custom_data(
        self, context: ApplyPatchToolCustomDataContext
    ) -> Mapping[str, Any]:
        """Return SDK-only display information for the completed output item."""
        call_id = _mapping_value(context.raw_item, "call_id") or ""
        presentations = [
            self._presentations.pop(id(operation), self._fallback(operation, context))
            for operation in context.operations
        ]
        return {
            APPLY_PATCH_CUSTOM_DATA_KEY: {
                "version": 1,
                "call_id": call_id,
                "status": context.status,
                "operations": [presentation.as_json() for presentation in presentations],
            }
        }

    @staticmethod
    def _fallback(operation: Any, context: ApplyPatchToolCustomDataContext) -> PatchOperationPresentation:
        """Preserve a useful final display if execution was intercepted early."""
        move_to = getattr(operation, "move_to", None)
        return PatchOperationPresentation(
            action="move" if move_to else str(getattr(operation, "type", "update")),
            path=str(getattr(operation, "path", "")),
            move_to=str(move_to) if move_to else None,
            status="failed" if context.status == "failed" else "completed",
            error=context.output if context.status == "failed" else None,
        )


def is_apply_patch_call(raw_item: Any) -> bool:
    """Return whether a raw Responses item represents an apply-patch call."""
    return _item_type(raw_item) == "apply_patch_call"


def is_apply_patch_output(raw_item: Any) -> bool:
    """Return whether a raw Responses item represents an apply-patch result."""
    return _item_type(raw_item) == "apply_patch_call_output"


def render_apply_patch_display(
    *,
    custom_data: Mapping[str, Any] | None,
    raw_call: Any = None,
    output: Any = None,
) -> str:
    """Render a native patch result as text safe for existing ACP consumers.

    If an SDK custom-data payload is available, this uses actual editor
    before/after content.  Older SDK timing and replay paths do not carry that
    payload; those receive an operation-only fallback rather than pretending a
    model-provided V4A patch is an applied diff.
    """
    payload = _presentation_payload(custom_data)
    if payload is not None:
        return _render_payload(payload)
    return _render_fallback(raw_call=raw_call, output=output)


def render_apply_patch_call_summary(raw_item: Any) -> str:
    """Concise safe display for history/sub-agent views before execution."""
    operations = _raw_operations(raw_item)
    if not operations:
        return "Apply patch"
    return _title_for_count(len(operations))


def render_apply_patch_history_preview(raw_item: Any) -> str:
    """Show the submitted V4A patch from persisted call arguments.

    Like the edit_file history preview, this does not claim to reconstruct
    the file state after execution. The SDK only persists the requested
    operations; their actual before/after file contents are SDK-local.
    """
    operations = _raw_operations(raw_item)
    if not operations:
        return render_apply_patch_call_summary(raw_item)

    body = [
        _title_for_count(len(operations)), "", APPLY_PATCH_HISTORY_PREVIEW,
        APPLY_PATCH_DISPLAY_START,
    ]
    used_chars = 0
    for operation in operations:
        action = str(_mapping_value(operation, "type") or "update_file")
        path = str(_mapping_value(operation, "path") or "")
        move_to = _optional_string(_mapping_value(operation, "move_to"))
        heading = _operation_heading("move" if move_to else action, path, move_to)
        raw_diff = _mapping_value(operation, "diff")
        display_path = move_to or path
        section = None
        if isinstance(raw_diff, str) and raw_diff:
            remaining = MAX_DIFF_CHARS_TOTAL - used_chars
            if len(raw_diff) > MAX_DIFF_CHARS_PER_OPERATION or len(raw_diff) > remaining:
                section = "Diff omitted to keep the history display responsive."
            else:
                preview = _preview_v4a_diff(raw_diff, action, path, display_path)
                if preview and len(preview) <= MAX_DIFF_CHARS_PER_OPERATION and len(preview) <= remaining:
                    section = f"```diff\n{preview}\n```"
                    used_chars += len(preview)
                elif preview:
                    section = "Diff omitted to keep the history display responsive."
        body.extend(["", heading])
        if section:
            body.append(section)

    body.append(APPLY_PATCH_DISPLAY_END)
    return "\n".join(body)


def _preview_v4a_diff(diff: str, action: str, from_path: str, to_path: str) -> str:
    """Make snippet-relative unified hunks, just as edit_file does for old/new strings."""
    source_name = "/dev/null" if action == "create_file" else f"a/{from_path}"
    target_name = "/dev/null" if action == "delete_file" else f"b/{to_path}"
    hunks: list[str] = []
    old_lines: list[str] = []
    new_lines: list[str] = []

    def flush() -> None:
        if old_lines != new_lines:
            patch = _unified_diff(
                old_text="\n".join(old_lines) + ("\n" if old_lines else ""),
                new_text="\n".join(new_lines) + ("\n" if new_lines else ""),
                action=action,
                from_path=from_path,
                to_path=to_path,
            )
            hunks.extend(patch.splitlines()[2:])
        old_lines.clear()
        new_lines.clear()

    lines = diff.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    for line in lines:
        if line.startswith("@@"):
            flush()
        elif line == "*** End of File":
            continue
        elif line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        elif not line or line.startswith(" "):
            context = line[1:] if line else ""
            old_lines.append(context)
            new_lines.append(context)
        else:
            # Malformed raw input: never manufacture a plausible-looking diff.
            return ""
    flush()
    if not hunks:
        return ""
    return "\n".join([f"--- {source_name}", f"+++ {target_name}", *hunks])


def _presentation_payload(custom_data: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(custom_data, Mapping):
        return None
    payload = custom_data.get(APPLY_PATCH_CUSTOM_DATA_KEY)
    return payload if isinstance(payload, Mapping) else None


def _render_payload(payload: Mapping[str, Any]) -> str:
    raw_operations = payload.get("operations")
    operations = raw_operations if isinstance(raw_operations, Sequence) else []
    title = _title_for_count(len(operations))
    body: list[str] = [title, "", APPLY_PATCH_DISPLAY_START]
    emitted_chars = 0

    for raw_operation in operations:
        if not isinstance(raw_operation, Mapping):
            continue
        operation = PatchOperationPresentation(
            action=str(raw_operation.get("action") or "update_file"),
            path=str(raw_operation.get("path") or ""),
            move_to=_optional_string(raw_operation.get("move_to")),
            old_text=_optional_string(raw_operation.get("old_text")),
            new_text=_optional_string(raw_operation.get("new_text")),
            status=str(raw_operation.get("status") or "completed"),
            error=_optional_string(raw_operation.get("error")),
        )
        section, section_chars = _render_operation(operation, emitted_chars)
        body.extend(["", section])
        emitted_chars += section_chars

    body.extend([APPLY_PATCH_DISPLAY_END])
    return "\n".join(body)


def _render_fallback(*, raw_call: Any, output: Any) -> str:
    operations = _raw_operations(raw_call)
    title = _title_for_count(len(operations)) if operations else "Apply patch"
    body = [title, "", APPLY_PATCH_DISPLAY_START]
    if operations:
        for operation in operations:
            action = str(_mapping_value(operation, "type") or "update_file")
            path = str(_mapping_value(operation, "path") or "")
            move_to = _optional_string(_mapping_value(operation, "move_to"))
            body.extend(["", _operation_heading(action, path, move_to)])
    elif output:
        body.extend(["", str(output)])
    body.append(APPLY_PATCH_DISPLAY_END)
    return "\n".join(body)


def _render_operation(
    operation: PatchOperationPresentation, used_chars: int
) -> tuple[str, int]:
    heading = _operation_heading(operation.action, operation.path, operation.move_to)
    if operation.status != "completed":
        message = operation.error or "The patch operation failed."
        return f"### Failed {heading.removeprefix('### ')}\n{message}", 0

    if operation.old_text is None or operation.new_text is None:
        return heading, 0

    display_path = operation.move_to or operation.path
    from_path = operation.path
    diff = _unified_diff(
        old_text=operation.old_text,
        new_text=operation.new_text,
        action=operation.action,
        from_path=from_path,
        to_path=display_path,
    )
    if not diff:
        return heading, 0

    remaining = MAX_DIFF_CHARS_TOTAL - used_chars
    if len(diff) > MAX_DIFF_CHARS_PER_OPERATION or len(diff) > remaining:
        return (
            f"{heading}\nDiff omitted ({len(diff):,} characters) to keep the tool display responsive.",
            0,
        )
    return f"{heading}\n```diff\n{diff}\n```", len(diff)


def _unified_diff(
    *,
    old_text: str,
    new_text: str,
    action: str,
    from_path: str,
    to_path: str,
) -> str:
    source_name = "/dev/null" if action == "create_file" else f"a/{from_path}"
    target_name = "/dev/null" if action == "delete_file" else f"b/{to_path}"
    return "".join(
        line if line.endswith("\n") else f"{line}\n"
        for line in difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=source_name,
            tofile=target_name,
        )
    ).rstrip("\n")


def _operation_heading(action: str, path: str, move_to: str | None) -> str:
    normalized = action.removesuffix("_file")
    labels = {
        "create": "Create",
        "update": "Update",
        "delete": "Delete",
        "move": "Move",
    }
    label = labels.get(normalized, normalized.replace("_", " ").title() or "Update")
    if normalized == "move" or move_to:
        return f"### {label} `{path}` → `{move_to or path}`"
    return f"### {label} `{path}`"


def _title_for_count(count: int) -> str:
    return f"Apply patch: {count} {'file' if count == 1 else 'files'} changed"


def _raw_operations(raw_item: Any) -> list[Any]:
    operations = _mapping_value(raw_item, "operations")
    if isinstance(operations, Sequence) and not isinstance(operations, (str, bytes)):
        return list(operations)
    operation = _mapping_value(raw_item, "operation")
    return [operation] if operation is not None else []


def _item_type(item: Any) -> str | None:
    return _mapping_value(item, "type")


def _mapping_value(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
