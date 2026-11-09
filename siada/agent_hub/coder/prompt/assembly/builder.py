from typing import Optional

from ..selection.profiles import PromptProfile, resolve_prompt_profile
from ..sections.language import _get_language_instruction
from ..sections.memory import MEMORY_SECTION_TITLE, wrap_user_memory
from .fragments import render_memory_section
from .template import render_optional_section, render_prompt_template


_SYSTEM_TEMPLATE = (
    "${intro}\n\n${capabilities}\n\n${rules}${objective}\n\n${language}\n"
    "${extra_sections}${skills_section}${agents_section}${memory_section}"
)


def build_system_prompt(

    intro: str,
    capabilities: str,
    rules: str,
    objective: str,
    user_memory: str = None,
    preferred_language: str = "en",
    agent_name: str = None,
    skills_section: Optional[str] = None,
    agents_section: Optional[str] = None,
    model_name: Optional[str] = None,
    *, profile: PromptProfile | None = None) -> str:
    """
    Common function for building system prompts.

    GPT-5 models append Siada-specific editing, frontend, and output-format
    sections automatically. GPT-6's distinct prompt content is selected by its
    intro, rules, and skills-profile branches instead.

    Args:
        intro: Agent-specific introduction section
        capabilities: Capabilities section
        rules: Rules section
        objective: Objective section
        user_memory: User memory content from siada.md file
        preferred_language: Preferred communication language ("en" or "zh-CN")
        agent_name: Agent name to determine default language (optional)
        skills_section: Pre-rendered skills section content (optional)
        agents_section: Pre-rendered user-defined agent catalog (optional)
        model_name: Model name, used to inject GPT-5-specific sections
        profile: Already-resolved profile for the main coding prompt path

    Returns:
        str: Complete system prompt
    """
    if profile is None:
        profile = resolve_prompt_profile(model_name)
    return render_system_prompt(
        intro=intro,
        capabilities=capabilities,
        rules=rules,
        objective=objective,
        user_memory=user_memory,
        preferred_language=preferred_language,
        agent_name=agent_name,
        skills_section=skills_section,
        agents_section=agents_section,
        profile=profile,
    )


def render_system_prompt(
    *,
    intro: str,
    capabilities: str,
    rules: str,
    objective: str,
    profile: PromptProfile,
    user_memory: Optional[str] = None,
    preferred_language: Optional[str] = "en",
    agent_name: Optional[str] = None,
    skills_section: Optional[str] = None,
    agents_section: Optional[str] = None,
) -> str:
    """Format already-selected prompt sections without resolving a model name."""
    return render_prompt_template(_SYSTEM_TEMPLATE, {
        "intro": intro,
        "capabilities": capabilities,
        "rules": rules,
        "objective": f"\n\n{objective}" if objective else "",
        "language": _get_language_instruction(preferred_language, agent_name),
        "extra_sections": (
            f"====\n\n{profile.extra_sections()}\n\n" if profile.extra_sections is not None else ""
        ),
        "skills_section": render_optional_section(
            skills_section, prefix="====\n\n", suffix="\n\n", strip=False,
        ),
        "agents_section": render_optional_section(
            agents_section, prefix="====\n\n", suffix="\n\n", strip=False,
        ),
        "memory_section": render_optional_section(render_memory_section(user_memory), prefix="\n"),
    })
