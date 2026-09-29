"""Role mapping in ``_format_history_for_telemetry``.

Native Responses items (``apply_patch_call`` and friends) carry no ``role``
key, so the formatter classifies them by type.  Regression guard: they are
assistant-origin model output and must never be filed as user messages.
"""

from __future__ import annotations

import siada.session.session_manager as session_manager_module


def _formatter():
    """Return the telemetry history formatter without depending on its name."""
    return next(
        obj
        for obj in vars(session_manager_module).values()
        if isinstance(obj, type) and "_format_history_for_telemetry" in obj.__dict__
    )._format_history_for_telemetry


def test_apply_patch_call_is_classified_as_assistant():
    history = [
        {
            "id": "apc_1",
            "call_id": "call_1",
            "type": "apply_patch_call",
            "status": "completed",
            "operation": {"type": "update_file", "path": "README.md", "diff": "@@"},
        }
    ]

    formatted = _formatter()(history)

    assert formatted[0]["role"] == "assistant"
    assert formatted[0]["content"][0]["type"] == "apply_patch_call"


def test_native_tool_call_items_are_classified_as_assistant():
    types = [
        "shell_call",
        "local_shell_call",
        "custom_tool_call",
        "computer_call",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "web_search_call",
        "file_search_call",
    ]

    formatted = _formatter()([{"type": item_type, "call_id": "call_1"} for item_type in types])

    assert [row["role"] for row in formatted] == ["assistant"] * len(types)


def test_reasoning_and_function_call_stay_assistant():
    formatted = _formatter()(
        [
            {"type": "reasoning", "summary": []},
            {"type": "function_call", "call_id": "c", "name": "x", "arguments": "{}"},
        ]
    )

    assert [row["role"] for row in formatted] == ["assistant", "assistant"]


def test_tool_outputs_stay_user():
    formatted = _formatter()(
        [{"type": "apply_patch_call_output", "call_id": "call_1", "output": "ok"}]
    )

    assert formatted[0]["role"] == "user"


def test_explicit_role_is_respected():
    formatted = _formatter()(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "output_text", "text": "hello"}]},
        ]
    )

    assert [row["role"] for row in formatted] == ["user", "assistant"]
    assert formatted[1]["content"][0] == {"type": "output_text", "text": "hello"}
