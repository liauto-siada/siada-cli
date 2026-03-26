"""
siada/services/skills/__init__.py
Skill service module entry point
"""

from pathlib import Path
from typing import Optional, Union

from .models import (
    SkillScope,
    SkillMetadata,
    SkillError,
    SkillLoadOutcome,
    SkillParseError,
)
from .config import (
    SKILL_FILENAME,
    get_skill_roots,
    get_repo_skills_root,
    get_user_skills_root,
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


def get_skills_section(cwd: Union[str, Path], include_empty_hint: bool = False) -> Optional[str]:
    """
    Get pre-rendered skills section for system prompt.
    
    This is a convenience function that wraps SkillsManager singleton.
    
    Args:
        cwd: Current working directory (workspace path)
        include_empty_hint: Whether to include hint when no skills available
    
    Returns:
        Rendered skills section string, or None if no skills
    
    Example:
        skills_section = get_skills_section("/path/to/project")
        system_prompt = build_system_prompt(..., skills_section=skills_section)
    """
    return SkillsManager.get_instance().get_skills_section(Path(cwd), include_empty_hint)


__all__ = [
    # Models
    "SkillScope",
    "SkillMetadata",
    "SkillError",
    "SkillLoadOutcome",
    "SkillParseError",
    # Config
    "SKILL_FILENAME",
    "get_skill_roots",
    "get_repo_skills_root",
    "get_user_skills_root",
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
