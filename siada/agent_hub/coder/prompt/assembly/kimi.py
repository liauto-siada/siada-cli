"""Kimi Code template followed by Siada's explicit session context."""

from string import Template

from ..models.kimi_k3.templates import get_kimi_k3_template
from ..sections.memory import wrap_user_memory
from ..sections.rules.shared import _GIT_SAFETY_SECTION, _HARNESS_SECTION, _OWASP_RULE


_SKILLS_GUIDANCE = (
    "Skills are reusable, composable capabilities that enhance your abilities. "
    "Each skill has a `SKILL.md` file containing instructions, examples, and/or reference material.\n\n"
    "Identify the skills relevant to your current task and read the skill file for its instructions; "
    "only read further skill details when needed, to conserve the context window. "
    "Instructions given directly by the user take precedence over skill guidance."
)


def render_kimi_system_prompt(
    *, cwd: str, os_name: str, home_dir: str, capabilities: str, interactive_mode: bool,
    username: str | None, preferred_language: str | None, skills_section: str | None,
    agents_section: str | None, user_memory: str | None,
) -> str:
    runtime = [
        "# Runtime instructions",
        "Use `edit_file` to inspect files and make text-file changes. "
        "Never use shell or Python write commands when the dedicated file tool can express the change.",
        _GIT_SAFETY_SECTION,
        _HARNESS_SECTION,
        _OWASP_RULE,
    ]
    if not interactive_mode:
        runtime.append(
            "## Interaction mode\n\nThis session is non-interactive, so you cannot ask the user anything. "
            "Complete authorized work autonomously. When approval or a missing decision is required, "
            "state the blocker in the final response; do not infer approval from elapsed time."
        )

    skills = ""
    if skills_section and skills_section.strip():
        catalog = skills_section.partition("\n### How to use skills")[0].strip()
        catalog = catalog.removeprefix("## Skills\n").lstrip()
        skills = f"\n\n# Skills\n\n{_SKILLS_GUIDANCE}\n\n{catalog}"

    return Template(get_kimi_k3_template()).substitute(
        capabilities=capabilities.strip(),
        runtime_instructions="\n\n".join(runtime),
        os=os_name,
        cwd=cwd,
        home_dir=home_dir,
        windows_notes=(
            "\nOn Windows, use `run_powershell` when explicit PowerShell syntax is needed "
            "and that tool is available. Prefer dedicated file tools for file operations.\n"
            if os_name == "Windows" else ""
        ),
        username_section=f"\nThe current user is {username}.\n" if username else "",
        language_section=(
            f"\n\n# PREFERRED LANGUAGE\n\nSpeak in {preferred_language}."
            if preferred_language is not None else ""
        ),
        skills_section=skills,
        agents_section=f"\n\n{agents_section.strip()}" if agents_section and agents_section.strip() else "",
        memory_section=f"\n\n{wrap_user_memory(user_memory)}" if user_memory and user_memory.strip() else "",
    ) + "\n"
