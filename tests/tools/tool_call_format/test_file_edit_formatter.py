import json

import pytest

from siada.tools.tool_call_format.formatters import FileEditFormatter


@pytest.mark.parametrize("path", ["docs/notes.md", "docs/notes.markdown", "src/example.py"])
@pytest.mark.parametrize(
    ("old_string", "new_string", "ticks"),
    [
        ("old", "new", "```"),
        ("```python\nold\n```", "```python\nnew\n```", "````"),
        ("old", "````\nnew\n````", "`````"),
        ("old\nwith:\ntext", "new\nwith:\ntext", "```"),
        ("old\n\n", "", "```"),
        ("", "new\n\n", "```"),
    ],
)
def test_replacement_uses_collision_safe_fences(
    path: str, old_string: str, new_string: str, ticks: str
) -> None:
    language = "python" if path.endswith(".py") else "markdown"
    arguments = json.dumps(
        {"command": "str_replace", "path": path, "old_str": old_string, "new_str": new_string}
    )

    content, complete = FileEditFormatter().format_input("call", "edit_file", arguments)

    assert complete is True
    assert content == (
        f"In the file `{path}``, replace the string:\n"
        f"{ticks}{language}\n{old_string}\n{ticks}\nwith:\n"
        f"{ticks}{language}\n{new_string}\n{ticks}"
    )


def test_partial_replacement_does_not_emit_new_text() -> None:
    arguments = '{"command":"str_replace","path":"docs/notes.md","old_str":"old","new_str":"new'

    content, complete = FileEditFormatter().format_input("call", "edit_file", arguments)

    assert complete is False
    assert content == "In the file `docs/notes.md``, replace the string:\n```markdown\nold\n```"


def test_history_reconstructs_markdown_replacement_with_protocol_fences() -> None:
    from siada.support.message_classifier import format_native_items_for_display

    arguments = json.dumps(
        {"command": "str_replace", "path": "docs/notes.md", "old_str": "old", "new_str": "new"}
    )

    messages = format_native_items_for_display([
        {"type": "function_call", "name": "edit_file", "call_id": "call", "arguments": arguments},
        {"type": "function_call_output", "call_id": "call", "output": "File edited."},
    ])

    assert messages == [{
        "role": "assistant",
        "subtype": "tool_use",
        "content": "In the file `docs/notes.md``, replace the string:\n```markdown\nold\n```\nwith:\n```markdown\nnew\n```",
    }]