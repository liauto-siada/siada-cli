from typing import Optional

# Outer section title wrapping the whole combined-memory snapshot at the
# system-prompt injection point. Kept here — next to the main injection
# path — so side agents (e.g. GerritIssueFixAgent) can reuse the exact
# same framing via ``wrap_user_memory`` instead of inventing ad-hoc
# prefixes like "User Memory:".
MEMORY_SECTION_TITLE = "Combined Memory"


def wrap_user_memory(user_memory: str) -> str:
    """Wrap the combined-memory snapshot in a titled ``====`` section.

    ``combined_memory`` is session-stable (built once at session start and
    rebuilt only after context compaction), so adding this wrapper does
    not hurt prompt-prefix caching stability.

    Args:
        user_memory: Assembled combined-memory content.

    Returns:
        The memory content wrapped in a ``====`` bounded section titled
        ``Combined Memory``.
    """
    return f"====\n{MEMORY_SECTION_TITLE}\n\n{user_memory.strip()}\n===="


def build_system_prompt(

    intro: str,
    capabilities: str,
    rules: str,
    objective: str,
    user_memory: str = None,
    preferred_language: str = "en",
    agent_name: str = None,
    pre_plan: bool = False,
    skills_section: Optional[str] = None,
    agents_section: Optional[str] = None,
    model_name: Optional[str] = None) -> str:
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
        pre_plan: Whether to include pre-plan section
        skills_section: Pre-rendered skills section content (optional)
        agents_section: Pre-rendered user-defined agent catalog (optional)
        model_name: Model name, used to inject GPT-5-specific sections

    Returns:
        str: Complete system prompt
    """
    # Build language instruction section
    language_instruction = _get_language_instruction(preferred_language, agent_name)

    # Assemble complete prompt
    base_prompt = f"""{intro}

{capabilities}

{rules}

{objective}

{language_instruction}
"""

    # GPT-6 uses a Codex-Astra-derived template. Its applicable instructions are
    # represented by the GPT-6 intro, rules, and skills profile; the remaining
    # Codex-only sections describe Apps, Plugins, and PR workflows unavailable
    # in Siada. Do not append GPT-5-only extra sections to GPT-6 prompts.
    from .gpt5_instructions import is_gpt5_model, get_gpt5_extra_sections
    from .skill_usage_profiles import is_gpt6_model
    is_gpt6 = is_gpt6_model(model_name)
    is_gpt5 = is_gpt5_model(model_name or "")
    if is_gpt5:
        base_prompt += f"====\n\n{get_gpt5_extra_sections()}\n\n"

    # For GPT-5 the plan-first directive is already stated by the pre_plan branch
    # of rules._get_gpt5_rules_section, so emitting this block as well would put
    # the same instruction in the prompt twice — three times back when the GPT-5
    # objective carried its own copy too. The default rules have no such branch,
    # so they still need this block.
    if pre_plan and not (is_gpt5 or is_gpt6):
        base_prompt += f"====\n\n{_get_pre_plan_section().strip()}"

    # Add skills section if provided
    if skills_section and skills_section.strip():
        base_prompt += f"====\n\n{skills_section}\n\n"

    # Add the user-defined agent catalog (`.agents/agents/*.md`) so the model
    # knows which named agents `run_subtask` can launch. Absent by default.
    if agents_section and agents_section.strip():
        base_prompt += f"====\n\n{agents_section}\n\n"

    # Add user memory content if available, framed by a titled section so
    # the model can tell where the memory snapshot begins and ends.
    if user_memory and user_memory.strip():
        memory_suffix = f"\n{wrap_user_memory(user_memory)}"
        return f"{base_prompt}{memory_suffix}"


    return base_prompt


def _get_pre_plan_section() -> str:
    """
    Get pre-plan instruction section.

    Returns:
        str: Pre-plan instruction section
    """
    return """  
        ** Before executing any action that modifies or creates files, you must first provide a design plan, and seek user's approval.**
            """


def _get_language_instruction(preferred_language: str = 'en', agent_name: str = None) -> str:
    """
    Get language preference instruction based on user's choice.
    Only returns instruction if the preferred language differs from the agent's default language.

    Args:
        preferred_language: "en" or "zh-CN"
        agent_name: Agent name to determine default language (optional)

    Returns:
        str: Language instruction section, or empty string if using default language
    """

    if preferred_language is not None:
        return f"""====  

PREFERRED LANGUAGE

Speak in {preferred_language}.

"""
    return ""
