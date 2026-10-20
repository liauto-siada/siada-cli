"""Regression coverage for GPT-6 prompt selection and rendering."""

import ast
from pathlib import Path

from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.models.gpt6.astra import get_astra_intro
from siada.agent_hub.coder.prompt.models.gpt6.instructions import get_gpt6_intro
from siada.agent_hub.coder.prompt.models.gpt6.templates import get_gpt6_template, resolve_gpt6_template_name
import pytest
from siada.agent_hub.coder.prompt.selection.model_features import (
    is_gpt5_model,
    is_gpt5_or_newer_model,
    is_gpt6_or_newer_model,
    uses_native_patch_file_tools,
)
from siada.agent_hub.coder.prompt.sections.rules.dispatch import get_rules_section
from siada.agent_hub.coder.prompt.selection.skill_usage import (
    is_astra_model,
    is_gpt6_model,
    resolve_skill_usage_profile,
)
from siada.models.model_base_config import MODEL_SETTING
from siada.services.skills import SkillMetadata, SkillScope, SkillUsageProfile, render_skills_section


def _render_gpt6_prompt(monkeypatch, model_name: str = "gpt-6-astra", **kwargs) -> str:
    """Render a deterministic GPT-6 prompt without user-local skill discovery."""
    skill = SkillMetadata("test-skill", "Test instructions", Path("/skills/test/SKILL.md"), SkillScope.REPO)

    def render_fixed_skills(*_args, **skill_kwargs):
        return render_skills_section([skill], usage_profile=skill_kwargs["usage_profile"])

    monkeypatch.setattr(code_gen_prompt, "get_skills_section", render_fixed_skills)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: None)
    return code_gen_prompt.get_system_prompt("/cwd", model_name=model_name, **kwargs)


def test_gpt6_preserves_four_distinct_upstream_templates_in_each_mode(monkeypatch):
    """Writing-style siblings retain their upstream policy differences."""
    for options in ({}, {"interactive_mode": False}):
        scannable = _render_gpt6_prompt(monkeypatch, model_name="gpt-6-sol", **options)
        for model_name in ("gpt-6-sol", "vendor-gpt-6-sol"):
            assert code_gen_prompt.get_system_prompt("/cwd", model_name=model_name, **options) == scannable

        prose = _render_gpt6_prompt(monkeypatch, model_name="gpt-6-astra", **options)
        for model_name in ("gpt-6-astra", "astra"):
            assert code_gen_prompt.get_system_prompt("/cwd", model_name=model_name, **options) == prose

        assert "write so the user understands your response on first read" in scannable
        assert "Write in connected prose" in prose
        assert scannable != prose
        luna = _render_gpt6_prompt(monkeypatch, model_name="gpt-6-luna", **options)
        sol61 = _render_gpt6_prompt(monkeypatch, model_name="gpt-6.1-sol", **options)
        assert len({prose, scannable, luna, sol61}) == 4
        assert "Avoid unnecessary apologies and self-blame." in sol61
        assert "Avoid unnecessary apologies and self-blame." not in prose
        assert "Do not add or run tests unless the user asks" in luna
        assert "Do not add or run tests unless the user asks" not in scannable


def test_gpt6_writing_style_follows_the_per_model_split(monkeypatch):
    for model_name in ("gpt-6-sol", "gpt-6-luna", "vendor-gpt-6-sol"):
        prompt = _render_gpt6_prompt(monkeypatch, model_name=model_name)
        assert "write so the user understands your response on first read" in prompt
        assert "minimize cognitive load" in prompt
        assert "Write in connected prose" not in prompt
        assert "avoid concluding summary statements" not in prompt

    for model_name in ("gpt-6-astra", "gpt-6.1-sol", "astra", "gpt-6-nova"):
        prompt = _render_gpt6_prompt(monkeypatch, model_name=model_name)
        assert "Write in connected prose" in prompt
        assert "write so the user understands your response on first read" not in prompt


def test_gpt6_action_requests_and_risk_scaled_verification_across_modes(monkeypatch):
    for options in ({}, {"interactive_mode": False}):
        prompt = _render_gpt6_prompt(monkeypatch, **options)
        assert '"can you..."' in prompt
        assert '"help me..."' in prompt
        assert "treat these as instructions to do the work and take action" in prompt
        assert "complete all the necessary work until the intended outcome is fulfilled" in prompt
        assert "Complete required checks before reporting success" in prompt
        assert "Incorporate corrections, clarifications, constraints" in prompt


def test_gpt6_final_answers_are_structured_and_not_token_compressed(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch)

    assert "## Final answer" in prompt
    assert "fully self-contained" in prompt
    assert "blank line before any list" in prompt
    assert "Minimize output tokens" not in prompt
    assert "use 1-2 short paragraphs" not in prompt
    assert "explain what changed, why, how it was tested" in prompt


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
    ):
        assert is_gpt6_model(model_name) is False
        assert is_gpt6_or_newer_model(model_name) is False
        assert resolve_skill_usage_profile(model_name) is SkillUsageProfile.STRICT

    for model_name in ("gpt-7-nova", "gpt-7-astra", "vendor-gpt-8.1-sol"):
        assert is_gpt6_model(model_name) is False
        assert is_gpt6_or_newer_model(model_name) is True
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
    scannable_intro = get_gpt6_intro(personality="scannable")

    assert "# Personality" in intro
    assert "## Writing style" in intro
    assert "## Technical communication" in intro
    assert "### Writing PR descriptions" not in intro
    assert "# Personality" not in without_personality
    assert "You are Siada, an agent based on GPT-6." in without_personality
    assert gpt6_intro == intro

    # The caller picks the writing-style variant by name; the intro itself
    # never depends on a separately threaded model name.
    assert "write so the user understands your response on first read" in scannable_intro
    assert "Write in connected prose" in intro
    assert "Write in connected prose" not in scannable_intro
    assert "write so the user understands your response on first read" not in intro


def test_gpt6_rules_include_permissions_without_duplicating_personality():
    rules = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-6-astra")

    assert "## When to Ask the User" in rules
    assert "## Tool Discipline" in rules
    assert "## Steering and Interruption" in rules
    assert "## Progress Updates" in rules
    assert "## Visualizations" in rules
    assert "# Personality" not in rules
    assert "## Writing style" not in rules


def test_gpt6_non_interactive_permission_variant(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch, interactive_mode=False)

    assert "This session is non-interactive, so you cannot ask the user anything." in prompt
    assert "Use your judgement about when you genuinely need" not in prompt


def test_gpt6_system_prompt_uses_gpt6_skills_and_has_no_codex_only_mechanisms(monkeypatch):
    prompt = _render_gpt6_prompt(monkeypatch)

    assert "# Personality" in prompt
    assert "develop it with the explanation and detail the reader needs" in prompt
    assert "reasonable judgement" in prompt
    assert prompt.splitlines().count("## How to use skills") == 1
    assert "### How to use skills" not in prompt
    assert "User authorization and preferences persist across turns" in prompt
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
        prompt = _render_gpt6_prompt(monkeypatch, model_name=model_name)

        assert "You can use `read_file` to view files and directories." in prompt
        assert "You can use `apply_patch` to create, update, delete, and move text files" in prompt
        assert "edit_file" not in prompt

    gpt6_prompt = code_gen_prompt.get_system_prompt("/cwd", model_name="gpt-6-nova")
    assert "reasonable judgement" in gpt6_prompt
    assert "# When to ask the user for permission" in gpt6_prompt
    assert "you must use that skill" not in gpt6_prompt

    # GPT-5 retains its own extra editing section; later GPT generations use
    # the shared capabilities contract without inheriting GPT-5 persona text.
    assert "Use `read_file` to inspect source before changing it" in code_gen_prompt.get_system_prompt(
        "/cwd", model_name="gpt-5.6-luna"
    )


@pytest.mark.parametrize("model_name, expected", [
    ("gpt-6-astra", "gpt-6-astra"), ("astra", "gpt-6-astra"),
    ("vendor-gpt-6.1-sol", "gpt-6.1-sol"), ("gpt-6-sol", "gpt-6-sol"),
    ("vendor-gpt-6-luna", "gpt-6-luna"), ("gpt-6-nova", "gpt-6-astra"),
])
def test_gpt6_template_aliases(model_name, expected):
    assert resolve_gpt6_template_name(model_name) == expected


def test_gpt6_uses_literal_template_then_runtime_fragments(monkeypatch):
    monkeypatch.setattr(code_gen_prompt, "get_rules_for_profile", lambda *_a, **_k: pytest.fail("Legacy rules used"))
    monkeypatch.setattr(code_gen_prompt, "render_system_prompt", lambda **_k: pytest.fail("Legacy builder used"))
    prompt = _render_gpt6_prompt(monkeypatch, preferred_language="zh-CN", user_memory="Synthetic note")
    template = get_gpt6_template("gpt-6-astra")
    assert prompt.startswith(template + "\n\n===\n\n# CAPABILITIES")
    headings = ["# CAPABILITIES", "# Runtime instructions", "# SYSTEM INFORMATION", "# PREFERRED LANGUAGE", "## Skills", "# Combined Memory"]
    assert [prompt.splitlines().index(heading) for heading in headings] == sorted(prompt.splitlines().index(heading) for heading in headings)
    assert "# RULES" not in prompt and "# OBJECTIVE" not in prompt
    assert "### Writing PR descriptions" in prompt
    assert "## User input tools" not in prompt


@pytest.mark.parametrize("model_name", [
    "claude-sonnet-5", "gpt-5.4", "zhipuai/glm-5.3", "gpt-6-astra",
    "gpt-6-sol", "gpt-6-luna", "gpt-6.1-sol",
])
@pytest.mark.parametrize("interactive_mode", [True, False])
def test_prompts_do_not_advertise_question_tools(monkeypatch, model_name, interactive_mode):
    prompt = _render_gpt6_prompt(
        monkeypatch, model_name=model_name, interactive_mode=interactive_mode,
    )
    assert "## User input tools" not in prompt
    for name in ("request_user_input", "request_user_input_async", "ask_followup_question"):
        assert name not in prompt
    assert "send_message_to_user_async" not in prompt


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
        root / "siada/agent_hub/coder/prompt/models/gpt6/instructions.py",
        {"_GPT6_INTRO_HEADER", "PERSONALITY_GPT6", "PERSONALITY_GPT6_SCANNABLE"},
    )
    _assert_gpt6_literals(
        root / "siada/agent_hub/coder/prompt/models/gpt6/rules.py",
        {
            "_GPT6_CONCISE_COMMUNICATION_SECTION",
            "_GPT6_FINAL_ANSWER_SECTION",
            "_GPT6_AUTONOMY_IMPLEMENT",
            "_GPT6_PERMISSION_ASK",
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
