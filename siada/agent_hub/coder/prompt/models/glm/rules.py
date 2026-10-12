"""GLM-specific mode gates and rule renderer."""

from ...sections.rules.shared import _GIT_SAFETY_SECTION, _OWASP_RULE, _system_information_section


# GLM-5.2-and-later mode rules. The GLM identity/behaviour text itself lives
# in glm_instructions.GLM_INTRO; RULES carries the conditional mode blocks,
# safety and output conventions, and completion discipline.
_GLM_IMPLEMENTATION_MODE_SECTION = """## IMPLEMENTATION MODE
Proceed with authorized, reversible work without routine approval requests once you have enough information. Resolve ordinary implementation choices from the task and codebase instead of asking whether to continue; do not stop at a proposal when implementation was requested. Complete safe work and state a concrete blocker if only the user can unblock the rest."""

_GLM_NON_INTERACTIVE_MODE_SECTION = """## NON-INTERACTIVE MODE
Do not start operations that require user interaction or participation. Complete authorized work that does not require interaction; explain any remaining action that requires approval or participation."""

_GLM_SECURITY_SECTION = "## Security\n" + _OWASP_RULE

# Terminal output conventions shared with the other model families (the
# CLI-rendering fact itself is stated in the GLM harness section).
_GLM_TERMINAL_OUTPUT_SECTION = """## Terminal Output
- Only use emojis if the user explicitly requests it. Avoid emojis in all other communication.
- All text you output outside of tool use is shown to the user, and it is the only channel for talking to them. Never use `run_cmd` (for example `echo`) or code comments as a way to communicate with the user."""

_GLM_COMPLETION_DISCIPLINE_SECTION = """## Completion Discipline

- Check the actual requested outcome with the relevant tests or artifacts. Report failures and skipped checks plainly. Finish authorized work until verified or until a concrete external blocker remains."""


def _get_glm_rules_section(cwd: str, os_name: str, home_dir: str, interactive_mode: bool) -> str:
    """GLM-5.2-and-later rules: mode gates plus the shared safety sections.

    Behaviour, harness and communication rules come from the GLM intro; this
    section keeps Siada's safety boundaries (Git safety, secure coding),
    terminal output conventions and completion discipline.
    """
    mode_sections = [_GLM_IMPLEMENTATION_MODE_SECTION]
    if not interactive_mode:
        mode_sections.append(_GLM_NON_INTERACTIVE_MODE_SECTION)
    sections = [
        *mode_sections,
        _GIT_SAFETY_SECTION,
        _GLM_SECURITY_SECTION,
        _GLM_TERMINAL_OUTPUT_SECTION,
        _GLM_COMPLETION_DISCIPLINE_SECTION,
        _system_information_section(os_name, home_dir, cwd),
    ]
    return "# RULES\n\n" + "\n\n".join(sections)
