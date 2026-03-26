from typing import Optional


def build_system_prompt(
    intro: str, 
    tool_use: str, 
    capabilities: str, 
    rules: str, 
    objective: str, 
    user_memory: str = None, 
    preferred_language: str = "en", 
    agent_name: str = None,
    pre_plan: bool = False,
    skills_section: Optional[str] = None) -> str:
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
        pre_plan: Whether to include pre-plan section
        skills_section: Pre-rendered skills section content (optional)
        
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

{language_instruction}
"""
    if pre_plan:
        base_prompt += f"====\n\n{_get_pre_plan_section().strip()}"

    # Add skills section if provided
    if skills_section and skills_section.strip():
        base_prompt += f"====\n\n{skills_section}\n\n"
    
    # Add user memory content if available
    if user_memory and user_memory.strip():
        memory_suffix = f"\n{user_memory.strip()}"
        return f"{base_prompt}{memory_suffix}"

    return base_prompt

def _get_pre_plan_section() -> str:
    """
    Get pre-plan instruction section.
    
    Returns:
        str: Pre-plan instruction section
    """
    return """  
        ** Before executing any action that modifies or create files, you must first provide a design plan, and seek user's approval.**
            """
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
        
    if preferred_language is not None:
        return f"""====  

PREFERRED LANGUAGE

Speak in {preferred_language}.

"""
    return ""
