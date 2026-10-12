from typing import Optional

from ..selection.profiles import PromptProfile, resolve_prompt_profile
from ..sections.language import _get_language_instruction
from ..sections.memory import MEMORY_SECTION_TITLE, wrap_user_memory


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
    # Build language instruction section
    language_instruction = _get_language_instruction(preferred_language, agent_name)

    # Assemble complete prompt. An empty objective (the GLM profile, whose
    # execution flow lives in its intro) is skipped instead of leaving a
    # blank gap; non-empty objectives render byte-identically to before.
    leading_sections = [intro, capabilities, rules]
    if objective:
        leading_sections.append(objective)
    base_prompt = "\n\n".join(leading_sections) + f"\n\n{language_instruction}\n"

    # Keep each optional block's historical separator and trailing newlines.
    if profile.extra_sections is not None:
        base_prompt += f"====\n\n{profile.extra_sections()}\n\n"

    # Add skills section if provided
    if skills_section and skills_section.strip():
        base_prompt += f"====\n\n{skills_section}\n\n"

    # Add the user-defined agent catalog (`.agents/agents/*.md`) so the model
    # knows which named agents `run_subtask` can launch. Absent by default.
    if agents_section and agents_section.strip():
        base_prompt += f"====\n\n{agents_section}\n\n"

    # Keep the memory snapshot as the last titled section.
    if user_memory and user_memory.strip():
        memory_suffix = f"\n{wrap_user_memory(user_memory)}"
        return f"{base_prompt}{memory_suffix}"

    return base_prompt
