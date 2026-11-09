"""Preferred-language system prompt section."""


def render_language_section(preferred_language: str | None) -> str:
    if preferred_language is None:
        return ""
    return f"# PREFERRED LANGUAGE\n\nSpeak in {preferred_language}."


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
        return f"====\n\n{render_language_section(preferred_language)}\n\n"
    return ""
