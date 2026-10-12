"""Regression coverage for the GLM-5.2-and-later prompt profile (GLM53-S2).

Contract under test:
- Selection: bare, provider-prefixed and ``-flash`` GLM-5.2 names and later
  generations use the profile; GLM-5.1 and older, unrelated names and other
  families keep their prompts.
- Only the identity/behaviour text is replaced: CAPABILITIES, the skills and
  agent catalogs and Combined Memory keep their shared text and order.
- Non-interactive constraints retain the model profile and safety rules.
- GLM-5.2 and later always use this profile, regardless of obsolete opt-outs.
"""

import ast
from pathlib import Path

import pytest

from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.sections.capabilities import get_capabilities_section
from siada.agent_hub.coder.prompt.models.glm.instructions import (
    GLM_INTRO,
    is_glm_profile_model,
    uses_glm_prompt_profile,
)
from siada.agent_hub.coder.prompt.selection.model_features import uses_native_patch_file_tools
from siada.agent_hub.coder.prompt.sections.memory import MEMORY_SECTION_TITLE
from siada.agent_hub.coder.prompt.sections.rules.dispatch import get_rules_section
from siada.agent_hub.coder.prompt.selection.skill_usage import resolve_skill_usage_profile
from siada.services.skills import SkillUsageProfile

GLM_PROFILE_MODELS = [
    "glm-5.2",
    "GLM-5.2",
    "zhipuai/glm-5.2",
    "zhipuai/glm-5.2-flash",
    "baidu-glm-5.2-flash",
    "bailian-glm-5.2",
    "z-ai/glm-5.2",
    "openai/glm-5.2",
    "glm-5.3",
    "GLM-5.3",
    "zhipuai/glm-5.3",
    "zhipuai/glm-5.3-flash",
    "baidu-glm-5.3-flash",
    "bailian-glm-5.3",
    "z-ai/glm-5.3",
    "openai/glm-5.3",
    # Later generations use the same profile.
    "glm-5.4",
    "z-ai/glm-5.30",
    "glm-6",
    "zhipuai/glm-6.1-flash",
]

NON_PROFILE_MODELS = [
    None,
    "",
    "glm-5.1",
    "z-ai/glm-5.1",
    "zhipuai/glm-5.1",
    "glm-4.6",
    "glm-5",
    "xglm-5.2",
    "xglm-5.3",
    "chatglm3-6b",
    "claude-sonnet-5",
    "gpt-5.6-luna",
    "gpt-6-astra",
    "moonshot/kimi-k3",
    "deepseek/deepseek-v4-flash",
]

_OBJECTIVE_PROCEED = "If all required parameters can be reasonably inferred, proceed with the tool use."


@pytest.fixture
def deterministic_prompt(monkeypatch):
    """Render prompts without user-local skills, agents or username."""
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: "SKILLS-CATALOG")
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: "AGENTS-CATALOG")

    def render(model_name, **kwargs):
        return code_gen_prompt.get_system_prompt(
            "/cwd", user_memory="MEMORY-BODY", model_name=model_name, **kwargs
        )

    return render


@pytest.mark.parametrize("model_name", GLM_PROFILE_MODELS)
def test_glm_5_2_family_and_later_select_the_profile(model_name):
    assert is_glm_profile_model(model_name) is True
    assert uses_glm_prompt_profile(model_name) is True
    # The profile changes prompt text only, not the tool surface or the
    # skills usage profile.
    assert uses_native_patch_file_tools(model_name) is False
    assert resolve_skill_usage_profile(model_name) is SkillUsageProfile.STRICT


@pytest.mark.parametrize("model_name", NON_PROFILE_MODELS)
def test_glm_5_1_and_other_families_do_not_select_the_profile(model_name):
    assert is_glm_profile_model(model_name) is False
    assert uses_glm_prompt_profile(model_name) is False


@pytest.mark.parametrize("model_name", [
    "glm-5.2", "baidu-glm-5.2-flash", "z-ai/glm-5.2",
    "glm-5.3", "baidu-glm-5.3-flash", "z-ai/glm-5.3", "glm-5.4",
])
def test_every_profile_variant_renders_the_same_prompt(deterministic_prompt, model_name):
    for options in ({}, {"interactive_mode": False}):
        assert deterministic_prompt(model_name, **options) == deterministic_prompt(
            "zhipuai/glm-5.3", **options
        )


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_profile_replaces_identity_and_keeps_shared_sections_in_order(deterministic_prompt, model_name):
    prompt = deterministic_prompt(model_name, preferred_language="zh-CN")

    assert prompt.startswith(GLM_INTRO)
    assert "You are Siada, a highly skilled software engineer" not in prompt
    # The generic OBJECTIVE and the legacy behaviour rules are replaced.
    assert "OBJECTIVE" not in prompt
    assert "## TO THE POINT" not in prompt
    assert "## Harness & System Reminders" not in prompt
    assert "fewer than 4 lines" not in prompt
    # Safety boundaries and terminal conventions are kept.
    assert "## Git Safety" in prompt
    assert "OWASP top 10" in prompt
    assert "Only use emojis if the user explicitly requests it." in prompt

    shared_capabilities = get_capabilities_section(model_name=model_name)
    assert shared_capabilities in prompt
    order = [
        prompt.index(GLM_INTRO),
        prompt.index(shared_capabilities),
        prompt.index("RULES"),
        prompt.index("SYSTEM INFORMATION"),
        prompt.index("PREFERRED LANGUAGE"),
        prompt.index("SKILLS-CATALOG"),
        prompt.index("AGENTS-CATALOG"),
        prompt.index(MEMORY_SECTION_TITLE),
        prompt.index("MEMORY-BODY"),
    ]
    assert order == sorted(order)
    assert prompt.rstrip().endswith("====")


def test_glm_communication_and_execution_contract_is_visible_to_the_model(deterministic_prompt):
    prompt = deterministic_prompt("zhipuai/glm-5.3")

    assert "Before your first tool call" in prompt
    assert "comment density, naming, and idiom" in prompt
    assert "constraint the code itself cannot show" in prompt
    assert "abbreviations or arrow chains" in prompt
    assert "Put the requested outcome and supporting evidence in your final response" in prompt
    assert "If the user asks only a question, requests a plan, or explores options without asking for changes" in prompt
    assert "When implementation is authorized by the current mode" in prompt
    assert "use the failure output to revise your approach" in prompt
    assert "a summary does not mean the task is finished" in prompt


@pytest.mark.parametrize("interactive_mode", [True, False])
def test_glm_autonomy_and_non_interactive_constraints(deterministic_prompt, interactive_mode):
    prompt = deterministic_prompt("zhipuai/glm-5.3", interactive_mode=interactive_mode)
    assert prompt.count("## IMPLEMENTATION MODE") == 1
    assert prompt.count("## NON-INTERACTIVE MODE") == int(not interactive_mode)
    assert "## Git Safety" in prompt
    assert "For hard-to-reverse or outward-facing actions, confirm" in prompt
    assert "Proceed with authorized, reversible work without routine approval requests" in prompt
    assert "When you have enough information, act." not in GLM_INTRO


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_default_interaction_has_no_non_interactive_block(deterministic_prompt, model_name):
    prompt = deterministic_prompt(model_name)

    assert "PLAN-FIRST MODE" not in prompt
    assert "NON-INTERACTIVE MODE" not in prompt
    assert "wait for the user's approval" not in prompt
    assert _OBJECTIVE_PROCEED not in prompt


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_non_interactive_mode_block(deterministic_prompt, model_name):
    prompt = deterministic_prompt(model_name, interactive_mode=False)

    assert prompt.count("## NON-INTERACTIVE MODE") == 1
    assert "PLAN-FIRST MODE" not in prompt
    # The legacy one-line constraint is replaced, not duplicated.
    assert "Prohibit operations requiring user interaction" not in prompt


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3", "glm-6"])
@pytest.mark.parametrize(
    "options", [{}, {"interactive_mode": False}]
)
def test_completion_discipline_lives_once_in_glm_rules(deterministic_prompt, model_name, options):
    completion_rule = (
        "- Check the actual requested outcome with the relevant tests or artifacts. "
        "Report failures and skipped checks plainly. Finish authorized work until "
        "verified or until a concrete external blocker remains."
    )
    prompt = deterministic_prompt(model_name, **options)
    rules = get_rules_section(
        "/cwd", "Linux", "/home", model_name=model_name, **options
    )
    assert "# Completion" not in GLM_INTRO.splitlines()
    assert "## Completion Discipline" not in GLM_INTRO
    assert prompt.splitlines().count("## Completion Discipline") == 1
    assert rules.splitlines().count("## Completion Discipline") == 1
    assert prompt.count(completion_rule) == 1
    assert rules.count(completion_rule) == 1
    assert prompt.index("# RULES") < prompt.index("## Completion Discipline")
    assert rules.index("## Terminal Output") < rules.index("## Completion Discipline") < rules.index("# SYSTEM INFORMATION")


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_subagent_switch_still_drops_the_run_subtask_capability(deterministic_prompt, model_name):
    prompt = deterministic_prompt(model_name, subagent_enabled=False)

    assert "run_subtask" not in prompt
    assert "AGENTS-CATALOG" not in prompt


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_prompt_never_ships_template_placeholders(deterministic_prompt, model_name):
    for options in ({}, {"interactive_mode": False}):
        prompt = deterministic_prompt(model_name, **options)
        assert "${" not in prompt
        assert "[Include ONLY" not in prompt


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.2", "zhipuai/glm-5.3"])
def test_obsolete_prompt_switch_does_not_disable_glm_profile(deterministic_prompt, monkeypatch, model_name):
    baseline = deterministic_prompt(model_name)
    monkeypatch.setenv("SIADA_GLM_PROMPT_PROFILE", "off")

    assert uses_glm_prompt_profile(model_name) is True
    assert deterministic_prompt(model_name) == baseline
    assert baseline.startswith(GLM_INTRO)
    assert baseline != deterministic_prompt("zhipuai/glm-5.1")


@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.1", "claude-sonnet-4", "kimi-k2.6"])
def test_default_branch_prompt_is_unchanged_for_other_models(deterministic_prompt, model_name):
    prompt = deterministic_prompt(model_name)

    assert prompt.startswith(code_gen_prompt.INTRO)
    assert GLM_INTRO not in prompt
    assert "OBJECTIVE" in prompt
    assert "## TO THE POINT" in prompt


def test_glm_prompt_text_is_defined_by_module_level_literals():
    root = Path(__file__).resolve().parents[3]
    expected = {
        root / "siada/agent_hub/coder/prompt/models/glm/instructions.py": {"GLM_INTRO"},
        root / "siada/agent_hub/coder/prompt/models/glm/rules.py": {
            "_GLM_IMPLEMENTATION_MODE_SECTION",
            "_GLM_NON_INTERACTIVE_MODE_SECTION",
            "_GLM_TERMINAL_OUTPUT_SECTION",
            "_GLM_COMPLETION_DISCIPLINE_SECTION",
        },
    }
    for module_path, names in expected.items():
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        assignments = {
            target.id: statement.value
            for statement in tree.body
            if isinstance(statement, ast.Assign)
            for target in statement.targets
            if isinstance(target, ast.Name)
        }
        for name in names:
            assert isinstance(assignments[name], ast.Constant), name
