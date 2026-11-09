from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from agents import RunConfig, RunContextWrapper
from agents.tool_context import ToolContext
import pytest

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder import sub_task_agent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.models.gpt6.multi_agent import EXPLICIT_REQUEST_ONLY
from siada.agent_hub.coder.prompt.sections.capabilities import get_capabilities_section
from siada.foundation.code_agent_context import CodeAgentContext
from siada.provider.retry import MissingFinalResponseError
from siada.services.agents import AgentScope, UserAgentDefinition
from siada.tools.agent import run_subtask as subtask


EXTRA_PROACTIVE_GUIDANCE = (
    "Proactively reach for this tool when a piece of work has a clear, self-contained\n"
    "boundary, would otherwise pollute your own context with a large amount of\n"
    "unrelated intermediate exploration, or can be carried out independently in\n"
    "parallel with other work — don't wait for the user to explicitly ask for a\n"
    "sub-agent.\n\n"
)
UPSTREAM_DELEGATION_GUIDANCE = (
    "Start independent delegations with `run_subtask` together in one assistant message "
    "and continue useful work while they run."
)


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_arguments, **_options: None)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda _cwd: None)
    monkeypatch.setattr(sub_task_agent, "_get_skills_hint_section", lambda _cwd: "")


@pytest.mark.parametrize("model_name", [
    "deepseek-v4-flash", "DEEPSEEK-V4-PRO", "baidu-deepseek-v4.1-flash",
    "openai/deepseek-v4-pro", "vendor_deepseek_v4",
])
def test_deepseek_tool_only_removes_proactive_guidance_and_keeps_sdk_contract(model_name):
    tool = subtask.create_run_subtask_tool(model_name)
    assert tool is not subtask.run_subtask
    assert tool.description == subtask.RUN_SUBTASK_DOCS.replace(EXTRA_PROACTIVE_GUIDANCE, "", 1)
    assert tool.description == subtask.NEUTRAL_RUN_SUBTASK_DOCS
    assert tool.__wrapped__ is subtask.run_subtask.__wrapped__
    assert tool.params_json_schema == subtask.run_subtask.params_json_schema
    assert tool.needs_approval is subtask.run_subtask.needs_approval
    assert tool.is_enabled is subtask.run_subtask.is_enabled
    assert "Proactively" not in tool.description
    assert "don't wait for the user" not in tool.description
    assert "current in-flight turn" not in tool.description
    for unsupported in ("send_message", "agent_preset", "subagent_fork", "list_subagent_models"):
        assert unsupported not in tool.description
    selected = CodeGenAgent()._get_base_tools(model_name=model_name)
    assert next(item for item in selected if item.name == "run_subtask").description == tool.description
    assert subtask.run_subtask.description == subtask.RUN_SUBTASK_DOCS


@pytest.mark.parametrize("interactive_mode", [True, False])
def test_deepseek_system_prompt_has_only_the_upstream_delegation_instruction(
    tmp_path, interactive_mode,
):
    prompt = code_gen_prompt.get_system_prompt(
        str(tmp_path), model_name="deepseek-v4-flash", interactive_mode=interactive_mode,
    )
    assert prompt.count(UPSTREAM_DELEGATION_GUIDANCE) == 1
    assert "Proactively reach for" not in prompt
    assert "don't wait for the user" not in prompt
    assert EXPLICIT_REQUEST_ONLY not in prompt
    assert "run_subtask" not in get_capabilities_section("deepseek-v4-flash")


def test_deepseek_does_not_customize_tool_identity_arguments_or_returns():
    description = subtask.create_run_subtask_tool("deepseek-v4-flash").description
    original = subtask.RUN_SUBTASK_DOCS
    assert description.partition("\n\n")[0] == original.partition("\n\n")[0]
    assert description[description.index("Args:"):] == original[original.index("Args:"):]


@pytest.mark.parametrize("model_name", [
    None, "claude-sonnet-5", "gpt-5.4", "glm-5.3", "kimi-k3",
    "glm-5.3-deepseek", "kimi-k3-deepseek", "vendor-gpt-5-deepseek-v4",
])
def test_other_model_tools_keep_the_original_description(model_name):
    assert subtask.create_run_subtask_tool(model_name) is subtask.run_subtask
    assert subtask.run_subtask.description == subtask.RUN_SUBTASK_DOCS


@pytest.mark.parametrize("model_name", ["astra-deepseek", "gpt-6-deepseek", "gpt-7-deepseek"])
def test_conflicting_gpt_models_keep_the_gpt_delegation_policy(model_name):
    assert subtask.create_run_subtask_tool(model_name).description == subtask.GPT6_RUN_SUBTASK_DOCS


@pytest.mark.parametrize("model_name", ["deepseek-v4-flash", "gpt-6-astra", "glm-5.3", "kimi-k3"])
@pytest.mark.parametrize("recursive", [True, False])
@pytest.mark.asyncio
async def test_recursive_children_keep_shared_instructions_and_only_remove_deepseek_tool_guidance(
    tmp_path, model_name, recursive,
):
    agent = sub_task_agent.SubTaskAgent(model_name=model_name, include_run_subtask=recursive)
    context = RunContextWrapper(context=CodeAgentContext(root_dir=str(tmp_path)))
    prompt = await agent.get_system_prompt(context)
    delegation_tools = [tool for tool in agent.tools if tool.name == "run_subtask"]
    assert bool(delegation_tools) is recursive
    if not recursive:
        assert "# Delegation" not in prompt
        assert "## Delegating Part of Your Task" not in prompt
    elif model_name.startswith("deepseek"):
        assert sub_task_agent._SUBTASK_RECURSIVE_HINT in prompt
        assert delegation_tools[0].description == subtask.NEUTRAL_RUN_SUBTASK_DOCS
    else:
        assert sub_task_agent._SUBTASK_RECURSIVE_HINT in prompt
        assert delegation_tools[0] is subtask.run_subtask


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled, is_subagent, expected", [
    (True, False, "Child result."), (False, False, "disabled by configuration"),
    (True, True, "not available to you"),
])
async def test_deepseek_adapted_tool_keeps_execution_and_runtime_guards(
    tmp_path, monkeypatch, enabled, is_subagent, expected,
):
    implementation = AsyncMock(return_value="Child result.")
    monkeypatch.setattr(subtask, "run_subtask_impl", implementation)
    context = RunContextWrapper(context=CodeAgentContext(
        root_dir=str(tmp_path), subagent_enabled=enabled, is_subagent=is_subagent,
    ))
    tool_context = ToolContext.from_agent_context(
        context, "synthetic-call", tool_name="run_subtask", tool_arguments="{}",
    )
    result = await subtask.create_run_subtask_tool("deepseek-v4-flash").on_invoke_tool(
        tool_context, '{"instruction":"Complete this task."}',
    )
    assert expected in result
    if enabled and not is_subagent:
        implementation.assert_awaited_once()
        assert implementation.call_args.kwargs["instruction"] == "Complete this task."
        assert implementation.call_args.kwargs["fork"] is False
    else:
        implementation.assert_not_awaited()


@pytest.mark.asyncio
async def test_fork_history_is_the_effective_snapshot_not_a_completed_turn_slice():
    history = [
        {"role": "user", "content": "Earlier task."},
        {"role": "assistant", "content": "Earlier answer."},
        {"role": "user", "content": "Current task."},
        {"role": "user", "content": "Current task."},
    ]
    store = SimpleNamespace(get_runtime_items=AsyncMock(return_value=history))
    tools = [subtask.create_run_subtask_tool("deepseek-v4-flash")]
    parent = SimpleNamespace(tools=tools, get_system_prompt=AsyncMock(return_value="Parent prompt."))
    context = RunContextWrapper(context=SimpleNamespace(session=SimpleNamespace(openai_session=store)))
    context.agent = parent
    inherited_tools, inherited_prompt, inherited_history = await subtask._build_fork_materials(context)
    assert inherited_prompt == "Parent prompt."
    assert inherited_tools == tools
    assert inherited_tools is not tools
    assert inherited_history == history
    assert inherited_history is not history
    store.get_runtime_items.assert_awaited_once_with()


@pytest.mark.parametrize("model_name, fork, parent_available, named_agent, retry", [
    ("deepseek-v4-flash", True, True, False, False),
    ("deepseek-v4-flash", True, True, False, True),
    ("deepseek-v4-flash", True, False, False, False),
    ("deepseek-v4-flash", True, True, True, False),
    ("deepseek-v4-flash", False, True, False, False),
    ("claude-sonnet-5", True, True, False, False),
    ("gpt-5.4", True, True, False, False),
    ("gpt-6-astra", True, True, False, False),
    ("glm-5.3", True, True, False, False),
    ("kimi-k3", True, True, False, False),
])
@pytest.mark.asyncio
async def test_fork_input_tools_and_prompt_remain_unchanged_for_all_models(
    tmp_path, monkeypatch, model_name, fork, parent_available, named_agent, retry,
):
    async def empty_events():
        for event in ():
            yield event

    result = SimpleNamespace(final_output="Child result.", new_items=[], stream_events=empty_events)
    responses = [MissingFinalResponseError(
        model=model_name, response_id=None, last_event=None, output_exposed=False,
    ), result] if retry else [result]
    runner = MagicMock(side_effect=responses)
    monkeypatch.setattr(subtask.Runner, "run_streamed", runner)
    monkeypatch.setattr(subtask.asyncio, "sleep", AsyncMock())
    tools = [subtask.create_run_subtask_tool(model_name)]
    history = [] if retry else [{"role": "user", "content": "Inherited context."}]
    materials = AsyncMock(return_value=(tools, "Parent prompt.", history))
    monkeypatch.setattr(subtask, "_build_fork_materials", materials)
    context = CodeAgentContext(root_dir=str(tmp_path))
    run_context = RunContextWrapper(context=context) if parent_available else None
    definition = UserAgentDefinition(
        name="reviewer", description="Reviews code.", prompt="Review code carefully.",
        path=tmp_path / "reviewer.md", scope=AgentScope.REPO,
    ) if named_agent else None
    summary = await subtask.run_subtask_impl(
        instruction="Inspect this module.", agent_context=context,
        run_config=RunConfig(model=model_name, tracing_disabled=True), fork=fork,
        run_ctx=run_context, agent_definition=definition,
    )
    assert summary == "Child result."
    actual_fork = fork and parent_available and not named_agent
    expected_input = "Inspect this module."
    assert runner.call_count == len(responses)
    for call in runner.call_args_list:
        assert call.kwargs["input"] == expected_input
    child = runner.call_args.kwargs["starting_agent"]
    if actual_fork:
        materials.assert_awaited_once()
        assert child.instructions == "Parent prompt."
        assert child.tools == tools
        assert child.tools[0] is tools[0]
        assert await runner.call_args.kwargs["session"].get_items() == history
    else:
        materials.assert_not_awaited()
    if named_agent:
        assert child.definition_prompt == "Review code carefully."


@pytest.mark.parametrize("background, async_mode", [(False, False), (False, True), (True, False)])
@pytest.mark.asyncio
async def test_deepseek_named_agent_background_setting_overrides_async_argument(
    tmp_path, monkeypatch, background, async_mode,
):
    definition = UserAgentDefinition(
        name="reviewer", description="Reviews code.", prompt="Review code carefully.",
        path=tmp_path / "reviewer.md", scope=AgentScope.REPO, background=background,
    )
    monkeypatch.setattr(subtask, "resolve_user_agent_definition", lambda *_arguments: definition)
    implementation = AsyncMock(return_value="Child result.")
    registration = MagicMock(return_value="synthetic-task")
    monkeypatch.setattr(subtask, "run_subtask_impl", implementation)
    monkeypatch.setattr(subtask, "register_background_subtask", registration)
    result = await subtask.run_subtask.__wrapped__(
        RunContextWrapper(context=CodeAgentContext(root_dir=str(tmp_path))),
        instruction="Review this module.", agent="reviewer", async_mode=async_mode,
    )
    if background or async_mode:
        assert "task_id=synthetic-task" in result
        registration.assert_called_once()
        implementation.assert_not_awaited()
    else:
        assert result == "Child result."
        implementation.assert_awaited_once()
        registration.assert_not_called()
