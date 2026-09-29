import os
import platform
from typing import List, Optional
from .base.capabilities import get_capabilities_section
from .base.rules import get_rules_section
from .base.prompt_builder import build_system_prompt
from .base.gpt5_instructions import is_gpt5_model, get_gpt5_intro
from .base.gpt6_instructions import get_gpt6_intro
from .base.skill_usage_profiles import is_gpt6_model, resolve_skill_usage_profile
from siada.services.skills import get_skills_section
from siada.services.agents import get_agents_section
from siada.foundation.tools.user_info import get_username
from siada.models.model_base_config import get_model_config


# Shared intro and objective
INTRO = "You are Siada, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices."


def _build_objective() -> str:
    """Build the OBJECTIVE section for non-GPT-5 models."""
    return """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
2. Work through these goals sequentially, utilizing available tools as necessary. Each goal should correspond to a distinct step in your problem-solving process. You will be informed on the work completed and what's remaining as you go.
3. You have extensive capabilities with access to a wide range of tools. Analyze the file structure to gain context, then choose the most relevant tool for each step. If all required parameters can be reasonably inferred, proceed with the tool use.

"""

# GPT-5 objective — the workflow steps, and nothing else.
# Three items were removed from this list because each one duplicated another
# section of the same prompt:
#   - "You have extensive capabilities with access to a wide range of tools..."
#     restated the CAPABILITIES section that sits directly above it.
#   - "Persist until the task is fully handled end-to-end..." was a shorter copy
#     of the Core Principles bullet in rules._get_gpt5_rules_section.
#   - "Unless the user explicitly asks for a plan..." was a shorter copy of the
#     autonomy_rule in that same function.
# Behaviour belongs to RULES; the objective only describes how to work a task.
# Dropping the last one also removed the need for a GPT5_OBJECTIVE_PRE_PLAN
# variant built by string .replace() on this constant.
GPT5_OBJECTIVE = """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

1. Analyze the user's task and set clear, achievable goals. Prioritize them in logical order.
2. Work through these goals sequentially, utilizing available tools as necessary. Each goal should correspond to a distinct step in your problem-solving process.

"""


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
                      preferred_language: str = None, agent_name: str = None, pre_plan: bool = False,
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
        pre_plan: Whether to include pre-plan section.
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

    # Model-family personality lives in the intro; behavioural differences are
    # resolved once in rules.py so pre_plan remains mutually exclusive there.
    if is_gpt6_model(model_name):
        intro = get_gpt6_intro(personality="gpt6")
        objective = GPT5_OBJECTIVE
    elif is_gpt5_model(model_name or ""):
        intro = get_gpt5_intro(personality="pragmatic")
        objective = GPT5_OBJECTIVE
    else:
        intro = INTRO
        objective = _build_objective()

    username = get_username()
    if username:
        intro += f"\n\nThe current user is {username}."

    # Build capabilities section with optional extra capabilities
    capabilities = get_capabilities_section(
        model_name=model_name, subagent_enabled=subagent_enabled
    )

    if extra_capabilities:
        capabilities = capabilities + "\n".join(extra_capabilities)

    prompt = build_system_prompt(
        intro=intro,
        capabilities=capabilities,
        rules=get_rules_section(cwd, os_name, home_dir, interactive_mode, model_name=model_name, pre_plan=pre_plan),
        objective=objective,
        user_memory=user_memory,
        preferred_language=preferred_language,
        agent_name=agent_name,
        pre_plan=pre_plan,
        skills_section=get_skills_section(
            cwd,
            context_window=_skills_context_window(model_name),
            activated_skill_names=activated_skill_names,
            usage_profile=resolve_skill_usage_profile(model_name),
        ),
        # The agent catalog is only advertised when the sub-agent feature is
        # on: with `sub_agent.enabled: false` the `run_subtask` tool is absent,
        # so the prompt must not mention it or list launchable agents.
        agents_section=get_agents_section(cwd) if subagent_enabled else None,
        model_name=model_name,
    )
    return prompt
