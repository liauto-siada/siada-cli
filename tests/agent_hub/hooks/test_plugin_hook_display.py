from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.agent_hub.hooks.guardrails import plugin_hook_input_guardrail as pre
from siada.agent_hub.hooks.guardrails import plugin_hook_output_guardrail as post
from siada.services.plugins.types import HookResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("module,event", [(pre, "PreToolUse"), (post, "PostToolUse")])
async def test_hook_context_is_displayed_and_staged(module, event, monkeypatch):
    response = HookResponse(additional_context="Synthetic hook notice")
    runner = SimpleNamespace(run_with_result=AsyncMock(return_value=[response]))
    io = Mock()
    monkeypatch.setattr(module, "get_active", lambda: runner)
    monkeypatch.setattr(module.InputOutput, "get_instance", lambda: io)
    stage = Mock()
    monkeypatch.setattr("siada.services.session_runtime_state.stage_notification", stage)
    context = SimpleNamespace(
        tool_name="run_cmd", tool_arguments='{"command":"true"}',
        context=SimpleNamespace(), tool_call_id="synthetic",
    )
    data = SimpleNamespace(context=context, output="Synthetic output")
    fn = pre._plugin_hook_input_fn if module is pre else post._plugin_hook_output_fn
    await fn(data)
    io.print_hook.assert_called_once_with("Synthetic hook notice", event)
    io.print_error.assert_not_called()
    stage.assert_called_once_with(context.context, "Synthetic hook notice")


@pytest.mark.asyncio
async def test_blocked_tool_displays_hook_reason_without_staging(monkeypatch):
    runner = SimpleNamespace(run_with_result=AsyncMock(
        return_value=[HookResponse(decision="block", reason="Synthetic block")],
    ))
    io = Mock()
    monkeypatch.setattr(pre, "get_active", lambda: runner)
    monkeypatch.setattr(pre.InputOutput, "get_instance", lambda: io)
    context = SimpleNamespace(tool_name="run_cmd", tool_arguments="{}")
    result = await pre._plugin_hook_input_fn(SimpleNamespace(context=context))
    io.print_hook.assert_called_once_with("Synthetic block", "PreToolUse", status="blocked")
    assert result.behavior["type"] == "reject_content"