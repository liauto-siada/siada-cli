import os
import platform
from typing import List, Optional
from .assembly.context import SystemPromptContext
from .assembly.system import render_coding_system_prompt
from .sections.capabilities import get_capabilities_for_profile
from .selection.profiles import resolve_prompt_profile
from siada.services.skills import get_skills_section
from siada.services.agents import get_agents_section
from siada.foundation.tools.user_info import get_username
from siada.models.model_base_config import get_model_config


def _skills_context_window(model_name: Optional[str]) -> Optional[int]:
    """Resolve the model's base context window for sizing the skills list budget.

    Uses the locally configured context_window to keep the skills section
    within its 2% share. Unknown models use the renderer's fallback budget.
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
                      subagent_enabled: bool = True,
                      available_tool_names: Optional[set[str]] = None) -> str:
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
        available_tool_names: Actual tool names exposed for this run. Optional
            DeepSeek web guidance is omitted when availability is unknown.

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

    context = SystemPromptContext(
        cwd=cwd, os_name=os_name, home_dir=home_dir, capabilities=capabilities,
        interactive_mode=interactive_mode, username=username,
        preferred_language=preferred_language, skills_section=skills_section,
        agents_section=agents_section, user_memory=user_memory, agent_name=agent_name,
        subagent_enabled=subagent_enabled,
        available_tool_names=frozenset(available_tool_names) if available_tool_names is not None else None,
    )
    return render_coding_system_prompt(profile, context)
