import os
import platform
from typing import List, Optional
from .assembly.builder import render_system_prompt
from .assembly.codex import render_codex_system_prompt
from .assembly.glm import render_glm_system_prompt
from .assembly.kimi import render_kimi_system_prompt
from .models.default.instructions import INTRO, _build_objective
from .models.gpt5.instructions import get_gpt5_intro
from .models.gpt6.instructions import get_gpt6_intro
from .selection.model_features import uses_gpt6_scannable_writing_style
from .sections.capabilities import get_capabilities_for_profile
from .sections.objectives import GPT5_OBJECTIVE
from .sections.rules.dispatch import get_rules_for_profile
from .selection.profiles import PromptFamily, PromptProfile, resolve_prompt_profile
from siada.services.skills import get_skills_section
from siada.services.agents import get_agents_section
from siada.foundation.tools.user_info import get_username
from siada.models.model_base_config import get_model_config


def _get_intro_and_objective(profile: PromptProfile) -> tuple[str, str]:
    """Keep family-specific prose selection outside the prompt assembly flow."""
    if profile.family is PromptFamily.GPT6:
        # GPT-6 splits its writing style per model (Sol/Luna vs Astra family).
        personality = "scannable" if uses_gpt6_scannable_writing_style(profile.model_name) else "gpt6"
        return get_gpt6_intro(personality=personality), GPT5_OBJECTIVE
    if profile.family is PromptFamily.GPT5:
        return get_gpt5_intro(personality="pragmatic"), GPT5_OBJECTIVE
    return INTRO, _build_objective()


def _skills_context_window(model_name: Optional[str]) -> Optional[int]:
    """Resolve the model's context window for sizing the skills list budget.

    Keeps the skills section within its 2% share of the window. Returns None
    when the model is unknown, in which case the renderer's flat fallback
    budget applies.
    """
    if not model_name:
        return None
    try:
        config = get_model_config(model_name)
    except ValueError:
        return None
    return config.context_window if config else None


def get_system_prompt(cwd: str = "/default/path", interactive_mode: bool = True, user_memory: str = None,
                      preferred_language: str = None, agent_name: str = None,
                      extra_capabilities: List[str] = None,
                      model_name: Optional[str] = None,
                      activated_skill_names: Optional[set[str]] = None,
                      subagent_enabled: bool = True) -> str:
    """Generate the system prompt for the code generation agent.

    Args:
        cwd: Current working directory path.
        interactive_mode: Whether the agent is running in interactive mode.
        user_memory: User memory content (loaded from the `siada.md` file).
        preferred_language: Preferred language code ("en" or "zh-CN").
        agent_name: Name of the agent.
        extra_capabilities: List of additional capabilities to append to the capabilities section.
        model_name: Model name, used to activate family-specific optimizations.
        subagent_enabled: Whether the sub-agent (`run_subtask`) capability is
            exposed for this run (conf.yaml `sub_agent.enabled`); when False
            its capability bullet is dropped along with the tool itself.

    Returns:
        The formatted system prompt string.
    """
    # Get OS and home directory information
    os_name = platform.system()
    home_dir = os.path.expanduser("~")

    # Resolve the prompt family once; file-tool selection remains independent.
    profile = resolve_prompt_profile(model_name)
    username = get_username()

    # Build capabilities section with optional extra capabilities
    capabilities = get_capabilities_for_profile(
        profile, subagent_enabled=subagent_enabled
    )

    if extra_capabilities:
        body, separator, closing = capabilities.rpartition("\n===")
        capabilities = f"{body.rstrip()}\n" + "\n".join(extra_capabilities) + separator + closing

    skills_section = get_skills_section(
        cwd,
        context_window=_skills_context_window(model_name),
        activated_skill_names=activated_skill_names,
        usage_profile=profile.skill_usage_profile,
    )
    # Do not advertise agents when run_subtask is absent from the tool surface.
    agents_section = get_agents_section(cwd) if subagent_enabled else None

    if profile.family is PromptFamily.GPT6:
        return render_codex_system_prompt(
            model_name=profile.model_name, cwd=cwd, os_name=os_name, home_dir=home_dir,
            capabilities=capabilities, interactive_mode=interactive_mode,
            username=username,
            preferred_language=preferred_language, skills_section=skills_section,
            agents_section=agents_section, user_memory=user_memory,
        )

    if profile.family is PromptFamily.KIMI_K3:
        return render_kimi_system_prompt(
            cwd=cwd, os_name=os_name, home_dir=home_dir, capabilities=capabilities,
            interactive_mode=interactive_mode, username=username,
            preferred_language=preferred_language, skills_section=skills_section,
            agents_section=agents_section, user_memory=user_memory,
        )

    if profile.family is PromptFamily.GLM:
        return render_glm_system_prompt(
            cwd=cwd, os_name=os_name, home_dir=home_dir, capabilities=capabilities,
            interactive_mode=interactive_mode, username=username,
            preferred_language=preferred_language, skills_section=skills_section,
            agents_section=agents_section, user_memory=user_memory,
        )

    intro, objective = _get_intro_and_objective(profile)
    if username:
        intro += f"\n\nThe current user is {username}."
    rules = get_rules_for_profile(
        cwd, os_name, home_dir, interactive_mode, profile=profile
    )
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
