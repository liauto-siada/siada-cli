from ..models.default.instructions import INTRO, _build_objective
from ..models.gpt5.instructions import get_gpt5_intro
from ..sections.objectives import GPT5_OBJECTIVE
from ..sections.rules.dispatch import get_rules_for_profile
from ..selection.profiles import PromptFamily, PromptProfile
from .builder import render_system_prompt
from .context import SystemPromptContext


def render_legacy_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    if profile.family is PromptFamily.GPT5:
        intro, objective = get_gpt5_intro(personality="pragmatic"), GPT5_OBJECTIVE
    else:
        intro, objective = INTRO, _build_objective()
    if context.username:
        intro += f"\n\nThe current user is {context.username}."
    rules = get_rules_for_profile(
        context.cwd, context.os_name, context.home_dir, context.interactive_mode, profile=profile,
    )
    return render_system_prompt(
        intro=intro, capabilities=context.capabilities, rules=rules, objective=objective,
        profile=profile, user_memory=context.user_memory,
        preferred_language=context.preferred_language, agent_name=context.agent_name,
        skills_section=context.skills_section, agents_section=context.agents_section,
    )
