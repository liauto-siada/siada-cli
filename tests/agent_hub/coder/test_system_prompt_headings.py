"""Heading format of the assembled coding and issue-review system prompts."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from siada.agent_hub.coder.prompt import code_gen_prompt, issue_review_prompt
from siada.services.agents.renderer import render_agents_section
from siada.services.memory.combined_memory import build_combined_memory
from siada.services.memory.memory_store import MemoryStore
from siada.services.skills import SkillMetadata, SkillScope, render_skills_section


class _FactProvider:
    def is_ready(self) -> bool:
        return True

    def fact_count(self) -> int:
        return 2


@pytest.mark.parametrize("model_name", ["claude-sonnet-5", "gpt-5.4", "gpt-6-astra", "glm-5.3", "kimi-k3"])
def test_coding_prompt_generated_sections_have_markdown_headings(
    monkeypatch, tmp_path, model_name
):
    (tmp_path / "MEMORY.md").write_text("Synthetic note", encoding="utf-8")
    (tmp_path / "USER.md").write_text("Synthetic preference", encoding="utf-8")
    memory_store = MemoryStore(memory_dir=tmp_path)
    memory_store.load_from_disk()
    memory = build_combined_memory(None, memory_store, _FactProvider())

    skill = SkillMetadata("sample", "Sample skill", Path("/skills/sample/SKILL.md"), SkillScope.REPO)
    skills = render_skills_section([skill])
    agents = render_agents_section([SimpleNamespace(name="reviewer", description="Reviews code")])
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: None)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: skills)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: agents)

    prompt = code_gen_prompt.get_system_prompt(
        str(tmp_path), model_name=model_name, user_memory=memory,
        preferred_language="zh-CN",
    )
    lines = prompt.splitlines()
    headings = [
        "# CAPABILITIES", "# PREFERRED LANGUAGE", "# AGENT TYPES", "# Combined Memory",
        "## Memory Layers — Common Rules", "## Inline Memory",
        "### MEMORY (your personal notes)", "### USER PROFILE (who the user is)",
        "## Session Search", "## Structured Fact Memory",
    ]
    if model_name == "kimi-k3":
        headings.extend(["# Runtime instructions", "# Environment", "# Project information", "# Skills"])
    elif model_name == "glm-5.3":
        headings.extend([
            "# Harness", "# Communicating with the user", "# Runtime instructions",
            "# Environment", "# Context management", "# Skills",
        ])
    elif model_name == "gpt-6-astra":
        headings.extend(["# SYSTEM INFORMATION", "## Skills"])
        headings.extend(["# Runtime instructions", "## Verification", "# Delegation"])
    else:
        headings.extend(["# SYSTEM INFORMATION", "## Skills"])
        headings.append("# OBJECTIVE")
    if model_name not in ("gpt-6-astra", "kimi-k3", "glm-5.3"):
        headings.extend(["# RULES", "## Completion Discipline"])
    if model_name == "gpt-6-astra":
        assert lines.index("# Combined Memory") < lines.index("# Delegation")
    else:
        assert prompt.rstrip().endswith("====")

    for heading in headings:
        assert lines.count(heading) == 1, heading
        assert lines.count(heading.lstrip("# ")) == 0, heading

    assert ("# OBJECTIVE" in lines) == (model_name not in ("glm-5.3", "gpt-6-astra", "kimi-k3"))
    assert "# Workspace" not in lines
    runtime_heading = "# Runtime instructions" if model_name in ("gpt-6-astra", "kimi-k3", "glm-5.3") else "# RULES"
    assert lines.index("# CAPABILITIES") < lines.index(runtime_heading) < lines.index("# Combined Memory")


def test_issue_review_prompt_shared_sections_have_markdown_headings():
    lines = issue_review_prompt.get_system_prompt("/review").splitlines()
    for heading in ("# CAPABILITIES", "# RULES", "# SYSTEM INFORMATION", "# OBJECTIVE"):
        assert lines.count(heading) == 1
        assert heading.lstrip("# ") not in lines


@pytest.mark.parametrize("model_name", ["claude-sonnet-5", "gpt-5.4"])
def test_extra_capabilities_stay_inside_titled_section(monkeypatch, model_name):
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: None)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: None)
    prompt = code_gen_prompt.get_system_prompt(
        "/cwd", model_name=model_name, extra_capabilities=["- Extra capability."],
    )
    assert "# CAPABILITIES" in prompt
    assert "- Extra capability.\n===" in prompt
    assert prompt.index("# CAPABILITIES") < prompt.index("- Extra capability.") < prompt.index("# RULES")
