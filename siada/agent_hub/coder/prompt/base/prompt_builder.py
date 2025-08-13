from .non_interactive import get_non_interactive_constraints


def build_system_prompt(intro: str, tool_use: str, capabilities: str, rules: str, objective: str, interactive_mode: bool = True) -> str:
    """
    构建系统提示词的通用函数
    
    Args:
        intro: Agent特定的介绍部分
        tool_use: 工具使用部分
        capabilities: 能力部分  
        rules: 规则部分
        objective: 目标部分
        interactive_mode: 是否为交互模式
        
    Returns:
        str: 完整的系统提示词
    """
    base_prompt = f"""{intro}

{tool_use}

{capabilities}

{rules}"""

    # 在非交互模式下添加特殊约束
    if not interactive_mode:
        base_prompt += f"\n{get_non_interactive_constraints()}"

    base_prompt += f"\n{objective}"
    
    return base_prompt
