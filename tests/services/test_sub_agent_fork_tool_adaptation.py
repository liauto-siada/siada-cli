"""Forked sub-agent tool adaptation for native apply_patch items.

Forked sub-agents inherit the parent's tool list verbatim (prompt-cache
alignment).  When ``conf.yaml`` routes sub-agents to a different, non-native
model, the inherited native ``ApplyPatchTool`` fails ChatCompletions tool
conversion ("Hosted tools are not supported with the ChatCompletions API");
``adapt_fork_tools_for_effective_model`` swaps it for ``edit_file`` in exactly
that case and leaves every other case untouched.
"""
from __future__ import annotations

from siada.services.sub_agent_run_config import adapt_fork_tools_for_effective_model
from siada.tools.coder.native_file_tools import create_native_apply_patch_tool
from siada.tools.coder.file_operator import edit


class TestAdaptForkToolsForEffectiveModel:
    def test_native_capable_model_keeps_tools_untouched(self):
        tools = [edit, create_native_apply_patch_tool()]
        assert adapt_fork_tools_for_effective_model(tools, "gpt-5.4") is tools

    def test_chat_model_swaps_native_patch_for_edit(self):
        native = create_native_apply_patch_tool()
        tools = [native]

        out = adapt_fork_tools_for_effective_model(tools, "kimi-k2-0905-preview")

        assert out is not tools
        assert out == [edit]
        # The inherited list (shared with the parent agent) is never mutated.
        assert tools == [native]

    def test_no_duplicate_edit_when_already_present(self):
        native = create_native_apply_patch_tool()
        out = adapt_fork_tools_for_effective_model([edit, native], "claude-sonnet-4.6")
        assert out == [edit]

    def test_noop_when_no_native_patch_tool_present(self):
        tools = [edit]
        assert adapt_fork_tools_for_effective_model(tools, "kimi-k2-0905-preview") is tools

    def test_noop_when_model_missing_or_tools_missing(self):
        native = create_native_apply_patch_tool()
        tools = [native]
        assert adapt_fork_tools_for_effective_model(tools, None) is tools
        assert adapt_fork_tools_for_effective_model(None, "kimi-k2-0905-preview") is None

    def test_swapped_tool_set_converts_for_chat_completions(self):
        from agents.models.chatcmpl_converter import Converter

        native = create_native_apply_patch_tool()
        out = adapt_fork_tools_for_effective_model([native], "glm-5")

        converted = [Converter.tool_to_openai(tool) for tool in out]
        assert converted[0]["function"]["name"] == "edit_file"
