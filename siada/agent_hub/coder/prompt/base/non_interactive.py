def get_non_interactive_constraints() -> str:
    """
    获取非交互模式约束部分的内容
    
    Returns:
        str: 非交互模式约束部分的文本内容
    """
    return """
NON-INTERACTIVE MODE CONSTRAINTS

EXECUTION MODE: Autonomous completion without user interaction.

PROHIBITED ACTIONS:
- Asking questions or requesting clarification
- Using tools requiring user input/confirmation
- Executing interactive commands or prompts
- Suggesting manual intervention steps

REQUIRED BEHAVIOR:
- Make reasonable assumptions for unclear requirements
- Provide complete, ready-to-use solutions
- Document assumptions and decisions
- Ensure definitive task completion

===="""
