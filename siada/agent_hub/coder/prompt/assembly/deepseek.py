from ..models.deepseek.templates import (
    get_deepseek_delegation_guidance,
    get_deepseek_skills_guidance,
    get_deepseek_template,
    get_deepseek_web_fetch_guidance,
    get_deepseek_web_search_guidance,
)
from ..selection.profiles import PromptProfile
from .context import SystemPromptContext
from .markdown_template import render_markdown_template_prompt


def render_deepseek_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    tool_names = context.available_tool_names or frozenset()
    web_sections = []
    if "web_search" in tool_names:
        web_sections.append(get_deepseek_web_search_guidance("web_fetch" in tool_names))
    if "web_fetch" in tool_names:
        web_sections.append(get_deepseek_web_fetch_guidance())
    return render_markdown_template_prompt(
        get_deepseek_template(), context,
        template_values={
            "model": profile.model_name,
            "web_section": "".join(f"\n\n{section}" for section in web_sections),
            "delegation_section": (
                f"\n\n{get_deepseek_delegation_guidance()}" if context.subagent_enabled else ""
            ),
        },
        skills_guidance=get_deepseek_skills_guidance(),
    )
