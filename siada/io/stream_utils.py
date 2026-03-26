"""
Stream output rendering utilities shared across ConversationTurn and tool runners.
"""
from agents import ToolOutputImage, ToolOutputText


def render_tool_call_output(io, output, tool_name: str = None) -> None:
    """Render a ToolCallOutputItem's output to IO, handling all known output types.

    Handles: FunctionCallResult (duck-typed), ToolOutputImage, ToolOutputText,
    list of the above, and plain str/anything else.
    """
    if hasattr(output, "format_for_display"):
        # FunctionCallResult or any future type with a display method
        io.print_tool_result(output.format_for_display())
    elif isinstance(output, list):
        for item in output:
            if isinstance(item, ToolOutputText):
                io.print_tool_result(item.text)
            elif isinstance(item, ToolOutputImage):
                io.print_tool_result("✓ Image loaded successfully")
            else:
                io.print_tool_result(str(item))
    elif isinstance(output, ToolOutputImage):
        io.print_tool_result("✓ Image loaded successfully")
    elif isinstance(output, ToolOutputText):
        io.print_tool_result(output.text)
    else:
        io.print_tool_result(str(output) if output is not None else "")
