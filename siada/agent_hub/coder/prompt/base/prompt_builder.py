from .non_interactive import get_non_interactive_constraints


def build_system_prompt(intro: str, tool_use: str, capabilities: str, rules: str, objective: str, interactive_mode: bool = True) -> str:
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

    # Add special constraints in non-interactive mode
    if not interactive_mode:
        base_prompt += f"\n{get_non_interactive_constraints()}"
    
    return base_prompt
