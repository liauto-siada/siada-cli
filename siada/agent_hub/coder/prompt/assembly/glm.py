"""ZCode system prompt template followed by Siada's explicit session context."""

from ..models.glm.templates import get_glm_template
from ..selection.profiles import PromptProfile
from .context import SystemPromptContext
from .markdown_template import render_markdown_template_prompt


def render_glm_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    return render_markdown_template_prompt(get_glm_template(), context)
