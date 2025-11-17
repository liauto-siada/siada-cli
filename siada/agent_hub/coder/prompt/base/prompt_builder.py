
def build_system_prompt(intro: str, tool_use: str, capabilities: str, rules: str, objective: str, user_memory: str = None, preferred_language: str = "en", agent_name: str = None) -> str:
    """
    Common function for building system prompts
    
    Args:
        intro: Agent-specific introduction section
        tool_use: Tool usage section
        capabilities: Capabilities section  
        rules: Rules section
        objective: Objective section
        user_memory: User memory content from siada.md file
        preferred_language: Preferred communication language ("en" or "zh-CN")
        agent_name: Agent name to determine default language (optional)
        
    Returns:
        str: Complete system prompt
    """
    # Build language instruction section
    language_instruction = _get_language_instruction(preferred_language, agent_name)
    
    # Assemble complete prompt
    base_prompt = f"""{intro}

{tool_use}

{capabilities}

{rules}

{objective}

{language_instruction}"""
    
    # Add user memory content if available
    if user_memory and user_memory.strip():
        memory_suffix = f"====\n\n{user_memory.strip()}"
        return f"{base_prompt}{memory_suffix}"
    
    return base_prompt


def _get_language_instruction(preferred_language: str='en', agent_name: str = None) -> str:
    """
    Get language preference instruction based on user's choice.
    Only returns instruction if the preferred language differs from the agent's default language.
    
    Args:
        preferred_language: "en" or "zh-CN"
        agent_name: Agent name to determine default language (optional)
        
    Returns:
        str: Language instruction section, or empty string if using default language
    """
    from siada.config.language_config import get_agent_default_language
    
    # Get the default language for this agent
    from siada.config.language_config import DEFAULT_LANGUAGE
    default_language = get_agent_default_language(agent_name) if agent_name else DEFAULT_LANGUAGE
    
#     if preferred_language == None:
#         return f"""====

# PREFERRED LANGUAGE

# Use the same language as the user to speak.

# """

    # Only return instruction if preferred language differs from default
    if preferred_language != default_language:
        return f"""====

PREFERRED LANGUAGE

Speak in {preferred_language}.


"""
    
    return ""
