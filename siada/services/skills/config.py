"""
siada/services/skills/config.py
Skill configuration constants and path utilities
"""

from pathlib import Path
from typing import Optional

from siada.foundation.constants import SIADA_HOME, SIADA_DIR_NAME
from .models import SkillScope


# File name constants
SKILL_FILENAME = "SKILL.md"

# Field length limits
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

# Default directory names
SKILLS_DIR_NAME = "skills"


def get_repo_skills_root(cwd: Path) -> Path:
    """Get repository level skill root directory"""
    return cwd / SIADA_DIR_NAME / SKILLS_DIR_NAME


def get_user_skills_root(siada_home: Path = SIADA_HOME) -> Path:
    """Get user level skill root directory"""
    return siada_home / SKILLS_DIR_NAME


def get_system_skills_root() -> Path:
    """Get system level skill root directory (built-in)"""
    # System skills are stored under siada/resources/skills/
    import siada.resources
    return Path(siada.resources.__file__).parent / "skills"


def get_skill_roots(
    cwd: Path,
    siada_home: Path,
    include_system: bool = True
) -> dict[SkillScope, Path]:
    """
    Get all scope skill root directories
    
    Args:
        cwd: Current working directory
        siada_home: Siada user directory (usually ~/.siada-cli)
        include_system: Whether to include system level skills
    
    Returns:
        Dict mapping scope to path
    """
    roots = {
        SkillScope.REPO: get_repo_skills_root(cwd),
        SkillScope.USER: get_user_skills_root(siada_home),
    }
    
    if include_system:
        roots[SkillScope.SYSTEM] = get_system_skills_root()
    
    return roots


def find_git_root(start_path: Path) -> Optional[Path]:
    """
    Find Git repository root from specified path upwards
    Used to determine search scope for repository level skills
    """
    current = start_path.resolve()
    
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    
    return None
