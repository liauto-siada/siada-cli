from typing import Optional


def get_tool_use_section(enable_parallel_tool_calls: bool = False) -> str:
    """
    Get the TOOL USE section content.

    For Claude models, the parallel_tool_calls API parameter is not supported,
    so parallel tool calling behavior must be controlled via prompt instructions.
    When enable_parallel_tool_calls is True, the prompt will instruct the model
    to use multiple tools in a single response for independent operations.

    Args:
        enable_parallel_tool_calls: Whether to enable parallel tool calling in prompt.
            Should only be set to True for Claude models with parallel_tool_calls config enabled.

    Returns:
        str: The TOOL USE section text content.
    """
    if enable_parallel_tool_calls:
        tool_desc = (
            "You have access to a set of tools that are executed upon the user's approval."
            " You may use multiple tools in a single response when the operations are independent"
            " (e.g., reading several files, searching in parallel)."
            " For dependent operations where one result informs the next, use tools sequentially."
            " You will receive the results of all tool uses in the user's response."
        )
    else:
        tool_desc = (
            "You have access to a set of tools. You can use one tool per message,"
            " and will receive the execution results of the tool."
            " You use tools step-by-step to accomplish a given task,"
            " with each tool use informed by the result of the previous tool use."
        )
    return f"""====

TOOL USE

{tool_desc}

===="""


def should_enable_parallel_tool_calls_in_prompt(run_context) -> bool:
    """
    Determine whether to enable parallel tool calling instructions in the system prompt.

    This returns True only for Claude models with parallel_tool_calls enabled,
    since Claude does not support the parallel_tool_calls API parameter and
    requires prompt-level control instead.

    Args:
        run_context: The RunContextWrapper containing agent context with session and model config.

    Returns:
        bool: True if parallel tool calling should be enabled in prompt (Claude models only).
    """
    try:
        from siada.models.model_base_config import is_claude_model
        llm_config = run_context.context.session.siada_config.llm_config
        return is_claude_model(llm_config.model_name) and bool(llm_config.parallel_tool_calls)
    except (AttributeError, TypeError):
        return False
