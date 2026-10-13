"""ZCode system prompt template followed by Siada's explicit session context."""

from ..models.glm.templates import get_glm_template
from .markdown_template import render_markdown_template_prompt


def render_glm_system_prompt(
    *, cwd: str, os_name: str, home_dir: str, capabilities: str, interactive_mode: bool,
    username: str | None, preferred_language: str | None, skills_section: str | None,
    agents_section: str | None, user_memory: str | None,
) -> str:
    return render_markdown_template_prompt(
        get_glm_template(),
        cwd=cwd, os_name=os_name, home_dir=home_dir, capabilities=capabilities,
        interactive_mode=interactive_mode, username=username,
        preferred_language=preferred_language, skills_section=skills_section,
        agents_section=agents_section, user_memory=user_memory,
    )