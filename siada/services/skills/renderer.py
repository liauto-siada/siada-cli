"""
siada/services/skills/renderer.py
Skill prompt renderer - generate skills section in system prompts
"""

from typing import Optional

from .models import SkillMetadata


# Skills section template
SKILLS_SECTION_TEMPLATE = """## Skills

A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill.

### Available skills

{skill_list}

### How to use skills

- **Discovery**: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- **Trigger rules**: If the user names a skill OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- **Missing/blocked**: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- **How to use a skill** (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.js`), resolve them relative to the skill directory listed above first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- **Coordination and sequencing**:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- **Context hygiene**:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- **Safety and fallback**: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""


# Hint when no skills available
NO_SKILLS_TEMPLATE = """## Skills

No skills are currently available in this session. """


def format_skill_entry(skill: SkillMetadata) -> str:
    """
    Format single skill entry
    
    Args:
        skill: Skill metadata
    
    Returns:
        Formatted string
    """
    # Use forward slashes for cross-platform consistency
    path_str = str(skill.path).replace("\\", "/")
    
    desc = skill.description
    
    # Truncate long descriptions for prompt brevity
    max_display_len = 200
    if len(desc) > max_display_len:
        desc = desc[:max_display_len - 3] + "..."
    
    return f"- **{skill.name}**: {desc}\n  - File: `{path_str}`"


def render_skills_section(
    skills: list[SkillMetadata],
    include_empty_hint: bool = False
) -> Optional[str]:
    """
    Render skills prompt section
    
    Args:
        skills: Skill metadata list
        include_empty_hint: Whether to include hint when no skills available
    
    Returns:
        Rendered prompt section, None if no skills and include_empty_hint=False
    """
    if not skills:
        return NO_SKILLS_TEMPLATE if include_empty_hint else None
    
    # Sort by name for consistency
    sorted_skills = sorted(skills, key=lambda s: s.name.lower())
    
    # Format each skill
    skill_entries = [format_skill_entry(skill) for skill in sorted_skills]
    skill_list = "\n".join(skill_entries)
    
    return SKILLS_SECTION_TEMPLATE.format(skill_list=skill_list)


def render_skill_summary(skills: list[SkillMetadata]) -> str:
    """
    Render skills brief summary (for logs or status display)
    
    Args:
        skills: Skill metadata list
    
    Returns:
        Brief summary string
    """
    if not skills:
        return "No skills loaded"
    
    names = [skill.name for skill in skills]
    return f"Loaded {len(skills)} skill(s): {', '.join(names)}"
