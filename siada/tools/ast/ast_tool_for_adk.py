from siada.tools.ast.ast_tool import _list_code_definitions_impl, AST_DOC


def list_code_definition_names(
        path: str,
        tool_context
) -> str:
    """List code definitions for ADK framework.

    Analyze a source code file and extract its structural definitions.

    Args:
        path: File path to analyze (relative to working directory or absolute)
        tool_context: The tool context for state management

    Returns:
        FunctionCallResult: Formatted string containing code definitions
    """
    import os
    root_dir = tool_context.state.get('root_dir', os.getcwd())

    context_dict = {
        'root_dir': root_dir
    }

    result = _list_code_definitions_impl(context=context_dict, path=path)
    return result.content

list_code_definition_names.__doc__ = AST_DOC
