"""
siada/services/skills/__init__.py
Skill service module entry point
"""

from pathlib import Path
from typing import Optional, Union

from .models import (
    SkillScope,
    SkillUsageProfile,
    SkillMetadata,
    SkillError,
    SkillLoadOutcome,
    SkillParseError,
)
from .config import (
    SKILL_FILENAME,
    get_skill_roots,
    get_repo_skills_root,
    get_repo_legacy_skills_root,
    get_user_skills_root,
    get_repo_agents_skills_root,
    get_user_agents_skills_root,
    get_system_skills_root,
)

from .loader import (
    discover_skill_dirs,
    parse_skill_file,
    load_skills_from_roots,
)
from .manager import SkillsManager
from .renderer import (
    render_skills_section,
    render_skill_summary,
)


def get_skills_section(
    cwd: Union[str, Path],
    include_empty_hint: bool = False,
    context_window: Optional[int] = None,
    activated_skill_names: Optional[set[str]] = None,
    usage_profile: SkillUsageProfile = SkillUsageProfile.STRICT,
) -> Optional[str]:
    """
    Get pre-rendered skills section for system prompt.
    
    This is a convenience function that wraps SkillsManager singleton.
    
    Args:
        cwd: Current working directory (workspace path)
        include_empty_hint: Whether to include hint when no skills available
        context_window: Model context window in tokens, used to size the skill
            list budget (2% of the window). When None, a flat fallback budget
            applies (see renderer.DEFAULT_SKILLS_METADATA_CHAR_BUDGET).
        activated_skill_names: Skill names explicitly activated for this turn.
        usage_profile: Instructions paired with the skills catalog. Defaults
            to STRICT to preserve existing model behavior.

    Returns:
        Rendered skills section string, or None if no skills
    
    Example:
        skills_section = get_skills_section("/path/to/project")
        system_prompt = build_system_prompt(..., skills_section=skills_section)
    """
    return SkillsManager.get_instance().get_skills_section(
        Path(cwd),
        include_empty_hint,
        context_window=context_window,
        activated_skill_names=activated_skill_names,
        usage_profile=usage_profile,
    )


__all__ = [
    # Models
    "SkillScope",
    "SkillUsageProfile",
    "SkillMetadata",
    "SkillError",
    "SkillLoadOutcome",
    "SkillParseError",
    # Config
    "SKILL_FILENAME",
    "get_skill_roots",
    "get_repo_skills_root",
    "get_repo_legacy_skills_root",
    "get_user_skills_root",
    "get_repo_agents_skills_root",
    "get_user_agents_skills_root",
    "get_system_skills_root",

    # Loader
    "discover_skill_dirs",
    "parse_skill_file",
    "load_skills_from_roots",
    # Manager
    "SkillsManager",
    # Renderer
    "render_skills_section",
    "render_skill_summary",
    # Convenience functions
    "get_skills_section",
]
