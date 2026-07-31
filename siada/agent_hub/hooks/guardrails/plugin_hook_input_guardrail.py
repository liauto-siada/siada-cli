from __future__ import annotations

import json

from agents.tool_guardrails import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
)

from siada.services.plugins.hook_runner import get_active
from siada.io.io import InputOutput

# Maps siada tool names → Claude Code canonical tool names.
# Hooks written for Claude Code use these names for event routing and field matching.
_TOOL_NAME_MAP: dict[str, str] = {
    "run_cmd":   "Bash",
    "run_powershell": "Bash",
    "edit_file": "Edit",
    "create_file": "Write",
}

# Maps (canonical_tool_name, siada_field) → Claude Code canonical field name.
_FIELD_MAP: dict[tuple[str, str], str] = {
    ("Edit",  "new_str"):   "new_string",
    ("Edit",  "old_str"):   "old_string",
    ("Edit",  "path"):      "file_path",
    ("Edit",  "file_text"): "new_string",  # edit_file create command
    ("Write", "path"):      "file_path",
}


def _normalize_context(tool_name: str, tool_input: dict) -> tuple[str, dict]:
    """Translate siada tool/field names to Claude Code canonical form."""
    canonical = _TOOL_NAME_MAP.get(tool_name, tool_name)
    normalized = {
        _FIELD_MAP.get((canonical, k), k): v
        for k, v in tool_input.items()
    }
    # Synthetic 'content' field: aggregates all string values so 'all' event
    # rules (which use field='content') can match any tool's text content.
    if "content" not in normalized:
        parts = [v for v in normalized.values() if isinstance(v, str) and v]
        if parts:
            normalized["content"] = " ".join(parts)
    return canonical, normalized


async def _plugin_hook_input_fn(
    data: ToolInputGuardrailData,
) -> ToolGuardrailFunctionOutput:
    """PreToolUse hook guardrail: runs before each FunctionTool invocation."""
    runner = get_active()
    if runner is None:
        return ToolGuardrailFunctionOutput.allow()

    # tool_arguments is a raw JSON string from the SDK; parse it so hook scripts
    # receive a proper dict under "tool_input" and can access fields like "command".
    raw_args = data.context.tool_arguments
    try:
        tool_input = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (json.JSONDecodeError, TypeError):
        tool_input = {}

    canonical_name, normalized_input = _normalize_context(data.context.tool_name, tool_input)
    context_dict = {
        "tool_name": canonical_name,
        "tool_input": normalized_input,
    }
    responses = await runner.run_with_result("PreToolUse", context_dict)

    for resp in responses:
        if not resp.continue_:
            return ToolGuardrailFunctionOutput.raise_exception(
                output_info=resp.stop_reason or "Hook stopped this turn."
            )
        if resp.decision == "block":
            return ToolGuardrailFunctionOutput.reject_content(
                message=resp.reason or "Hook blocked this tool call.",
            )
        if resp.updated_input is not None:
            data.context.context.hook_pending_input_updates[
                data.context.tool_call_id
            ] = resp.updated_input
        if resp.additional_context is not None:
            io = InputOutput.get_instance()
            if io:
                io.print_error(resp.additional_context)
            data.context.context.hook_pending_contexts.append(resp.additional_context)

    return ToolGuardrailFunctionOutput.allow()


PLUGIN_HOOK_INPUT_GUARDRAIL = ToolInputGuardrail(
    guardrail_function=_plugin_hook_input_fn,
    name="plugin_hook_pre_tool_use",
)
