"""Offline checks for native tool isolation in the goal-verification fork."""

from unittest.mock import MagicMock

import pytest
from agents.editor import ApplyPatchOperation

from siada.services.goal.verifier import _wrap_tools_with_deny
from siada.services.sub_agent_run_config import adapt_fork_tools_for_effective_model
from siada.tools.coder.native_file_tools import NativeApplyPatchTool


@pytest.mark.parametrize("operation_type", ["create_file", "update_file", "delete_file"])
def test_native_patch_editor_rejects_without_touching_parent(operation_type):
    parent_editor = MagicMock()
    approval = MagicMock()
    extractor = MagicMock()
    original = NativeApplyPatchTool(
        editor=parent_editor,
        needs_approval=True,
        on_approval=approval,
        custom_data_extractor=extractor,
    )

    wrapped = _wrap_tools_with_deny([original])[0]
    operation = ApplyPatchOperation(type=operation_type, path="synthetic.txt", diff="+content")
    result = getattr(wrapped.editor, operation_type)(operation)

    assert result.status == "failed"
    assert "read-only" in result.output
    assert wrapped is not original
    assert wrapped.editor is not parent_editor
    assert wrapped.needs_approval is False
    assert wrapped.on_approval is None
    assert wrapped.custom_data_extractor is None
    assert original.editor is parent_editor
    assert original.needs_approval is True
    assert original.on_approval is approval
    assert original.custom_data_extractor is extractor
    assert parent_editor.mock_calls == []


def test_chat_model_adaptation_removes_native_patch_and_denies_replacement():
    original = NativeApplyPatchTool(editor=MagicMock())
    adapted = adapt_fork_tools_for_effective_model([original], "claude-sonnet-4-6")
    wrapped = _wrap_tools_with_deny(adapted)

    assert len(wrapped) == 1
    assert not isinstance(wrapped[0], NativeApplyPatchTool)
    assert wrapped[0].name == "edit_file"
    assert wrapped[0].tool_input_guardrails
    assert original.editor.mock_calls == []