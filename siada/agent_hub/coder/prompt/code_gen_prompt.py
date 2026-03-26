import os
import platform
from typing import List
from .base.tool_use import get_tool_use_section
from .base.capabilities import get_capabilities_section
from .base.rules import get_rules_section
from .base.prompt_builder import build_system_prompt
from .base.long_horizon import get_long_horizon_section
from siada.services.skills import get_skills_section
from siada.foundation.tools.user_info import get_username


# Shared intro and objective
INTRO = "You are Siada, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices."

OBJECTIVE = """OBJECTIVE

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

1. Analyze the user's task and set clear, achievable goals to accomplish it. Prioritize these goals in a logical order.
2. Work through these goals sequentially, utilizing available tools one at a time as necessary. Each goal should correspond to a distinct step in your problem-solving process. 
3. Remember, you have extensive capabilities with access to a wide range of tools that can be used in powerful and clever ways as necessary to accomplish each goal. First, analyze the file structure provided in environment_details to gain context and insights for proceeding effectively. Then, think about which of the provided tools is the most relevant tool to accomplish the user's task. Next, go through each of the required parameters of the relevant tool and determine if the user has directly provided or given enough information to infer a value. When deciding if the parameter can be inferred, carefully consider all the context to see if it supports a specific value. If all of the required parameters are present or can be reasonably inferred, close the thinking tag and proceed with the tool use.

"""


def get_system_prompt(cwd: str = "/default/path", interactive_mode: bool = True, user_memory: str = None,
                      preferred_language: str = None, agent_name: str = None, pre_plan: bool = False,
                      extra_capabilities: List[str] = None,
                      enable_parallel_tool_calls: bool = False) -> str:
    """Generate the system prompt for the code generation agent.

    Args:
        cwd: Current working directory path.
        interactive_mode: Whether the agent is running in interactive mode.
        user_memory: User memory content (loaded from the `siada.md` file).
        preferred_language: Preferred language code ("en" or "zh-CN").
        agent_name: Name of the agent.
        pre_plan: Whether to include pre-plan section.
        extra_capabilities: List of additional capabilities to append to the capabilities section.
        enable_parallel_tool_calls: Whether to enable parallel tool calling in prompt (Claude models only).

    Returns:
        The formatted system prompt string.
    """
    # Get OS and home directory information
    os_name = platform.system()
    home_dir = os.path.expanduser("~")

    intro = INTRO
    username = get_username()
    if username:
        intro += f"\n\nThe current user is {username}."
    objective = OBJECTIVE

    # Build capabilities section with optional extra capabilities
    capabilities = get_capabilities_section(cwd)
    if extra_capabilities:
        capabilities = capabilities  + "\n".join(extra_capabilities)

    prompt = build_system_prompt(
        intro=intro,
        tool_use=get_tool_use_section(enable_parallel_tool_calls),
        capabilities=capabilities,
        rules=get_rules_section(cwd, os_name, home_dir, interactive_mode),
        objective=objective,
        user_memory=user_memory,
        preferred_language=preferred_language,
        agent_name=agent_name,
        pre_plan=pre_plan,
        skills_section=get_skills_section(cwd)
    )
    prompt += f"====\n\n{get_long_horizon_section()}\n\n"
    return prompt
