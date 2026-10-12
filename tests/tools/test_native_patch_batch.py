"""SDK multi-operation compatibility without private dispatch interception."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import Agent, ApplyPatchTool, RunConfig, RunContextWrapper, RunHooks
from agents.run_internal.run_loop import ToolRunApplyPatchCall
from agents.run_internal.tool_actions import ApplyPatchAction

from siada.foundation.siadaignore_controller import SiadaIgnoreController
from siada.tools.coder.apply_patch_presentation import APPLY_PATCH_CUSTOM_DATA_KEY
from siada.tools.coder.native_file_tools import create_native_apply_patch_tool


async def execute_batch(root, operations, *, tool=None, hooks=None, context=None, call_id="batch"):
    tool = tool or create_native_apply_patch_tool()
    context = context or SimpleNamespace(root_dir=str(root), siadaignore_controller=None)
    raw = {"type": "apply_patch_call", "call_id": call_id, "operations": operations}
    # The native protocol and ScriptedModel expose one operation per call.
    # Exercise the SDK's legacy multi-operation path without replacing it.
    return await ApplyPatchAction.execute(
        agent=Agent(name="patch-test", tools=[tool]),
        call=ToolRunApplyPatchCall(tool_call=raw, apply_patch_tool=tool),
        hooks=hooks or RunHooks(), context_wrapper=RunContextWrapper(context),
        config=RunConfig(tracing_disabled=True),
    )


@pytest.mark.asyncio
async def test_context_failure_only_fails_its_operation_and_returns_recovery(tmp_path):
    (tmp_path / "source.txt").write_text("current\n")
    operations = [
        {"type": "create_file", "path": "parent/new.txt", "diff": "+new\n"},
        {"type": "update_file", "path": "source.txt", "diff": "@@\n-old\n+changed\n"},
        {"type": "delete_file", "path": "source.txt"},
    ]
    result = await execute_batch(tmp_path, operations)
    assert result.raw_item["status"] == "failed"
    assert (tmp_path / "parent/new.txt").read_text() == "new"
    assert not (tmp_path / "source.txt").exists()
    assert "read_file" in result.output
    assert "Do not retry the unchanged patch" in result.output
    display = result.custom_data[APPLY_PATCH_CUSTOM_DATA_KEY]["operations"]
    assert [operation["status"] for operation in display] == ["completed", "failed", "completed"]


@pytest.mark.asyncio
async def test_failed_batch_does_not_poison_later_calls_on_same_tool(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("current\n")
    tool = create_native_apply_patch_tool()
    failed = await execute_batch(
        tmp_path,
        [{"type": "update_file", "path": "source.txt", "diff": "@@\n-old\n+changed\n"}],
        tool=tool,
    )
    completed = await execute_batch(
        tmp_path,
        [{"type": "update_file", "path": "source.txt", "diff": "@@\n-current\n+changed\n"}],
        tool=tool,
        call_id="retry-with-current-content",
    )
    assert failed.raw_item["status"] == "failed"
    assert completed.raw_item["status"] == "completed"
    assert source.read_text() == "changed\n"


@pytest.mark.asyncio
async def test_dependent_create_update_move_update_delete_operations(tmp_path):
    operations = [
        {"type": "create_file", "path": "one.txt", "diff": "+one\n"},
        {"type": "update_file", "path": "one.txt", "move_to": "sub/two.txt", "diff": "@@\n-one\n+two\n"},
        {"type": "update_file", "path": "sub/two.txt", "diff": "@@\n-two\n+three\n"},
        {"type": "delete_file", "path": "sub/two.txt"},
    ]
    result = await execute_batch(tmp_path, operations)
    assert result.raw_item["status"] == "completed"
    assert not (tmp_path / "one.txt").exists()
    assert not (tmp_path / "sub/two.txt").exists()
    display = result.custom_data[APPLY_PATCH_CUSTOM_DATA_KEY]["operations"]
    assert display[2]["old_text"] == "two"
    assert display[3]["old_text"] == "three"


@pytest.mark.asyncio
async def test_invalid_parent_does_not_undo_an_earlier_success(tmp_path):
    operations = [
        {"type": "create_file", "path": "parent", "diff": "+file\n"},
        {"type": "create_file", "path": "parent/child", "diff": "+child\n"},
    ]
    result = await execute_batch(tmp_path, operations)
    assert result.raw_item["status"] == "failed"
    assert (tmp_path / "parent").read_text() == "file"
    assert not (tmp_path / "parent/child").exists()
    assert "not a directory" in result.output


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_child", [False, True])
async def test_directories_created_by_earlier_operations_cannot_become_files(tmp_path, delete_child):
    operations = [{"type": "create_file", "path": "parent/child", "diff": "+child\n"}]
    if delete_child:
        operations.append({"type": "delete_file", "path": "parent/child"})
    operations.append({"type": "create_file", "path": "parent", "diff": "+file\n"})
    result = await execute_batch(tmp_path, operations)
    assert result.raw_item["status"] == "failed"
    assert (tmp_path / "parent").is_dir()
    assert (tmp_path / "parent/child").exists() == (not delete_child)
    assert "not a regular file" in result.output


@pytest.mark.asyncio
async def test_delete_file_then_create_directory_at_same_path(tmp_path):
    (tmp_path / "parent").write_text("old file\n")
    result = await execute_batch(
        tmp_path,
        [
            {"type": "delete_file", "path": "parent"},
            {"type": "create_file", "path": "parent/child", "diff": "+child\n"},
        ],
    )
    assert result.raw_item["status"] == "completed"
    assert (tmp_path / "parent/child").read_text() == "child"


@pytest.mark.asyncio
async def test_ignore_failure_rejects_its_operation_without_undoing_earlier_create(tmp_path):
    (tmp_path / ".siadaignore").write_text("private.txt\n")
    controller = SiadaIgnoreController(tmp_path)
    controller.initialize()
    context = SimpleNamespace(root_dir=str(tmp_path), siadaignore_controller=controller)
    result = await execute_batch(
        tmp_path,
        [
            {"type": "create_file", "path": "new.txt", "diff": "+new\n"},
            {"type": "create_file", "path": "private.txt", "diff": "+private\n"},
        ],
        context=context,
    )
    assert result.raw_item["status"] == "failed"
    assert (tmp_path / "new.txt").read_text() == "new"
    assert not (tmp_path / "private.txt").exists()
    assert ".siadaignore" in result.output


@pytest.mark.asyncio
async def test_runtime_failure_does_not_stop_later_operations_or_roll_back(tmp_path):
    tool = create_native_apply_patch_tool()
    original_write = tool.editor._write_text

    def fail_second(path, text):
        if path.name == "second.txt":
            raise OSError("simulated write failure")
        original_write(path, text)

    tool.editor._write_text = fail_second
    result = await execute_batch(
        tmp_path,
        [{"type": "create_file", "path": name, "diff": "+new\n"}
         for name in ("first.txt", "second.txt", "third.txt")],
        tool=tool,
    )
    assert result.raw_item["status"] == "failed"
    assert (tmp_path / "first.txt").read_text() == "new"
    assert not (tmp_path / "second.txt").exists()
    assert (tmp_path / "third.txt").read_text() == "new"
    display = result.custom_data[APPLY_PATCH_CUSTOM_DATA_KEY]["operations"]
    assert [operation["status"] for operation in display] == ["completed", "failed", "completed"]
    assert "simulated write failure" in result.output


@pytest.mark.asyncio
async def test_source_change_after_verification_is_not_overwritten(tmp_path):
    target = tmp_path / "source.txt"
    target.write_text("original\n")
    tool = create_native_apply_patch_tool()
    original_commit = tool.editor._commit_operation

    def mutate_before_commit(operation, prepared):
        target.write_text("external edit\n")
        return original_commit(operation, prepared)

    tool.editor._commit_operation = mutate_before_commit
    result = await execute_batch(
        tmp_path,
        [{"type": "update_file", "path": "source.txt", "diff": "@@\n-original\n+changed\n"}],
        tool=tool,
    )
    assert result.raw_item["status"] == "failed"
    assert target.read_text() == "external edit\n"
    assert "changed after patch verification" in result.output


@pytest.mark.asyncio
async def test_shared_tool_concurrent_calls_have_isolated_operation_results(tmp_path):
    tool = create_native_apply_patch_tool()
    editor = tool.editor
    hooks = RunHooks()

    async def yield_before_execution(*args):
        await asyncio.sleep(0)

    hooks.on_tool_start = AsyncMock(side_effect=yield_before_execution)
    results = await asyncio.gather(*[
        execute_batch(
            tmp_path,
            [{"type": "create_file", "path": f"{index}.txt", "diff": f"+{index}\n"}],
            tool=tool,
            hooks=hooks,
            call_id=f"batch-{index}",
        )
        for index in range(3)
    ])
    assert tool.editor is editor
    assert all(result.raw_item["status"] == "completed" for result in results)
    assert [result.raw_item["call_id"] for result in results] == [f"batch-{index}" for index in range(3)]
    assert [(tmp_path / f"{index}.txt").read_text() for index in range(3)] == ["0", "1", "2"]


@pytest.mark.asyncio
async def test_sdk_approval_blocks_verification_and_writes(tmp_path):
    tool = create_native_apply_patch_tool()
    tool.needs_approval = True
    tool.editor._prepare_operation = Mock(side_effect=AssertionError("verification before approval"))
    result = await execute_batch(
        tmp_path, [{"type": "create_file", "path": "new.txt", "diff": "+new\n"}], tool=tool,
    )
    assert result.type == "tool_approval_item"
    tool.editor._prepare_operation.assert_not_called()
    assert not (tmp_path / "new.txt").exists()


@pytest.mark.asyncio
async def test_foreign_sdk_editor_is_not_intercepted(tmp_path):
    editor = SimpleNamespace(create_file=Mock(return_value="foreign result"))
    result = await execute_batch(
        tmp_path,
        [{"type": "create_file", "path": "new.txt", "diff": "+new\n"}],
        tool=ApplyPatchTool(editor=editor),
    )
    assert result.output == "foreign result"
    editor.create_file.assert_called_once()
