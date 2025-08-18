def build_system_prompt(intro: str, tool_use: str, capabilities: str, rules: str, objective: str) -> str:
    """
    Common function for building system prompts
    
    Args:
        intro: Agent-specific introduction section
        tool_use: Tool usage section
        capabilities: Capabilities section  
        rules: Rules section
        objective: Objective section
        interactive_mode: Whether it's interactive mode
        
    Returns:
        str: Complete system prompt
    """
    base_prompt = f"""{intro}

{tool_use}

{capabilities}

{rules}

{objective}"""
    
    return base_prompt
