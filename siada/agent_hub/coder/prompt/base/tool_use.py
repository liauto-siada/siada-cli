def get_tool_use_section() -> str:
    """
    获取 TOOL USE 部分的内容
    
    Returns:
        str: TOOL USE 部分的文本内容
    """
    return """====

TOOL USE

You have access to a set of tools. You can use one tool per message, and will receive the execution results of the tool. You use tools step-by-step to accomplish a given task, with each tool use informed by the result of the previous tool use.

===="""
