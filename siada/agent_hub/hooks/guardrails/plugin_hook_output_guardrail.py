from __future__ import annotations

from agents.tool_guardrails import (
    ToolGuardrailFunctionOutput,
    ToolOutputGuardrail,
    ToolOutputGuardrailData,
)

from siada.services.plugins.hook_runner import get_active


async def _plugin_hook_output_fn(
    data: ToolOutputGuardrailData,
) -> ToolGuardrailFunctionOutput:
    """PostToolUse hook guardrail: runs after each FunctionTool invocation."""
    runner = get_active()
    if runner is None:
        return ToolGuardrailFunctionOutput.allow()

    context_dict = {
        "tool_name": data.context.tool_name,
        "tool_output": str(data.output),
    }
    responses = await runner.run_with_result("PostToolUse", context_dict)

    for resp in responses:
        if not resp.continue_:
            return ToolGuardrailFunctionOutput.raise_exception(
                output_info=resp.stop_reason or "Hook stopped this turn."
            )
        if resp.updated_output is not None:
            return ToolGuardrailFunctionOutput.reject_content(
                message=resp.updated_output,
            )
        if resp.additional_context is not None:
            data.context.context.hook_pending_contexts.append(resp.additional_context)

    return ToolGuardrailFunctionOutput.allow()


PLUGIN_HOOK_OUTPUT_GUARDRAIL = ToolOutputGuardrail(
    guardrail_function=_plugin_hook_output_fn,
    name="plugin_hook_post_tool_use",
)
