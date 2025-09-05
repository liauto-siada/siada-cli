def build_system_prompt(intro: str, tool_use: str, capabilities: str, rules: str, objective: str, user_memory: str = None) -> str:
    """
    Common function for building system prompts
    
    Args:
        intro: Agent-specific introduction section
        tool_use: Tool usage section
        capabilities: Capabilities section  
        rules: Rules section
        objective: Objective section
        user_memory: User memory content from siada.md file
        
    Returns:
        str: Complete system prompt
    """
    base_prompt = f"""{intro}

{tool_use}

{capabilities}

{rules}

{objective}"""
    
    # Add user memory content if available
    if user_memory and user_memory.strip():
        memory_suffix = f"====\n\n{user_memory.strip()}"
        return f"{base_prompt}{memory_suffix}"
    
    return base_prompt
