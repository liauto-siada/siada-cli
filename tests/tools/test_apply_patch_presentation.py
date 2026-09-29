"""Regression tests for native patch text sent to the terminal UI."""

import pytest

from siada.tools.coder.apply_patch_presentation import (
    APPLY_PATCH_CUSTOM_DATA_KEY,
    render_apply_patch_display,
)


@pytest.mark.parametrize(
    ("old_text", "new_text"),
    [
        ("before", "after"),
        ("before", "after\n"),
        ("before\n", "after"),
    ],
)
def test_patch_display_separates_diff_lines_without_final_newline(old_text, new_text):
    display = render_apply_patch_display(
        custom_data={
            APPLY_PATCH_CUSTOM_DATA_KEY: {
                "operations": [
                    {
                        "action": "update_file",
                        "path": "progress.md",
                        "old_text": old_text,
                        "new_text": new_text,
                    }
                ]
            }
        }
    )

    assert "--- a/progress.md\n+++ b/progress.md" in display
    assert "@@ -1 +1 @@\n-before\n+after\n```" in display


def test_patch_display_keeps_multiline_hunk_parseable_without_final_newline():
    context = "阶段一已完成\n阶段二正在验证\n下一项是测试\n"
    display = render_apply_patch_display(
        custom_data={
            APPLY_PATCH_CUSTOM_DATA_KEY: {
                "operations": [
                    {
                        "action": "update_file",
                        "path": "progress.md",
                        "old_text": context + "旧的阶段记录",
                        "new_text": context + "新的阶段记录\n新增验证结果",
                    }
                ]
            }
        }
    )

    assert "@@ -1,4 +1,5 @@" in display
    assert "-旧的阶段记录\n+新的阶段记录\n+新增验证结果\n```" in display


def test_patch_display_shows_only_action_and_path_when_no_diff_is_available():
    display = render_apply_patch_display(
        custom_data={
            APPLY_PATCH_CUSTOM_DATA_KEY: {
                "operations": [
                    {"action": "create_file", "path": "empty.py", "old_text": "", "new_text": ""},
                    {"action": "update_file", "path": "missing.py"},
                    {"action": "delete_file", "path": "deleted.py"},
                ]
            }
        }
    )

    assert "### Create `empty.py`\n\n### Update `missing.py`\n\n### Delete `deleted.py`" in display
    assert "no displayable" not in display
    assert "without text changes" not in display


def test_patch_fallback_keeps_file_actions_without_an_unavailable_notice():
    display = render_apply_patch_display(
        custom_data=None,
        raw_call={"operations": [
            {"type": "create_file", "path": "empty.py"},
            {"type": "delete_file", "path": "deleted.py"},
        ]},
    )
    assert "### Create `empty.py`\n\n### Delete `deleted.py`" in display
    assert "unavailable" not in display
