"""Kimi Code template followed by Siada's explicit session context."""

from ..models.kimi_k3.templates import get_kimi_k3_template
from ..selection.profiles import PromptProfile
from .context import SystemPromptContext
from .markdown_template import render_markdown_template_prompt


def render_kimi_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    return render_markdown_template_prompt(get_kimi_k3_template(), context)
