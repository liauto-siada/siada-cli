"""
siada/services/agents/config.py
User-defined agent configuration constants and path utilities.

Agent definitions are Markdown files (``<name>.md``) with a YAML frontmatter
block, discovered under an ``agents`` subdirectory of the same layouts the
skill loader understands (``.agents`` compatibility, ``.claude`` compatibility,
and the canonical ``.siada-cli``).
"""

from pathlib import Path
from typing import Optional

from siada.foundation.constants import SIADA_HOME, SIADA_DIR_NAME

from .models import AgentScope

# Agent definition file extension
AGENT_FILE_SUFFIX = ".md"

# Field length limits
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

# Directory name holding agent definition files
AGENTS_DIR_NAME = "agents"

# Legacy repository layout from the first skills implementation, kept as a
# read-only discovery source for workspaces that already use it.
LEGACY_SIADA_DIR_NAME = ".siada"

# Compatibility layout directory name (e.g. ~/.agents/agents, <project>/.agents/agents).
AGENTS_COMPAT_DIR_NAME = ".agents"

# Claude Code compatibility layout (e.g. ~/.claude/agents, <project>/.claude/agents).
CLAUDE_DIR_NAME = ".claude"


def get_repo_agents_root(cwd: Path) -> Path:
    """Repository-level canonical root: <cwd>/.siada-cli/agents/"""
    return cwd / SIADA_DIR_NAME / AGENTS_DIR_NAME


def get_repo_legacy_agents_root(cwd: Path) -> Path:
    """Repository-level legacy root: <cwd>/.siada/agents/"""
    return cwd / LEGACY_SIADA_DIR_NAME / AGENTS_DIR_NAME


def get_repo_agents_compat_root(cwd: Path) -> Path:
    """Repository-level ``.agents`` compatibility root: <cwd>/.agents/agents/"""
    return cwd / AGENTS_COMPAT_DIR_NAME / AGENTS_DIR_NAME


def get_repo_claude_agents_root(cwd: Path) -> Path:
    """Repository-level Claude Code compatibility root: <cwd>/.claude/agents/"""
    return cwd / CLAUDE_DIR_NAME / AGENTS_DIR_NAME


def get_user_agents_root(siada_home: Optional[Path] = None) -> Path:
    """User-level canonical root: <siada_home>/agents/"""
    base = siada_home if siada_home is not None else SIADA_HOME
    return base / AGENTS_DIR_NAME


def get_user_agents_compat_root(home: Optional[Path] = None) -> Path:
    """User-level ``.agents`` compatibility root: ~/.agents/agents/"""
    base = home if home is not None else Path.home()
    return base / AGENTS_COMPAT_DIR_NAME / AGENTS_DIR_NAME


def get_user_claude_agents_root(home: Optional[Path] = None) -> Path:
    """User-level Claude Code compatibility root: ~/.claude/agents/"""
    base = home if home is not None else Path.home()
    return base / CLAUDE_DIR_NAME / AGENTS_DIR_NAME


def get_agent_roots(
    cwd: Path,
    siada_home: Optional[Path] = None,
) -> dict[AgentScope, list[Path]]:
    """Return every scope's ordered list of agent definition roots.

    Within a scope, roots are listed lowest-to-highest priority and later
    entries override earlier ones for the same agent name (last-write-wins),
    mirroring the skill loader: ``.claude`` (compat) → ``.siada`` (legacy) →
    ``.agents`` (compat) → ``.siada-cli`` (canonical). Across scopes the
    lower-numbered ``AgentScope`` wins (USER > REPO).

    Args:
        cwd: Current working directory (workspace root).
        siada_home: Siada user directory; defaults to ``~/.siada-cli``.

    Returns:
        Dict mapping scope to an ordered list of search paths.
    """
    return {
        AgentScope.REPO: [
            get_repo_claude_agents_root(cwd),
            get_repo_legacy_agents_root(cwd),
            get_repo_agents_compat_root(cwd),
            get_repo_agents_root(cwd),
        ],
        AgentScope.USER: [
            get_user_claude_agents_root(),
            get_user_agents_compat_root(),
            get_user_agents_root(siada_home),
        ],
    }
