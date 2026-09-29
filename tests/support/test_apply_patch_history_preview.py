"""History previews use persisted apply_patch inputs, not transient SDK display data."""

from siada.support.message_classifier import format_native_items_for_display
from siada.tools.coder.apply_patch_presentation import (
    APPLY_PATCH_DISPLAY_END,
    APPLY_PATCH_HISTORY_PREVIEW,
    render_apply_patch_history_preview,
)


def test_resume_replays_multi_file_requested_patch_from_raw_call():
    call = {
        "type": "apply_patch_call",
        "call_id": "call_patch",
        "operations": [
            {"type": "update_file", "path": "src/a.py", "diff": "@@ def run():\n old\n-before\n+after\n"},
            {"type": "create_file", "path": "new.py", "diff": "+first\n+second\n"},
            {"type": "delete_file", "path": "obsolete.py"},
            {"type": "update_file", "path": "old.py", "move_to": "moved.py", "diff": "@@\n-x\n+y\n"},
        ],
    }
    messages = format_native_items_for_display([
        call,
        {"type": "apply_patch_call_output", "call_id": "call_patch", "status": "completed", "output": "Updated src/a.py"},
    ])

    assert len(messages) == 1
    assert messages[0]["subtype"] == "tool_use"
    content = messages[0]["content"]
    assert APPLY_PATCH_HISTORY_PREVIEW in content
    assert "### Update `src/a.py`\n```diff" in content
    assert " old\n-before\n+after" in content
    assert "### Create `new.py`\n```diff" in content
    assert "+first\n+second" in content
    assert "### Delete `obsolete.py`" in content
    assert "Deletion requested" not in content
    assert "### Move `old.py` → `moved.py`\n```diff" in content
    assert content.endswith(APPLY_PATCH_DISPLAY_END)


def test_history_preview_labels_unverified_input_when_result_failed():
    call = {"type": "apply_patch_call", "operation": {
        "type": "update_file", "path": "src/a.py", "diff": "@@\n-old\n+new\n",
    }}
    messages = format_native_items_for_display([
        call,
        {"type": "apply_patch_call_output", "call_id": "call_patch", "status": "failed", "output": "Access denied"},
    ])

    assert len(messages) == 1
    assert APPLY_PATCH_HISTORY_PREVIEW in messages[0]["content"]
    assert "-old\n+new" in messages[0]["content"]
    assert "Access denied" not in messages[0]["content"]  # Same input-only semantics as edit_file history.


def test_history_preview_falls_back_for_missing_or_malformed_input():
    assert render_apply_patch_history_preview({"type": "apply_patch_call"}) == "Apply patch"
    result = render_apply_patch_history_preview({"operations": [
        {"type": "update_file", "path": "a.py", "diff": "not valid V4A"},
        {"type": "delete_file", "path": "old.py"},
    ]})
    assert "### Update `a.py`" in result
    assert "### Delete `old.py`" in result
    assert "Submitted patch" not in result
    assert "Deletion requested" not in result
    assert "```diff" not in result


def test_history_preview_caps_large_submitted_patches():
    content = render_apply_patch_history_preview({"operations": [
        {"type": "create_file", "path": "large.py", "diff": "+" + "x" * 41_000},
    ]})
    assert "### Create `large.py`" in content
    assert "Diff omitted to keep the history display responsive." in content
    assert len(content) < 1_000


def test_history_preview_only_shows_paths_for_missing_create_update_delete_diffs():
    content = render_apply_patch_history_preview({"operations": [
        {"type": "create_file", "path": "created.py"},
        {"type": "update_file", "path": "updated.py"},
        {"type": "delete_file", "path": "deleted.py"},
    ]})
    assert "### Create `created.py`\n\n### Update `updated.py`\n\n### Delete `deleted.py`" in content
    assert "unavailable" not in content
