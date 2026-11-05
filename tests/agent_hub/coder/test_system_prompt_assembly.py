from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

import pytest

from siada.agent_hub.coder.prompt.assembly import builder, codex, markdown_template, system
from siada.agent_hub.coder.prompt.assembly.context import SystemPromptContext
from siada.agent_hub.coder.prompt.assembly.template import render_optional_section, render_prompt_template
from siada.agent_hub.coder.prompt.selection.profiles import PromptFamily, resolve_prompt_profile


MODEL_NAMES = (
    None, "gpt-5.4", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-6.1-sol",
    "gpt-6.1-terra", "glm-5.3", "kimi-k3", "deepseek-v4-flash", "gpt-7-nova",
)


@pytest.fixture
def context():
    return SystemPromptContext(
        cwd="/synthetic/workspace-${cwd}", os_name="Windows", home_dir="/synthetic/home",
        capabilities="# CAPABILITIES\n\n- Synthetic capability.", interactive_mode=False,
        username="synthetic-user", preferred_language="zh-CN", subagent_enabled=False,
        skills_section="## Skills\n\n- ${cwd}\n### How to use skills\nUsage guidance.",
        agents_section="# AGENT TYPES\n\n- reviewer", user_memory="Synthetic ${os} memory.",
        available_tool_names=frozenset({"web_search", "web_fetch"}),
    )


def test_template_substitutes_once_and_preserves_literal_bytes():
    assert render_prompt_template(
        "\n  ${content}\n\n$$ ${empty}\n", {"content": "${missing} $$ 中文 {{literal}}", "empty": ""},
    ) == "\n  ${missing} $$ 中文 {{literal}}\n\n$ \n"


def test_template_rejects_missing_values():
    with pytest.raises(KeyError, match="missing"):
        render_prompt_template("${missing}", {})


@pytest.mark.parametrize("template", ["${}", "${unterminated", "$!"])
def test_template_rejects_invalid_placeholders(template):
    with pytest.raises(ValueError, match="Invalid placeholder"):
        render_prompt_template(template, {})


@pytest.mark.parametrize("content", [None, "", " \n\t "])
@pytest.mark.parametrize("strip", [True, False])
def test_optional_section_omits_blank_values_and_separators(content, strip):
    assert render_optional_section(content, prefix="before", suffix="after", strip=strip) == ""


@pytest.mark.parametrize("strip, expected", [
    (True, "\n\n${literal} 中文\n"), (False, "\n\n  ${literal} 中文\n \n"),
])
def test_optional_section_owns_whitespace_policy(strip, expected):
    assert render_optional_section("  ${literal} 中文\n ", prefix="\n\n", suffix="\n", strip=strip) == expected


def test_context_is_immutable(context):
    with pytest.raises(FrozenInstanceError):
        context.cwd = "/different/workspace"


def test_registry_covers_every_prompt_family():
    assert set(system._RENDERERS) == set(PromptFamily)


@pytest.mark.parametrize("model_name", MODEL_NAMES)
def test_dispatch_passes_the_selected_profile_and_context(monkeypatch, context, model_name):
    profile = resolve_prompt_profile(model_name)
    renderer = Mock(return_value="Synthetic prompt\n")
    monkeypatch.setitem(system._RENDERERS, profile.family, renderer)
    assert system.render_coding_system_prompt(profile, context) == "Synthetic prompt\n"
    renderer.assert_called_once_with(profile, context)


@pytest.mark.parametrize("model_name, separator", [
    (None, None), ("claude-sonnet-5", None), ("gpt-5.4", None),
    ("gpt-6-astra", "\n"), ("gpt-6-sol", "\n"), ("gpt-6-luna", "\n"),
    ("gpt-6.1-sol", "\n"), ("gpt-6.1-terra", "\n"), ("astra", "\n"),
    ("gpt-7-nova", "\n\n"), ("vendor/gpt-8-nova", "\n\n"),
    ("glm-5.3", None), ("gpt-7-glm-5.3", None),
    ("vendor-gpt-7-glm-6.1", None), ("vendor/gpt-8-glm-5.3", None),
    ("kimi-k3", None), ("deepseek-v4-flash", None),
])
@pytest.mark.parametrize("subagent_enabled", [True, False])
def test_delegation_suffix_preserves_rendering_path_scope(
    monkeypatch, context, model_name, separator, subagent_enabled,
):
    profile = resolve_prompt_profile(model_name)
    context = replace(context, subagent_enabled=subagent_enabled)
    expected = "Synthetic prompt\n"
    renderer = Mock(return_value=expected)
    monkeypatch.setitem(system._RENDERERS, profile.family, renderer)
    if subagent_enabled and separator is not None:
        expected += f"{separator}# Delegation\n\n{system.EXPLICIT_REQUEST_ONLY}\n"

    assert system.render_coding_system_prompt(profile, context) == expected
    renderer.assert_called_once_with(profile, context)


@pytest.mark.parametrize("model_name", MODEL_NAMES)
def test_every_family_uses_the_same_single_pass_renderer(monkeypatch, context, model_name):
    rendered_templates = []

    def record_render(template, values):
        rendered_templates.append(template)
        return render_prompt_template(template, values)

    for module in (builder, codex, markdown_template):
        monkeypatch.setattr(module, "render_prompt_template", record_render)
    prompt = system.render_coding_system_prompt(resolve_prompt_profile(model_name), context)
    assert len(rendered_templates) == 1
    assert "Synthetic ${os} memory." in prompt
    assert "/synthetic/workspace-${cwd}" in prompt


@pytest.mark.parametrize("model_name", MODEL_NAMES)
def test_runtime_values_do_not_leak_between_renders(context, model_name):
    profile = resolve_prompt_profile(model_name)
    expected = system.render_coding_system_prompt(profile, context)
    other_context = replace(
        context, cwd="/second/workspace", username=None, preferred_language=None,
        skills_section=None, agents_section=None, user_memory=None, interactive_mode=True,
        available_tool_names=None,
    )
    other_prompt = system.render_coding_system_prompt(profile, other_context)
    assert "Synthetic ${os} memory." not in other_prompt
    assert "/synthetic/workspace-${cwd}" not in other_prompt
    assert system.render_coding_system_prompt(profile, context) == expected


@pytest.mark.parametrize("model_name", [
    "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-6.1-sol", "gpt-6.1-terra",
])
def test_codex_preserves_the_empty_catalog_separator(context, model_name):
    profile = resolve_prompt_profile(model_name)
    plain = replace(context, skills_section=None, agents_section=None, user_memory=None)
    usage_only = replace(plain, skills_section="\n### How to use skills\nUsage only.")
    prompt = system.render_coding_system_prompt(profile, plain)
    assert system.render_coding_system_prompt(profile, usage_only) == prompt + "\n\n"


@pytest.mark.parametrize("extra_sections", ["", " \n "])
def test_legacy_extra_sections_keep_their_separator_even_when_empty(extra_sections):
    profile = replace(resolve_prompt_profile(None), extra_sections=lambda: extra_sections)
    assert builder.render_system_prompt(
        intro="intro", capabilities="capabilities", rules="rules", objective="",
        preferred_language=None, profile=profile,
    ) == f"intro\n\ncapabilities\n\nrules\n\n\n====\n\n{extra_sections}\n\n"
