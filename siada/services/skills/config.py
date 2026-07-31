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

# Compatibility layout directory name (e.g. ~/.agents/skills, <project>/.agents/skills).
# The .agents/skills layout is loaded as a compatibility source. When a same-named
# skill exists under .siada-cli/skills at the same level, the siada-cli version wins
# (.siada-cli is loaded after .agents, so it overrides).
AGENTS_DIR_NAME = ".agents"

# Claude Code compatibility layout (e.g. ~/.claude/skills, <project>/.claude/skills).
# Loaded at the lowest priority within each scope so siada-native and .agents layouts
# override when the same skill name exists.
CLAUDE_DIR_NAME = ".claude"


def get_repo_skills_root(cwd: Path) -> Path:
    """Get repository level siada-cli skill root directory: <cwd>/.siada-cli/skills/"""
    return cwd / SIADA_DIR_NAME / SKILLS_DIR_NAME


def get_user_skills_root(siada_home: Path = SIADA_HOME) -> Path:
    """Get user level siada-cli skill root directory: <siada_home>/skills/"""
    return siada_home / SKILLS_DIR_NAME


def get_repo_agents_skills_root(cwd: Path) -> Path:
    """Get repository level .agents compatibility skill root: <cwd>/.agents/skills/"""
    return cwd / AGENTS_DIR_NAME / SKILLS_DIR_NAME


def get_user_agents_skills_root(home: Optional[Path] = None) -> Path:
    """Get user level .agents compatibility skill root: ~/.agents/skills/"""
    base = home if home is not None else Path.home()
    return base / AGENTS_DIR_NAME / SKILLS_DIR_NAME


def get_repo_claude_skills_root(cwd: Path) -> Path:
    """Get repository level Claude Code compatibility skill root: <cwd>/.claude/skills/"""
    return cwd / CLAUDE_DIR_NAME / SKILLS_DIR_NAME


def get_user_claude_skills_root(home: Optional[Path] = None) -> Path:
    """Get user level Claude Code compatibility skill root: ~/.claude/skills/"""
    base = home if home is not None else Path.home()
    return base / CLAUDE_DIR_NAME / SKILLS_DIR_NAME


def get_plugin_skill_roots(siada_home: Path = SIADA_HOME) -> list[Path]:
    """Return skills/ subdirs for all enabled installed plugins.

    Reads ~/.siada-cli/plugins/ directly to avoid circular imports with
    siada.services.plugins (which itself imports SkillsManager).
    """
    import json
    plugins_root = siada_home / "plugins"
    if not plugins_root.exists():
        return []

    # Read disabled list from plugin_config.json (best-effort)
    disabled: set[str] = set()
    config_path = siada_home / "plugin_config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            disabled = set(cfg.get("disabled_skills", []))
        except Exception:
            pass

    roots: list[Path] = []
    try:
        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
            if not manifest_path.exists():
                continue
            # Determine plugin name (from manifest or directory name)
            plugin_name = plugin_dir.name
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_name = data.get("name", plugin_dir.name)
            except Exception:
                pass
            if plugin_name in disabled:
                continue
            skills_dir = plugin_dir / SKILLS_DIR_NAME
            if skills_dir.is_dir():
                roots.append(skills_dir)
    except PermissionError:
        pass
    return roots


def get_system_skills_root() -> Path:
    """Get system level skill root directory (built-in)"""
    # System skills are stored under siada/resources/skills/
    import siada.resources
    return Path(siada.resources.__file__).parent / "skills"


def get_skill_roots(
    cwd: Path,
    siada_home: Path,
    include_system: bool = True,
) -> dict[SkillScope, list[Path]]:
    """
    Get all scope skill root directories.

    Each scope may map to multiple search paths. Within a single scope, paths
    are loaded in list order and later entries override earlier ones for the
    same skill name (last-write-wins).

    Layout:
        USER   -> [~/.claude/skills, ~/.agents/skills, <siada_home>/skills]
        REPO   -> [<cwd>/.claude/skills, <cwd>/.agents/skills, <cwd>/.siada-cli/skills]
        SYSTEM -> [built-in]

    Paths within each scope are ordered lowest-to-highest priority so later
    entries (siada-native) override earlier ones (compat) for the same skill
    name.  Cross-scope priority still follows ``SkillScope``
    (USER > REPO > SYSTEM).

    Args:
        cwd: Current working directory
        siada_home: Siada user directory (usually ~/.siada-cli)
        include_system: Whether to include system level skills

    Returns:
        Dict mapping scope to an ordered list of search paths
    """
    roots: dict[SkillScope, list[Path]] = {
        # NOTE: order matters - .claude (lowest compat) → .agents → .siada-cli (canonical)
        # so the canonical layout wins on duplicate skill names within the same scope.
        SkillScope.REPO: [
            get_repo_claude_skills_root(cwd),
            get_repo_agents_skills_root(cwd),
            get_repo_skills_root(cwd),
        ],
        SkillScope.USER: [
            get_user_claude_skills_root(),
            get_user_agents_skills_root(),
            get_user_skills_root(siada_home),
            *get_plugin_skill_roots(siada_home),
        ],
    }

    if include_system:
        roots[SkillScope.SYSTEM] = [get_system_skills_root()]

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
