"""Render a full Markdown system prompt template with Siada session facts.

Full-template families ship their content under ``models/``;
this renderer owns the shared substitution logic so the families cannot
drift apart in how runtime values, safety rules and optional catalogs are
spliced in. Dynamic values are substituted once and are never interpreted as
template syntax themselves.
"""

from ..sections.language import render_language_section
from .context import SystemPromptContext
from .fragments import get_skills_catalog, render_memory_section, render_runtime_instructions
from .template import render_optional_section, render_prompt_template


_SKILLS_GUIDANCE = (
    "Skills are reusable, composable capabilities that enhance your abilities. "
    "Each skill has a `SKILL.md` file containing instructions, examples, and/or reference material.\n\n"
    "Identify the skills relevant to your current task and read the skill file for its instructions; "
    "only read further skill details when needed, to conserve the context window. "
    "Instructions given directly by the user take precedence over skill guidance."
)


def render_markdown_template_prompt(
    template: str, context: SystemPromptContext, *,
    template_values: dict[str, object] | None = None, skills_guidance: str = _SKILLS_GUIDANCE,
) -> str:
    skills = ""
    if context.skills_section and context.skills_section.strip():
        catalog = get_skills_catalog(context.skills_section)
        catalog = catalog.removeprefix("## Skills\n").lstrip()
        skills = f"\n\n# Skills\n\n{skills_guidance}\n\n{catalog}"

    values = {
        **(template_values or {}),
        "capabilities": context.capabilities.strip(),
        "runtime_instructions": render_runtime_instructions(interactive_mode=context.interactive_mode),
        "os": context.os_name,
        "cwd": context.cwd,
        "home_dir": context.home_dir,
        "windows_notes": (
            "\nOn Windows, use `run_powershell` when explicit PowerShell syntax is needed "
            "and that tool is available. Prefer dedicated file tools for file operations.\n"
            if context.os_name == "Windows" else ""
        ),
        "username_section": (
            f"\nThe current user is {context.username}.\n" if context.username else ""
        ),
        "language_section": render_optional_section(
            render_language_section(context.preferred_language), prefix="\n\n",
        ),
        "skills_section": skills,
        "agents_section": render_optional_section(context.agents_section, prefix="\n\n"),
        "memory_section": render_optional_section(render_memory_section(context.user_memory), prefix="\n\n"),
    }
    return render_prompt_template(template + "\n", values)
