"""Unit tests for ``prompt_builder`` memory-section framing.

The contract verified here:

1. ``wrap_user_memory`` wraps the combined-memory snapshot in a titled
   ``====`` section so the model can tell where the snapshot begins and
   ends.
2. ``build_system_prompt`` ships that framed section at the tail of the
   prompt (instead of raw memory), and
   skips the section entirely when no memory is available.
3. Whitespace-only memory is treated as absent, mirroring the historical
   guard behaviour.
"""

import pytest

from siada.agent_hub.coder.prompt.assembly import builder as prompt_builder
from siada.agent_hub.coder.prompt.assembly.builder import (
    MEMORY_SECTION_TITLE,
    build_system_prompt,
    render_system_prompt,
    wrap_user_memory,
)
from siada.agent_hub.coder.prompt.selection.profiles import resolve_prompt_profile


def test_wrap_user_memory_produces_titled_section():
    wrapped = wrap_user_memory("some memory body")
    assert wrapped == f"====\n# {MEMORY_SECTION_TITLE}\n\nsome memory body\n===="


def test_wrap_user_memory_strips_surrounding_whitespace():
    wrapped = wrap_user_memory("\n  some memory body  \n")
    assert wrapped == f"====\n# {MEMORY_SECTION_TITLE}\n\nsome memory body\n===="


def test_build_system_prompt_frames_memory_with_outer_title():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory="====\n## Inline Memory\n\nbody\n====",
    )
    # The combined-memory snapshot must ship inside the outer titled
    # section at the tail of the prompt.
    assert f"====\n# {MEMORY_SECTION_TITLE}\n" in prompt
    assert prompt.rstrip().endswith("====")
    pos_title = prompt.find(MEMORY_SECTION_TITLE)
    pos_inner = prompt.find("Inline Memory")
    assert -1 < pos_title < pos_inner


def test_build_system_prompt_skips_memory_section_when_absent():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory=None,
    )
    assert MEMORY_SECTION_TITLE not in prompt


def test_build_system_prompt_skips_memory_section_when_blank():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        user_memory="   \n  ",
    )
    assert MEMORY_SECTION_TITLE not in prompt


def test_build_system_prompt_optional_headings_use_markdown():
    prompt = build_system_prompt(
        intro="intro",
        capabilities="# CAPABILITIES\n- tool",
        rules="# RULES\n- rule",
        objective="# OBJECTIVE\nobjective",
        preferred_language="zh-CN",
        skills_section="## Skills\n- skill",
        agents_section="# AGENT TYPES\n- agent",
        user_memory="## Inline Memory\nbody",
    )

    for heading in (
        "# CAPABILITIES", "# RULES", "# OBJECTIVE", "# PREFERRED LANGUAGE",
        "## Skills", "# AGENT TYPES", "# Combined Memory",
    ):
        assert heading in prompt.splitlines()


@pytest.mark.parametrize("model_name", [None, "gpt-5.4", "gpt-6-astra", "glm-5.3", "gpt-7-nova"])
def test_build_system_prompt_does_not_inject_patch_recovery_rules(model_name):
    prompt = build_system_prompt(
        intro="intro",
        capabilities="capabilities",
        rules="rules",
        objective="objective",
        model_name=model_name,
    )

    assert "## Patch Context and Recovery" not in prompt
    assert "Read the current target region before updating it" not in prompt
    assert "Do not retry the unchanged patch" not in prompt


@pytest.mark.parametrize("model_name", [None, "gpt-5.4", "gpt-6-astra", "glm-5.3", "gpt-7-nova"])
@pytest.mark.parametrize("objective, user_memory", [("# OBJECTIVE\nobjective", "## Inline Memory\nbody"), ("", None)])
def test_renderer_matches_legacy_entry_without_resolving_again(
    monkeypatch, model_name, objective, user_memory
):
    sections = {
        "intro": "intro",
        "capabilities": "# CAPABILITIES\n- tool",
        "rules": "# RULES\n- rule",
        "objective": objective,
        "user_memory": user_memory,
        "preferred_language": "zh-CN",
        "skills_section": "## Skills\n- skill",
        "agents_section": "# AGENT TYPES\n- agent",
    }
    expected = build_system_prompt(**sections, model_name=model_name)
    profile = resolve_prompt_profile(model_name)

    def unexpected_resolution(_model_name):
        raise AssertionError("The renderer must not resolve a model name")

    monkeypatch.setattr(prompt_builder, "resolve_prompt_profile", unexpected_resolution)
    assert render_system_prompt(**sections, profile=profile) == expected
    assert build_system_prompt(**sections, profile=profile) == expected
