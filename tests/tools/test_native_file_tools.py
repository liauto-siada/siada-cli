"""Regression tests for the native patch file-tool surface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import (
    Agent,
    ApplyPatchTool,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    RunItemStreamEvent,
    Runner,
    ToolCallOutputItem,
)
from agents.editor import ApplyPatchOperation
from agents.models.openai_responses import Converter as OpenAIResponsesConverter
from agents.run_internal.run_loop import ToolRunApplyPatchCall
from agents.run_internal.tool_actions import ApplyPatchAction
from agents.testing import ScriptedModel
from agents.tool_context import ToolContext
from openai.types.responses import ResponseApplyPatchToolCall

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.sub_task_agent import _build_default_tools
from siada.foundation.siadaignore_controller import SiadaIgnoreController
from siada.tools.coder.native_file_tools import (
    APPLY_PATCH_DESCRIPTION,
    SiadaNativeApplyPatchEditor,
    create_native_apply_patch_tool,
    read_file,
)
from siada.tools.coder.apply_patch_presentation import (
    APPLY_PATCH_CUSTOM_DATA_KEY,
    APPLY_PATCH_DISPLAY_END,
    APPLY_PATCH_DISPLAY_START,
    render_apply_patch_display,
)
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory


class _Context:
    def __init__(self, root_dir: str, siadaignore_controller=None):
        self.root_dir = root_dir
        self.siadaignore_controller = siadaignore_controller


class _RunContext:
    def __init__(self, root_dir: str, siadaignore_controller=None):
        self.context = _Context(root_dir, siadaignore_controller)


def _operation(root_dir: str, **kwargs) -> ApplyPatchOperation:
    return ApplyPatchOperation(ctx_wrapper=_RunContext(root_dir), **kwargs)


def test_read_file_exposes_only_read_arguments_and_reuses_view_backend():
    schema = read_file.params_json_schema
    assert read_file.name == "read_file"
    assert set(schema["properties"]) == {"path", "view_range"}
    assert "command" not in schema["properties"]
    assert "old_str" not in schema["properties"]
    assert "new_str" not in schema["properties"]

    with TemporaryDirectory() as root:
        Path(root, "example.txt").write_text("first\nsecond\n", encoding="utf-8")
        tool_context = ToolContext(
            _Context(root),
            tool_name="read_file",
            tool_call_id="read-file-test",
            tool_arguments='{"path": "example.txt", "view_range": null}',
        )
        result = asyncio.run(read_file.on_invoke_tool(tool_context, tool_context.tool_arguments))

    assert "first" in result.content
    assert "second" in result.content


def test_read_file_pagination_never_refers_to_the_unregistered_edit_tool(monkeypatch):
    monkeypatch.setattr("siada.tools.coder.siada_editor.DEFAULT_MAX_LINES", 2)
    with TemporaryDirectory() as root:
        Path(root, "large.txt").write_text(
            "".join(f"line {index}\n" for index in range(5)), encoding="utf-8"
        )
        tool_context = ToolContext(
            _Context(root),
            tool_name="read_file",
            tool_call_id="read-file-pagination-test",
            tool_arguments='{"path": "large.txt", "view_range": null}',
        )
        result = asyncio.run(read_file.on_invoke_tool(tool_context, tool_context.tool_arguments))

    assert "file-reading tool" in result.content
    assert "edit_file" not in result.content


def test_read_file_formatter_has_a_read_only_display_contract():
    formatter = ToolCallFormatterFactory.get_formatter("read_file")

    ranged, complete = formatter.format_input(
        "call-read", "read_file", '{"path":"src/app.py","view_range":[4,12]}'
    )
    full, full_complete = formatter.format_input(
        "call-read", "read_file", '{"path":"README.md","view_range":null}'
    )

    assert complete is True
    assert ranged == "Read the file `src/app.py` from line 4 to line 12."
    assert full_complete is True
    assert full == "Read the file `README.md`."


def test_read_file_formatters_include_cwd_only_when_given():
    native = ToolCallFormatterFactory.get_formatter("read_file")
    edit = ToolCallFormatterFactory.get_formatter("edit_file")
    native_content, native_complete = native.format_input(
        "call-read", "read_file",
        '{"path":"src/app.py","view_range":[4,12],"cwd":"/tmp/work"}',
    )
    edit_content, edit_complete = edit.format_input(
        "call-view", "edit_file",
        '{"command":"view","path":"src/app.py","view_range":[4,12],"cwd":"/tmp/work"}',
    )
    expected = "Read the file `src/app.py` from line 4 to line 12.\ncwd: `/tmp/work`"
    assert native_complete and edit_complete
    assert native_content == edit_content == expected


def test_native_apply_patch_tool_keeps_its_contract():
    tool = create_native_apply_patch_tool()

    assert isinstance(tool, ApplyPatchTool)
    assert tool.name == "apply_patch"
    assert tool.type == "apply_patch"
    assert tool.description == APPLY_PATCH_DESCRIPTION
    assert "workspace-relative" in tool.description
    assert "Codex's file-oriented patch rules" not in tool.description


def test_astra_named_file_tool_imports_remain_compatible():
    from siada.tools.coder import astra_file_contract, astra_file_tools
    from siada.tools.coder.native_file_tools import NativeApplyPatchTool

    assert astra_file_contract.APPLY_PATCH_DESCRIPTION == APPLY_PATCH_DESCRIPTION
    assert astra_file_tools.read_file is read_file
    assert astra_file_tools.SiadaAstraApplyPatchEditor is SiadaNativeApplyPatchEditor
    assert astra_file_tools.AstraApplyPatchTool is NativeApplyPatchTool
    assert isinstance(astra_file_tools.create_astra_apply_patch_tool(), NativeApplyPatchTool)


def test_editor_creates_updates_moves_and_deletes_text_files():
    editor = SiadaNativeApplyPatchEditor()
    with TemporaryDirectory() as root:
        created = editor.create_file(
            _operation(
                root,
                type="create_file",
                path="src/example.txt",
                diff="+one\n+two\n",
            )
        )
        assert created.status == "completed"
        assert Path(root, "src/example.txt").read_text(encoding="utf-8") == "one\ntwo"

        updated = editor.update_file(
            _operation(
                root,
                type="update_file",
                path="src/example.txt",
                diff="@@\n one\n-two\n+three\n",
                move_to="src/renamed.txt",
            )
        )
        assert updated.status == "completed"
        assert "Moved src/example.txt to src/renamed.txt" in (updated.output or "")
        assert not Path(root, "src/example.txt").exists()
        assert Path(root, "src/renamed.txt").read_text(encoding="utf-8") == "one\nthree"

        deleted = editor.delete_file(
            _operation(root, type="delete_file", path="src/renamed.txt")
        )
        assert deleted.status == "completed"
        assert not Path(root, "src/renamed.txt").exists()


def test_editor_rejects_invalid_diff_without_modifying_file():
    editor = SiadaNativeApplyPatchEditor()
    with TemporaryDirectory() as root:
        file_path = Path(root, "example.txt")
        file_path.write_text("one\ntwo\n", encoding="utf-8")

        result = editor.update_file(
            _operation(
                root,
                type="update_file",
                path="example.txt",
                diff="@@\n missing\n-old\n+new\n",
            )
        )

        assert result.status == "failed"
        assert "Invalid Context" in (result.output or "")
        assert file_path.read_text(encoding="utf-8") == "one\ntwo\n"


def test_editor_rejects_workspace_escape_and_siadaignore_paths():
    editor = SiadaNativeApplyPatchEditor()
    with TemporaryDirectory() as root:
        controller = SiadaIgnoreController(root)
        Path(root, ".siadaignore").write_text("private.txt\n", encoding="utf-8")
        controller.initialize()

        escaped = editor.create_file(
            _operation(root, type="create_file", path="../outside.txt", diff="+blocked\n")
        )
        assert escaped.status == "failed"
        assert "parent-directory traversal" in (escaped.output or "")

        ignored = editor.create_file(
            ApplyPatchOperation(
                type="create_file",
                path="private.txt",
                diff="+blocked\n",
                ctx_wrapper=_RunContext(root, controller),
            )
        )
        assert ignored.status == "failed"
        assert ".siadaignore" in (ignored.output or "")
        assert not Path(root, "private.txt").exists()

        source = Path(root, "source.txt")
        source.write_text("before\n", encoding="utf-8")
        blocked_move = editor.update_file(
            ApplyPatchOperation(
                type="update_file",
                path="source.txt",
                diff="@@\n-before\n+after\n",
                move_to="private.txt",
                ctx_wrapper=_RunContext(root, controller),
            )
        )
        assert blocked_move.status == "failed"
        assert source.read_text(encoding="utf-8") == "before\n"
        assert not Path(root, "private.txt").exists()


def test_gpt5_or_newer_replaces_edit_file_with_native_patch_tools():
    agent = CodeGenAgent()

    for model_name in ("astra", "gpt-5.6-luna", "gpt-6-astra", "vendor-gpt-7-nova"):
        names = [getattr(tool, "name", "") for tool in agent._get_base_tools(model_name)]
        assert "read_file" in names
        assert "apply_patch" in names
        assert "edit_file" not in names
        assert any(
            isinstance(tool, ApplyPatchTool)
            for tool in agent._get_base_tools(model_name)
        )

    for model_name in ("claude-sonnet-5", "bailian-glm-5.3", "gpt-4.1"):
        names = [getattr(tool, "name", "") for tool in agent._get_base_tools(model_name)]
        assert "edit_file" in names
        assert "read_file" not in names
        assert "apply_patch" not in names


def test_non_fork_subtask_uses_the_same_gpt5_or_newer_file_tools():
    for model_name in ("astra", "gpt-5.6-luna", "gpt-6-astra", "vendor-gpt-7-nova"):
        names = [getattr(tool, "name", "") for tool in _build_default_tools(model_name=model_name)]
        assert "read_file" in names
        assert "apply_patch" in names
        assert "edit_file" not in names

    names = [getattr(tool, "name", "") for tool in _build_default_tools(model_name="claude-sonnet-5")]
    assert "edit_file" in names
    assert "read_file" not in names
    assert "apply_patch" not in names


def test_gpt5_or_newer_tools_convert_to_native_responses_apply_patch():
    for model_name in ("astra", "gpt-5.6-luna", "gpt-6-astra"):
        tools = CodeGenAgent()._get_base_tools(model_name)
        converted = OpenAIResponsesConverter.convert_tools(tools, handoffs=[])

        assert {tool.get("name") for tool in converted.tools if tool.get("type") == "function"} >= {
            "read_file",
            "run_cmd",
        }
        assert {tool.get("type") for tool in converted.tools} >= {"function", "apply_patch"}
        assert not any(
            tool.get("type") == "function" and tool.get("name") == "edit_file"
            for tool in converted.tools
        )


def test_native_apply_patch_sdk_output_keeps_call_id_and_display_custom_data():
    """Exercise the SDK's multi-operation compatibility path end to end."""

    async def execute_fixture():
        with TemporaryDirectory() as root:
            Path(root, "old.txt").write_text("old\n", encoding="utf-8")
            tool = create_native_apply_patch_tool()
            raw_call = {
                "type": "apply_patch_call",
                "call_id": "call_patch_fixture_001",
                "operations": [
                    {"type": "create_file", "path": "new.txt", "diff": "+new\n"},
                    {
                        "type": "update_file",
                        "path": "old.txt",
                        "diff": "@@\n-old\n+updated\n",
                    },
                    {"type": "delete_file", "path": "old.txt"},
                ],
            }
            result = await ApplyPatchAction.execute(
                agent=Agent(name="patch-fixture", tools=[tool]),
                call=ToolRunApplyPatchCall(tool_call=raw_call, apply_patch_tool=tool),
                hooks=RunHooks(),
                context_wrapper=RunContextWrapper(context=_Context(root)),
                config=RunConfig(),
            )
            return result, Path(root, "new.txt").read_text(encoding="utf-8")

    result, new_file = asyncio.run(execute_fixture())

    assert result.raw_item == {
        "type": "apply_patch_call_output",
        "call_id": "call_patch_fixture_001",
        "status": "completed",
        "output": "Created new.txt\nUpdated old.txt\nDeleted old.txt",
    }
    # The raw Responses item stays model-replayable; SDK-only renderer data is
    # deliberately attached to ToolCallOutputItem instead.
    assert "custom_data" not in result.raw_item
    display_data = result.custom_data[APPLY_PATCH_CUSTOM_DATA_KEY]
    assert display_data["call_id"] == "call_patch_fixture_001"
    assert [operation["action"] for operation in display_data["operations"]] == [
        "create_file",
        "update_file",
        "delete_file",
    ]
    assert display_data["operations"][1]["old_text"] == "old\n"
    assert display_data["operations"][1]["new_text"] == "updated\n"
    assert new_file == "new"

    rendered = render_apply_patch_display(
        custom_data=result.custom_data,
        output=result.output,
    )
    assert rendered.startswith("Apply patch: 3 files changed")
    assert APPLY_PATCH_DISPLAY_START in rendered
    assert "### Create `new.txt`" in rendered
    assert "### Update `old.txt`" in rendered
    assert "### Delete `old.txt`" in rendered
    assert "--- a/old.txt" in rendered
    assert APPLY_PATCH_DISPLAY_END in rendered


def test_native_apply_patch_recorder_captures_move_and_failure():
    async def execute_fixture():
        with TemporaryDirectory() as root:
            Path(root, "source.txt").write_text("before\n", encoding="utf-8")
            Path(root, "already.txt").write_text("present\n", encoding="utf-8")
            tool = create_native_apply_patch_tool()
            raw_call = {
                "type": "apply_patch_call",
                "call_id": "call_patch_move_failure",
                "operations": [
                    {
                        "type": "update_file",
                        "path": "source.txt",
                        "move_to": "renamed.txt",
                        "diff": "@@\n-before\n+after\n",
                    },
                    {"type": "create_file", "path": "already.txt", "diff": "+duplicate\n"},
                ],
            }
            return await ApplyPatchAction.execute(
                agent=Agent(name="patch-fixture", tools=[tool]),
                call=ToolRunApplyPatchCall(tool_call=raw_call, apply_patch_tool=tool),
                hooks=RunHooks(),
                context_wrapper=RunContextWrapper(context=_Context(root)),
                config=RunConfig(),
            )

    result = asyncio.run(execute_fixture())
    operations = result.custom_data[APPLY_PATCH_CUSTOM_DATA_KEY]["operations"]

    assert result.raw_item["call_id"] == "call_patch_move_failure"
    assert result.raw_item["status"] == "failed"
    assert operations[0]["action"] == "move"
    assert operations[0]["path"] == "source.txt"
    assert operations[0]["move_to"] == "renamed.txt"
    assert operations[0]["old_text"] == "before\n"
    assert operations[0]["new_text"] == "after\n"
    assert operations[1]["status"] == "failed"
    assert "already exists" in operations[1]["error"]


def test_streamed_native_patch_output_exposes_custom_data_before_conversation_consumes_it():
    """Lock the SDK timing used by ConversationTurn's native display branch."""

    async def stream_fixture():
        with TemporaryDirectory() as root:
            native_call = ResponseApplyPatchToolCall.model_validate(
                {
                    "id": "item_patch_stream_001",
                    "type": "apply_patch_call",
                    "call_id": "call_patch_stream_001",
                    "status": "completed",
                    "operation": {
                        "type": "create_file",
                        "path": "streamed.txt",
                        "diff": "+streamed\n",
                    },
                }
            )
            model = ScriptedModel([[native_call], []])
            result = Runner.run_streamed(
                Agent(
                    name="patch-stream-fixture",
                    model=model,
                    tools=[create_native_apply_patch_tool()],
                ),
                input="create a file",
                context=_Context(root),
                run_config=RunConfig(tracing_disabled=True),
            )
            custom_data = []
            async for event in result.stream_events():
                if isinstance(event, RunItemStreamEvent) and isinstance(
                    event.item, ToolCallOutputItem
                ):
                    custom_data.append(event.item.custom_data)
            return custom_data

    outputs = asyncio.run(stream_fixture())

    assert len(outputs) == 1
    assert outputs[0][APPLY_PATCH_CUSTOM_DATA_KEY]["call_id"] == "call_patch_stream_001"
    assert outputs[0][APPLY_PATCH_CUSTOM_DATA_KEY]["operations"][0]["new_text"] == "streamed"
