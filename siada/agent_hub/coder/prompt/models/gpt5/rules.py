"""GPT-5-specific rules and completion discipline."""

from ...sections.rules.shared import (
    _CONCISE_COMMUNICATION_SECTION,
    _GPT_COMPLETION_DISCIPLINE_SECTION,
    _render_gpt_rules,
)


def _get_gpt5_rules_section(cwd: str, os_name: str, home_dir: str, interactive_mode: bool) -> str:
    """GPT-5 optimized rules section with Codex-style constraints."""
    autonomy_rule = (
        "- Unless the user explicitly asks for a plan, asks a question about the code, is "
        "brainstorming potential solutions, or some other intent that makes it clear that code "
        "should not be written, assume the user wants you to make code changes or run tools to "
        "solve the user's problem. In these cases, do not output your proposed solution in a "
        "message — go ahead and actually implement the change. If you encounter challenges or "
        "blockers, attempt to resolve them yourself."
    )

    return _render_gpt_rules(
        cwd, os_name, home_dir, interactive_mode,
        autonomy_rule=autonomy_rule,
        completion_section=_GPT_COMPLETION_DISCIPLINE_SECTION,
        tail_sections=(_CONCISE_COMMUNICATION_SECTION,),
    )
