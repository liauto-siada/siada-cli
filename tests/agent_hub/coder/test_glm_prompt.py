"""GLM-5.2-and-later template selection and coding-agent prompt delivery.

The GLM profile ships the ZCode CLI system prompt as a complete template
(``models/glm/templates/system.md``), rendered through the shared Markdown
template renderer with Siada's runtime facts, safety rules, and catalogs.

Contract under test:
- Selection: bare, provider-prefixed and ``-flash`` GLM-5.2 names and later
  generations use the profile; GLM-5.1 and older, unrelated names and other
  families keep their prompts.
- Delivery: the main coding path renders the template instead of the legacy
  intro/rules builder, in both interaction modes.
- Siada's edit_file tool surface, Git safety, OWASP rule, sub-agent switch,
  skills and agent catalogs, and framed combined memory are preserved.
"""

from pathlib import Path
from types import SimpleNamespace

from agents import RunContextWrapper
import pytest

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.assembly import glm, legacy
from siada.agent_hub.coder.prompt.selection.model_features import (
    is_glm_profile_model,
    uses_glm_prompt_profile,
)
from siada.agent_hub.coder.prompt.selection.profiles import PromptFamily, resolve_prompt_profile
from siada.services.skills import SkillMetadata, SkillScope, SkillUsageProfile, render_skills_section

GLM_PROFILE_MODELS = [
    "glm-5.2",
    "GLM-5.2",
    "lpai-glm-5.2",
    "lpai-glm-5.2-flash",
    "baidu-glm-5.2-flash",
    "bailian-glm-5.2",
    "kivy-glm-5.2",
    "openai/glm-5.2",
    "glm-5.3",
    "GLM-5.3",
    "lpai-glm-5.3",
    "lpai-glm-5.3-flash",
    "baidu-glm-5.3-flash",
    "bailian-glm-5.3",
    "kivy-glm-5.3",
    "openai/glm-5.3",
    # Later generations use the same profile.
    "glm-5.4",
    "kivy-glm-5.30",
    "glm-6",
    "lpai-glm-6.1-flash",
]

NON_PROFILE_MODELS = [
    None,
    "",
    "glm-5.1",
    "kivy-glm-5.1",
    "lpai-glm-5.1",
    "glm-4.6",
    "glm-5",
    "xglm-5.2",
    "xglm-5.3",
    "chatglm3-6b",
    "claude-sonnet-5",
    "gpt-5.6-luna",
    "gpt-6-astra",
    "kivy-kimi-k3",
    "kimi-k3",
    "kivy-deepseek-v4-flash",
]


@pytest.fixture
def render_prompt(monkeypatch):
    root = Path("/skills")
    skill = SkillMetadata("sample", "Sample instructions", root / "sample/SKILL.md", SkillScope.REPO)

    def fixed_skills(*_args, **kwargs):
        return render_skills_section(
            [skill], skill_roots={SkillScope.REPO: [root]}, usage_profile=kwargs["usage_profile"],
        )

    monkeypatch.setattr(code_gen_prompt.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(code_gen_prompt.os.path, "expanduser", lambda _path: "/home/synthetic")
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: "synthetic-user")
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: 128000)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", fixed_skills)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda _cwd: "# AGENT TYPES\n\n- reviewer")

    def render(model_name="glm-5.3", **overrides):
        arguments = {
            "model_name": model_name,
            "preferred_language": "zh-CN",
            "user_memory": "## Inline Memory\n\nSynthetic memory.",
        }
        arguments.update(overrides)
        return code_gen_prompt.get_system_prompt("/workspace/project", **arguments)

    return render


@pytest.mark.parametrize("model_name", GLM_PROFILE_MODELS)
@pytest.mark.parametrize("interactive_mode", [True, False])
def test_glm_5_2_family_and_later_select_one_template_and_keep_the_existing_tool_surface(
    render_prompt, model_name, interactive_mode,
):
    assert is_glm_profile_model(model_name) is True
    assert uses_glm_prompt_profile(model_name) is True
    profile = resolve_prompt_profile(model_name)
    assert profile.family is PromptFamily.GLM
    assert profile.native_patch_file_tools is False
    assert profile.skill_usage_profile is SkillUsageProfile.STRICT
    assert profile.extra_sections is None
    assert render_prompt(model_name, interactive_mode=interactive_mode) == render_prompt(
        interactive_mode=interactive_mode,
    )


@pytest.mark.parametrize("model_name", [
    "gpt-7-glm-5.3", "vendor-gpt-7-glm-6.1", "vendor/gpt-8-glm-5.3",
])
@pytest.mark.parametrize("interactive_mode", [True, False])
@pytest.mark.parametrize("subagent_enabled", [True, False])
def test_glm_mixed_future_gpt_aliases_keep_the_glm_delegation_policy(
    render_prompt, model_name, interactive_mode, subagent_enabled,
):
    assert resolve_prompt_profile(model_name).family is PromptFamily.GLM
    options = {"interactive_mode": interactive_mode, "subagent_enabled": subagent_enabled}
    prompt = render_prompt(model_name, **options)
    assert "# Delegation" not in prompt.splitlines()
    assert prompt == render_prompt(**options)


@pytest.mark.parametrize("model_name", NON_PROFILE_MODELS)
def test_glm_5_1_and_other_families_do_not_select_the_profile(model_name):
    assert is_glm_profile_model(model_name) is False
    assert uses_glm_prompt_profile(model_name) is False
    assert resolve_prompt_profile(model_name).family is not PromptFamily.GLM


def test_glm_main_path_uses_the_template_instead_of_legacy_rules(render_prompt, monkeypatch):
    monkeypatch.setattr(
        legacy, "get_rules_for_profile", lambda *args, **kwargs: pytest.fail("Legacy rules used"),
    )
    monkeypatch.setattr(
        legacy, "render_system_prompt", lambda **kwargs: pytest.fail("Legacy builder used"),
    )
    prompt = render_prompt()
    assert prompt.startswith(
        "You are an interactive Siada agent that helps users with software engineering tasks."
    )
    assert "You are Siada, an interactive coding agent" not in prompt
    headings = [
        "# Harness", "# Communicating with the user", "# Environment", "# Context management",
        "# CAPABILITIES", "# Runtime instructions", "# PREFERRED LANGUAGE", "# Skills",
        "# AGENT TYPES", "# Combined Memory",
    ]
    lines = prompt.splitlines()
    for heading in headings:
        assert lines.count(heading) == 1
    assert [lines.index(heading) for heading in headings] == sorted(
        lines.index(heading) for heading in headings
    )
    for legacy_text in (
        "# RULES", "# OBJECTIVE", "## IMPLEMENTATION MODE", "## NON-INTERACTIVE MODE",
        "## TO THE POINT", "fewer than 4 lines", "Minimize output tokens",
        "use 1-2 short paragraphs", "# SYSTEM INFORMATION", "${",
    ):
        assert legacy_text not in prompt


def test_glm_prompt_copies_the_zcode_system_prompt_text(render_prompt):
    prompt = render_prompt()
    # The identity sentence appears once: ZCode's separate one-line CLI prefix
    # message is dropped because Siada renders the prompt as a single string.
    assert prompt.count("You are an interactive Siada agent") == 1
    assert "You are an interactive Siada agent that helps users with software engineering tasks." in prompt
    assert "Assist with authorized security testing, defensive security, CTF challenges" in prompt
    assert "a denied call means the user declined it" in prompt
    assert "Reference code as `file_path:line_number`" in prompt
    assert "Lead with the outcome." in prompt
    assert "arrow chains like `A → B → fails`" in prompt
    assert "Write code that reads like the surrounding code" in prompt
    assert "noise the moment the PR merges" in prompt
    assert "For actions that are hard to reverse or outward-facing, confirm first" in prompt
    assert "Report outcomes faithfully" in prompt
    assert "You are operating autonomously." in prompt
    assert "Before ending your turn, check your last paragraph." in prompt
    assert "you don't need to wrap up early or hand off mid-task" in prompt
    assert "You have been invoked in the following environment:" in prompt
    assert "- Primary working directory: /workspace/project" in prompt
    assert "- Platform: Darwin" in prompt
    assert "- Home directory: /home/synthetic" in prompt
    assert "The current user is synthetic-user." in prompt


def test_glm_prompt_preserves_siada_tool_permission_and_safety_rules(render_prompt):
    prompt = render_prompt()
    assert "Use `edit_file` to inspect files and make text-file changes." in prompt
    for tool in ("edit_file", "regex_search_files", "list_code_definition_names", "run_cmd", "todo_write"):
        assert f"`{tool}`" in prompt
    for unsupported in ("`read_file`", "`apply_patch`", "`Bash`", "`Write`"):
        assert unsupported not in prompt
    assert "NEVER** revert existing changes you did not make unless explicitly requested" in prompt
    assert "OWASP top 10" in prompt
    assert "## Git Safety" in prompt


def test_glm_skills_catalog_keeps_aliases_without_the_old_usage_block(render_prompt):
    prompt = render_prompt()
    assert "Identify the skills relevant to your current task and read the skill file" in prompt
    assert "Instructions given directly by the user take precedence over skill guidance" in prompt
    assert "### Skill roots" in prompt
    assert "- `r0` = `/skills`" in prompt
    assert "sample: Sample instructions (file: r0/sample/SKILL.md)" in prompt
    assert "### How to use skills" not in prompt
    assert "you must use that skill for that turn" not in prompt
    assert prompt.splitlines().count("# Skills") == 1
    assert "## Skills" not in prompt.splitlines()


@pytest.mark.parametrize("interactive_mode", [True, False])
def test_glm_non_interactive_mode_reports_approval_blockers(render_prompt, interactive_mode):
    prompt = render_prompt(interactive_mode=interactive_mode)
    assert ("## Interaction mode" in prompt) is not interactive_mode
    assert ("you cannot ask the user anything" in prompt) is not interactive_mode
    assert ("do not infer approval from elapsed time" in prompt) is not interactive_mode
    assert "## Git Safety" in prompt


@pytest.mark.parametrize("blank", [None, "", " \n "])
def test_glm_optional_catalogs_memory_and_language_are_absent_when_not_supplied(
    render_prompt, monkeypatch, blank,
):
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: blank)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: blank)
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    prompt = render_prompt(user_memory=blank, preferred_language=None)
    for heading in ("# Skills", "# AGENT TYPES", "# Combined Memory", "# PREFERRED LANGUAGE"):
        assert heading not in prompt.splitlines()
    assert "The current user is" not in prompt
    assert "${" not in prompt


def test_glm_subagent_switch_drops_the_tool_and_catalog(render_prompt):
    prompt = render_prompt(subagent_enabled=False)
    assert "run_subtask" not in prompt
    assert "# AGENT TYPES" not in prompt
    assert "- reviewer" not in prompt


def test_glm_extra_capabilities_stay_in_the_capabilities_section(render_prompt):
    prompt = render_prompt(extra_capabilities=["- Extra capability."])
    assert prompt.index("# CAPABILITIES") < prompt.index("- Extra capability.") < prompt.index(
        "# Runtime instructions"
    )
    assert "- Extra capability.\n===" in prompt


def test_glm_runtime_values_are_literal_and_not_expanded_as_templates(render_prompt, monkeypatch):
    memory = "## Inline Memory\n\nKeep `${cwd}`, `$HOME`, `$(example)`, and `{literal}` verbatim."
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: "synthetic-${os}")
    prompt = render_prompt(user_memory=memory)
    assert memory in prompt
    assert "The current user is synthetic-${os}." in prompt
    assert "- Primary working directory: /workspace/project" in prompt


def test_glm_invalid_template_placeholder_fails_instead_of_shipping_unresolved_text(
    render_prompt, monkeypatch,
):
    monkeypatch.setattr(glm, "get_glm_template", lambda: "${missing_runtime_value}")
    with pytest.raises(KeyError, match="missing_runtime_value"):
        render_prompt()


@pytest.mark.parametrize("model_name", ["lpai-glm-5.2", "lpai-glm-5.3"])
def test_obsolete_prompt_switch_does_not_disable_glm_profile(render_prompt, monkeypatch, model_name):
    baseline = render_prompt(model_name)
    monkeypatch.setenv("SIADA_GLM_PROMPT_PROFILE", "off")

    assert uses_glm_prompt_profile(model_name) is True
    assert render_prompt(model_name) == baseline
    assert baseline.startswith(
        "You are an interactive Siada agent that helps users with software engineering tasks."
    )
    assert baseline != render_prompt("lpai-glm-5.1")


@pytest.mark.parametrize("model_name", ["lpai-glm-5.1", "claude-sonnet-4", "kimi-k2.6"])
def test_default_branch_prompt_is_unchanged_for_other_models(render_prompt, model_name):
    prompt = render_prompt(model_name)

    assert prompt.startswith(legacy.INTRO)
    assert "OBJECTIVE" in prompt
    assert "# Harness" not in prompt.splitlines()


@pytest.mark.parametrize("model_name", ["glm-5.2", "lpai-glm-5.3", "baidu-glm-5.3-flash", "glm-6"])
@pytest.mark.asyncio
async def test_coding_agent_delivers_the_glm_template_with_matching_file_tools(render_prompt, model_name):
    context = SimpleNamespace(
        root_dir="/workspace/project",
        combined_memory="## Inline Memory\n\nSynthetic memory.",
        preferred_language="zh-CN",
        interactive_mode=True,
        activated_skill_names=set(),
        subagent_enabled=True,
        session=SimpleNamespace(
            siada_config=SimpleNamespace(
                agent_name="CodeGenAgent", llm_config=SimpleNamespace(model_name=model_name),
            ),
        ),
    )
    agent = CodeGenAgent()
    prompt = await agent.get_system_prompt(RunContextWrapper(context=context))
    assert prompt == render_prompt(model_name)
    tools = {tool.name for tool in agent._get_base_tools(model_name=model_name)}
    assert "edit_file" in tools
    assert "read_file" not in tools
    assert "apply_patch" not in tools
    assert all(
        f"`{name}`" in prompt for name in (
            "edit_file", "regex_search_files", "run_cmd", "list_code_definition_names", "todo_write",
        )
    )
