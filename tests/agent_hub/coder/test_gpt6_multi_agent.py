"""Offline prompt and tool contracts for GPT-6+ delegation policy."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunContextWrapper
from agents.tool_context import ToolContext

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.models.gpt6.multi_agent import EXPLICIT_REQUEST_ONLY
from siada.agent_hub.coder.prompt.models.gpt6.templates import get_gpt6_template
from siada.agent_hub.coder.prompt.sections.capabilities import get_capabilities_section
from siada.agent_hub.coder.prompt.selection.model_features import is_gpt6_model
from siada.foundation.code_agent_context import CodeAgentContext
from siada.session.session_models import RunningSession
from siada.tools.agent import run_subtask as subtask
from siada.tools.agent.run_subtask import (
    GPT6_RUN_SUBTASK_DOCS,
    RUN_SUBTASK_DOCS,
    create_run_subtask_tool,
    run_subtask,
)


GPT6_MODELS = (
    "gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna", "astra",
    "vendor-gpt-6.1-sol", "vendor-gpt-7-nova", "gpt-8.1-sol",
)


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: None)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(
        code_gen_prompt, "get_agents_section", lambda _cwd: "# AGENT TYPES\n- reviewer",
    )


@pytest.mark.parametrize("model_name", GPT6_MODELS)
@pytest.mark.parametrize("interactive_mode", [True, False])
def test_primary_delegates_only_on_explicit_requests(
    model_name, interactive_mode, tmp_path,
):
    prompt = code_gen_prompt.get_system_prompt(
        str(tmp_path), model_name=model_name, interactive_mode=interactive_mode,
    )
    if is_gpt6_model(model_name):
        assert prompt.startswith(get_gpt6_template(model_name))
    else:
        assert prompt.startswith("You are Siada, a highly skilled software engineer")
    assert "# Multi-agent role" not in prompt
    assert "You are the primary agent in a team of agents" not in prompt
    assert prompt.count(EXPLICIT_REQUEST_ONLY) == 1
    assert prompt.splitlines().count("# Delegation") == 1
    capabilities = get_capabilities_section(model_name)
    assert "You can use `run_subtask`" in capabilities
    assert "Use `run_subtask` for self-contained" not in capabilities
    assert "Proactively reach for" not in capabilities
    for unavailable in ("spawn_agent", "followup_task", "send_message", "wait_agent", "fork_turns", "ultra"):
        assert unavailable not in prompt


@pytest.mark.parametrize("model_name", GPT6_MODELS)
def test_disabled_subagents_do_not_advertise_delegation(model_name, tmp_path):
    prompt = code_gen_prompt.get_system_prompt(
        str(tmp_path), model_name=model_name, subagent_enabled=False,
    )
    assert "run_subtask" not in prompt
    assert "# AGENT TYPES" not in prompt
    assert "# Multi-agent role" not in prompt
    assert EXPLICIT_REQUEST_ONLY not in prompt
    assert "# Delegation" not in prompt
    assert "CAPABILITIES" in prompt


@pytest.mark.parametrize("model_name", GPT6_MODELS)
def test_neutral_tool_keeps_schema_and_invocation_without_mutating_other_models(model_name):
    tool = create_run_subtask_tool(model_name)
    assert tool is not run_subtask
    assert tool.description == GPT6_RUN_SUBTASK_DOCS
    assert tool.__wrapped__ is run_subtask.__wrapped__
    assert tool.params_json_schema == run_subtask.params_json_schema
    assert tool.needs_approval is run_subtask.needs_approval
    assert tool.is_enabled is run_subtask.is_enabled
    assert "Proactively reach" not in tool.description
    assert tool.description[tool.description.index("Args:"):] == (
        RUN_SUBTASK_DOCS[RUN_SUBTASK_DOCS.index("Args:"):]
    )
    assert run_subtask.description == RUN_SUBTASK_DOCS
    assert create_run_subtask_tool("gpt-5.4") is run_subtask
    assert create_run_subtask_tool("claude-sonnet-5") is run_subtask
    selected = CodeGenAgent()._get_base_tools(model_name=model_name)
    subtask_tool = next(tool for tool in selected if tool.name == "run_subtask")
    assert subtask_tool.description == GPT6_RUN_SUBTASK_DOCS


@pytest.mark.parametrize("model_name", [None, "gpt-5.4", "claude-sonnet-5", "lpai-glm-5.3", "kimi-k3"])
def test_other_model_tools_preserve_the_original_description(model_name):
    assert create_run_subtask_tool(model_name) is run_subtask
    assert create_run_subtask_tool(model_name).description == RUN_SUBTASK_DOCS
    assert "Proactively reach for this tool" in RUN_SUBTASK_DOCS


@pytest.mark.asyncio
async def test_reused_primary_agent_refreshes_delegation_after_model_switch(tmp_path, monkeypatch):
    session = MagicMock(spec=RunningSession)
    session.session_id = "model-switch-test"
    session.siada_config = MagicMock()
    session.siada_config.agent_name = None
    context = CodeAgentContext(
        root_dir=str(tmp_path), session=session, provider="default",
        web_tools_enabled=False, memory_tools_enabled=False,
    )
    monkeypatch.setattr(
        "siada.agent_hub.coder.code_gen_agent.get_available_lark_tools", lambda: [],
    )
    agent = CodeGenAgent()
    for model_name in ("gpt-6-luna", "gpt-5.4", "gpt-7-astra", "claude-sonnet-5", "astra"):
        session.siada_config.llm_config = SimpleNamespace(model_name=model_name, provider="default")
        agent.configure_tools_for_context(context)
        tool = next(tool for tool in agent.tools if tool.name == "run_subtask")
        explicit_only = model_name in ("gpt-6-luna", "gpt-7-astra", "astra")
        expected = GPT6_RUN_SUBTASK_DOCS if explicit_only else RUN_SUBTASK_DOCS
        assert tool.description == expected
        prompt = await agent.get_system_prompt(RunContextWrapper(context=context))
        assert (EXPLICIT_REQUEST_ONLY in prompt) is explicit_only


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled, is_subagent, expected",
    [(True, False, "Child result."), (False, False, "disabled by configuration"),
     (True, True, "not available to you")],
)
async def test_adapted_tool_preserves_execution_and_runtime_guards(
    tmp_path, monkeypatch, enabled, is_subagent, expected,
):
    impl = AsyncMock(return_value="Child result.")
    monkeypatch.setattr(subtask, "run_subtask_impl", impl)
    context = CodeAgentContext(
        root_dir=str(tmp_path), subagent_enabled=enabled, is_subagent=is_subagent,
    )
    run_ctx = RunContextWrapper(context=context)
    tool_ctx = ToolContext.from_agent_context(
        run_ctx, "subtask-call", tool_name="run_subtask", tool_arguments="{}",
    )
    tool = create_run_subtask_tool("gpt-6-astra")
    result = await tool.on_invoke_tool(tool_ctx, '{"instruction":"Complete this task."}')
    assert expected in result
    if enabled and not is_subagent:
        impl.assert_awaited_once()
        assert impl.call_args.kwargs["instruction"] == "Complete this task."
        assert impl.call_args.kwargs["fork"] is False
    else:
        impl.assert_not_awaited()