from typing import Optional


# Sub-agent (`run_subtask`) capability bullets. Both variants are omitted
# entirely when the sub-agent master switch (conf.yaml `sub_agent.enabled`) is
# off, so the prompt never advertises a tool the agent doesn't have.
_NATIVE_PATCH_SUBAGENT_BULLET = (
    "- Use `run_subtask` for self-contained, boundary-clear work that would "
    "otherwise clutter your context or that can run independently/in parallel "
    "— give it a self-contained instruction and use its returned summary."
)

_DEFAULT_SUBAGENT_BULLET = (
    "- Proactively reach for `run_subtask` when a piece of work has a clear, "
    "self-contained boundary, would otherwise pollute your own context with a "
    "large amount of unrelated intermediate exploration, or can be carried out "
    "independently in parallel with other work — hand it a fully "
    "self-contained instruction and let it report back a summary instead of "
    "doing that exploration inline."
)


def get_capabilities_section(
    model_name: Optional[str] = None, subagent_enabled: bool = True
) -> str:
    """
    Get the CAPABILITIES section content.

    This section answers "what tools do I have", nothing else. Tone/style and
    behavioural constraints belong to the RULES section (see rules.py) — keeping
    them there is what prevents the same rule from being stated twice with
    different strengths.

    Args:
        model_name: The model name, used to tailor the file-tool protocol.
        subagent_enabled: Whether the sub-agent (`run_subtask`) capability is
            available for this run. When False, its bullet is dropped along
            with the tool itself (conf.yaml `sub_agent.enabled`).

    Returns:
        str: The text content of the CAPABILITIES section.
    """
    from .gpt5_instructions import uses_native_patch_file_tools

    if uses_native_patch_file_tools(model_name):
        return _get_native_patch_capabilities_section(subagent_enabled=subagent_enabled)
    return _get_default_capabilities_section(subagent_enabled=subagent_enabled)


def _get_native_patch_capabilities_section(subagent_enabled: bool = True) -> str:
    """Native patch surface for GPT-5+ and the Astra compatibility alias."""
    return f"""
===

CAPABILITIES

- You have access to tools that let you execute CLI commands, search source, inspect definitions, read files, and apply focused file patches.
- You can use `regex_search_files` to perform regex searches across files, outputting context-rich results with surrounding lines.
- You can use `list_code_definition_names` to get an overview of source code definitions at the top level of a directory. Useful for understanding broader context and relationships.
- You can use `run_cmd` to run commands on the user's computer. Prefer to execute complex CLI commands over creating executable scripts.
- You can use `read_file` to view files and directories. Use `view_range` to efficiently read specific portions of large text files.
- You can use `apply_patch` to create, update, delete, and move text files with focused patches.
- You can use `todo_write` to plan and track work. Mark each task completed as soon as it's done; don't batch.
{_NATIVE_PATCH_SUBAGENT_BULLET if subagent_enabled else ""}

===
"""


def _get_default_capabilities_section(subagent_enabled: bool = True) -> str:
    """Default capabilities section for non-GPT-5 models."""
    return f"""===

CAPABILITIES

- You have access to tools that let you execute CLI commands on the user's computer, list files, view source code definitions, regex search, read and edit files. These tools help you effectively accomplish a wide range of tasks, such as writing code, making edits or improvements to existing files, understanding the current state of a project, performing system operations, and much more.
- You can use `regex_search_files` to perform regex searches across files in a specified directory, outputting context-rich results that include surrounding lines. This is particularly useful for understanding code patterns, finding specific implementations, or identifying areas that need refactoring.
- You can use the `list_code_definition_names` tool to get an overview of source code definitions for all files at the top level of a specified directory. This can be particularly useful when you need to understand the broader context and relationships between certain parts of the code. You may need to call this tool multiple times to understand various parts of the codebase related to the task.
      - For example, when asked to make edits or improvements you might use `list_code_definition_names` to get further insight using source code definitions for files located in relevant directories, then use `edit_file` to examine the contents of relevant files, analyze the code and suggest improvements or make necessary edits. If you refactored code that could affect other parts of the codebase, you could use `regex_search_files` to ensure you update other files as needed.
- You can use the `run_cmd` tool to run commands on the user's computer whenever you feel it can help accomplish the user's task. When you need to execute a CLI command, you must provide a clear explanation of what the command does. Prefer to execute complex CLI commands over creating executable scripts, since they are more flexible and easier to run.
- You can use the `todo_write` tool to plan and track work. Mark each task completed as soon as it's done; don't batch.
{_DEFAULT_SUBAGENT_BULLET if subagent_enabled else ""}


===
"""
