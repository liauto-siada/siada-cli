"""Per-model instructions followed by explicit runtime fragments."""

from ..models.gpt6.templates import get_gpt6_template
from ..sections.language import render_language_section
from ..selection.profiles import PromptProfile
from .context import SystemPromptContext
from .fragments import get_skills_catalog, render_memory_section, render_runtime_instructions
from .template import render_optional_section, render_prompt_template


_SYSTEM_TEMPLATE = (
    "${instructions}\n\n${capabilities}\n\n${runtime_instructions}\n\n${environment}"
    "${language_section}${skills_section}${agents_section}${memory_section}\n"
)
_VERIFICATION_SECTION = (
    "## Verification\n\nFollow explicit user and repository verification requirements. "
    "Complete required checks before reporting success, even when the model template's "
    "default is to run tests only on request. Never claim that an unrun check passed."
)


def render_codex_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    """Select fixed model instructions and append only supplied session facts."""
    environment = [
        "# SYSTEM INFORMATION", f"Operating System: {context.os_name}",
        f"Home Directory: {context.home_dir}",
        f"Current Working Directory: {context.cwd} (all tools execute from this directory)",
    ]
    if context.username:
        environment.append(f"The current user is {context.username}.")
    return render_prompt_template(_SYSTEM_TEMPLATE, {
        "instructions": get_gpt6_template(profile.model_name),
        "capabilities": context.capabilities.strip(),
        "runtime_instructions": render_runtime_instructions(
            interactive_mode=context.interactive_mode, native_patch=True,
            extra_sections=(_VERIFICATION_SECTION,),
        ),
        "environment": "\n\n".join(environment),
        "language_section": render_optional_section(
            render_language_section(context.preferred_language), prefix="\n\n",
        ),
        "skills_section": (
            f"\n\n{get_skills_catalog(context.skills_section)}"
            if context.skills_section and context.skills_section.strip() else ""
        ),
        "agents_section": render_optional_section(context.agents_section, prefix="\n\n"),
        "memory_section": render_optional_section(
            render_memory_section(context.user_memory, bounded=False), prefix="\n\n",
        ),
    })
