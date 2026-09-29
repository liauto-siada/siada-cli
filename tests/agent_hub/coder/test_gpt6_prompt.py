"""Regression coverage for GPT-6 prompt selection and rendering."""

import ast
from pathlib import Path

from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.base.astra_instructions import get_astra_intro
from siada.agent_hub.coder.prompt.base.gpt6_instructions import get_gpt6_intro
from siada.agent_hub.coder.prompt.base.gpt5_instructions import (
    is_gpt5_model,
    is_gpt5_or_newer_model,
    uses_native_patch_file_tools,
)
from siada.agent_hub.coder.prompt.base.rules import get_rules_section
from siada.agent_hub.coder.prompt.base.skill_usage_profiles import (
    is_astra_model,
    is_gpt6_model,
    resolve_skill_usage_profile,
)
from siada.models.model_base_config import MODEL_SETTING
from siada.services.skills import SkillMetadata, SkillScope, SkillUsageProfile, render_skills_section


def _render_gpt6_prompt(monkeypatch, **kwargs) -> str:
    """Render a deterministic GPT-6 prompt without user-local skill discovery."""
    skill = SkillMetadata("test-skill", "Test instructions", Path("/skills/test/SKILL.md"), SkillScope.REPO)

    def render_fixed_skills(*_args, **skill_kwargs):
        return render_skills_section([skill], usage_profile=skill_kwargs["usage_profile"])

    monkeypatch.setattr(code_gen_prompt, "get_skills_section", render_fixed_skills)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    return code_gen_prompt.get_system_prompt("/cwd", model_name="gpt-6-astra", **kwargs)


def test_gpt6_variants_share_the_same_prompt_in_each_mode(monkeypatch):
    for options in ({}, {"pre_plan": True}, {"interactive_mode": False}):
        expected = _render_gpt6_prompt(monkeypatch, **options)
        for model_name in ("gpt-6-sol", "gpt-6-luna", "astra"):
            assert code_gen_prompt.get_system_prompt("/cwd", model_name=model_name, **options) == expected


def test_gpt6_model_detection_uses_major_version_with_astra_alias_support():
    for model_name in ("astra", "vendor-astra", "gpt-6-astra", "vendor-gpt-6-astra"):
        assert is_astra_model(model_name) is True

    for model_name in (None, "", "astral-projection", "astrapi", "gpt-5-astra", "gpt-7-astra"):
        assert is_astra_model(model_name) is False

    for model_name in ("astra", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-6-codex", "vendor-gpt-6.1-nova"):
        assert is_gpt6_model(model_name) is True
        assert resolve_skill_usage_profile(model_name) is SkillUsageProfile.GPT6

    for model_name in (
        None,
        "",
        "astral-projection",
        "gpt-5.6-luna",
        "gpt-5-astra",
        "gpt-7-nova",
        "gpt-7-astra",
    ):
        assert is_gpt6_model(model_name) is False
        assert resolve_skill_usage_profile(model_name) is SkillUsageProfile.STRICT

    assert is_gpt5_model("gpt-6-astra") is False
    for model_name in ("gpt-5.6-luna", "gpt-6-astra", "vendor-gpt-7-nova"):
        assert is_gpt5_or_newer_model(model_name) is True
    assert is_gpt5_or_newer_model("gpt-4.1") is False

    for model_name in ("astra", "gpt-5.6-luna", "gpt-6-astra", "vendor-gpt-7-nova"):
        assert uses_native_patch_file_tools(model_name) is True
    for model_name in ("gpt-4.1", "claude-sonnet-5", "bailian-glm-5.3"):
        assert uses_native_patch_file_tools(model_name) is False


def test_gpt6_intro_preserves_astra_compatibility():
    intro = get_astra_intro()
    without_personality = get_astra_intro(personality="default")
    gpt6_intro = get_gpt6_intro()

    assert "# Personality" in intro
    assert "## Writing style" in intro
    assert "## Technical communication" in intro
    assert "### Writing PR descriptions" not in intro
    assert "# Personality" not in without_personality
    assert "You are Siada, an agent based on GPT-6." in without_personality
    assert gpt6_intro == intro


def test_gpt6_rules_include_permissions_without_duplicating_personality():
    rules = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-6-astra")

    assert "## When to Ask the User" in rules
    assert "## Tool Discipline" in rules
    assert "## Steering and Interruption" in rules
    assert "## Progress Updates" in rules
    assert "## Visualizations" in rules
    assert "# Personality" not in rules
    assert "## Writing style" not in rules


def test_gpt6_pre_plan_uses_one_plan_gate(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch, pre_plan=True)

    assert "Plan-first mode is enabled" in prompt
    assert "Complete the work that is already authorized" not in prompt
    assert "go ahead and actually implement" not in prompt
    assert prompt.count("modifies or creates files") == 1


def test_gpt6_non_interactive_permission_variant(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch, interactive_mode=False)

    assert "This session is non-interactive, so you cannot ask the user anything." in prompt
    assert "Use your judgement about when you genuinely need" not in prompt


def test_gpt6_system_prompt_uses_gpt6_skills_and_has_no_codex_only_mechanisms(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch)

    assert "# Personality" in prompt
    assert "develop it with the explanation and detail the reader needs" in prompt
    assert "reasonable judgement" in prompt
    assert "### How to use skills" in prompt
    assert "explicitly require approval" in prompt
    assert "you must use that skill" not in prompt
    assert "long-horizon" not in prompt
    assert "only hidden" not in prompt
    assert "fewer than 4 lines" not in prompt
    assert "## Editing Constraints" not in prompt
    assert "## Frontend Tasks" not in prompt
    assert "## Formatting Rules" not in prompt
    assert "Aim for interfaces that feel intentional, bold, and a bit surprising." not in prompt
    for forbidden in (
        "commentary channel",
        "final channel",
        "request_user_input_async",
        "send_user_message_async",
        "codex_apps",
        "tool_search",
        "auto-review",
        "mcp__server__tool",
        "plugin_name:",
        "skill://",
        "skills.list",
    ):
        assert forbidden not in prompt


def test_gpt6_prompt_lists_read_file_and_native_apply_patch(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch)

    assert "You can use `read_file` to view files and directories." in prompt
    assert "Use `view_range` to efficiently read specific portions" in prompt
    assert "You can use `apply_patch` to create, update, delete, and move text files" in prompt
    assert "### `read_file`" not in prompt
    assert "### `apply_patch`" not in prompt
    assert "The diff language follows Codex's file-oriented patch rules" not in prompt
    assert "str_replace" not in prompt
    assert "edit_file" not in prompt


def test_every_gpt5_or_newer_prompt_uses_the_native_file_tool_contract(monkeypatch):
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    for model_name in ("gpt-5.6-luna", "gpt-6-nova", "vendor-gpt-7-nova"):
        prompt = code_gen_prompt.get_system_prompt("/cwd", model_name=model_name)

        assert "You can use `read_file` to view files and directories." in prompt
        assert "You can use `apply_patch` to create, update, delete, and move text files" in prompt
        assert "edit_file" not in prompt

    gpt6_prompt = code_gen_prompt.get_system_prompt("/cwd", model_name="gpt-6-nova")
    assert "reasonable judgement" in gpt6_prompt
    assert "## When to Ask the User" in gpt6_prompt
    assert "you must use that skill" not in gpt6_prompt

    # GPT-5 retains its own extra editing section; later GPT generations use
    # the shared capabilities contract without inheriting GPT-5 persona text.
    assert "Use `read_file` to inspect source before changing it" in code_gen_prompt.get_system_prompt(
        "/cwd", model_name="gpt-5.6-luna"
    )


def test_non_gpt_prompt_includes_shared_skill_root_alias_guidance(monkeypatch):
    """The alias-to-root catalog fact applies to every model family."""
    root = Path("/skills")
    skill = SkillMetadata("test-skill", "Test instructions", root / "test" / "SKILL.md", SkillScope.REPO)

    def render_aliased_skills(*_args, **skill_kwargs):
        return render_skills_section(
            [skill],
            skill_roots={SkillScope.REPO: [root]},
            usage_profile=skill_kwargs["usage_profile"],
        )

    monkeypatch.setattr(code_gen_prompt, "get_skills_section", render_aliased_skills)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)

    prompt = code_gen_prompt.get_system_prompt("/cwd", model_name="claude-sonnet-5")

    assert "### Skill roots" in prompt
    assert "- `r0` = `/skills`" in prompt
    assert "maps aliases such as `r0` to their absolute filesystem roots" in prompt
    assert "Expand the matching alias before accessing the skill." in prompt
    assert "you must use that skill for that turn" in prompt


def _is_static_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and _is_static_literal(node.left)
        and _is_static_literal(node.right)
    )


def _assert_gpt6_literals(module_path: Path, expected_names: set[str]) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    assignments: dict[str, ast.AST] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = statement.value

    assert expected_names <= assignments.keys()
    for name in expected_names:
        assert _is_static_literal(assignments[name]), name


def test_gpt6_prompt_text_is_defined_by_module_level_literals():
    root = Path(__file__).resolve().parents[3]
    _assert_gpt6_literals(
        root / "siada/agent_hub/coder/prompt/base/gpt6_instructions.py",
        {"_GPT6_INTRO_HEADER", "PERSONALITY_GPT6"},
    )
    _assert_gpt6_literals(
        root / "siada/agent_hub/coder/prompt/base/rules.py",
        {
            "_GPT6_CONCISE_COMMUNICATION_SECTION",
            "_GPT6_AUTONOMY_IMPLEMENT",
            "_GPT6_AUTONOMY_PRE_PLAN",
            "_GPT6_PERMISSION_ASK",
            "_GPT6_PERMISSION_PREPLAN",
            "_GPT6_PERMISSION_NONINTERACTIVE",
            "_GPT6_TOOL_DISCIPLINE_SECTION",
            "_GPT6_STEERING_SECTION",
            "_GPT6_PROGRESS_UPDATE_SECTION",
            "_GPT6_VISUALIZATION_SECTION",
        },
    )


def test_gpt_6_astra_has_local_model_fallback_configuration():
    config = next(config for config in MODEL_SETTING if config.model_name == "gpt-6-astra")

    # Capacity may be tuned independently of the prompt implementation; this
    # test guards that the local fallback entry remains valid and usable.
    assert config.context_window > 0
    assert config.max_tokens == 32768 * 2
    assert config.supports_images is True
    assert config.parallel_tool_calls is True
    assert config.supports_extra_params == ["reasoning_effort"]
    assert config.default_reasoning_effort == "low"
