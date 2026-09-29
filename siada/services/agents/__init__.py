"""
siada/services/agents/__init__.py
User-defined agent definitions (``agents/*.md``) - loading and prompt rendering.

Layout (mirrors the skill loader; canonical layout wins on duplicate names):

    REPO -> [<cwd>/.claude/agents, <cwd>/.siada/agents,
             <cwd>/.agents/agents, <cwd>/.siada-cli/agents]
    USER -> [~/.claude/agents, ~/.agents/agents, <siada_home>/agents]

Usage::

    from siada.services.agents import get_agents_section, get_agent_definition

    section = get_agents_section(cwd)          # main-agent prompt section
    definition = get_agent_definition(cwd, "code-reviewer")
"""

from pathlib import Path
from typing import Optional

from .config import (
    AGENT_FILE_SUFFIX,
    AGENTS_DIR_NAME,
    get_agent_roots,
    get_repo_agents_compat_root,
    get_repo_agents_root,
    get_user_agents_compat_root,
    get_user_agents_root,
)
from .loader import (
    discover_agent_files,
    load_agents_for_cwd,
    load_agents_from_root,
    load_agents_from_roots,
    normalize_tool_names,
    parse_agent_file,
    parse_frontmatter,
    strip_frontmatter,
)
from .models import (
    AgentDefinitionError,
    AgentDefinitionParseError,
    AgentLoadOutcome,
    AgentScope,
    McpServerSpec,
    UserAgentDefinition,
)
from .renderer import render_agents_section
from .runtime import (
    PreloadedSkill,
    filter_tools_for_agent,
    load_preloaded_skills,
    open_agent_mcp_servers,
    resolve_effort_for_model,
)


def get_agent_definition(
    cwd: Path,
    name: str,
    siada_home: Optional[Path] = None,
) -> Optional[UserAgentDefinition]:
    """Resolve a single agent definition by name for the given workspace."""
    return load_agents_for_cwd(Path(cwd), siada_home=siada_home).get(name)


def get_agents_section(
    cwd: Path,
    siada_home: Optional[Path] = None,
) -> Optional[str]:
    """Render the agent catalog for the main agent's system prompt.

    Returns None when no definition is available, so callers can skip the
    section entirely and leave the prompt unchanged.
    """
    outcome = load_agents_for_cwd(Path(cwd), siada_home=siada_home)
    return render_agents_section(outcome.agents)


__all__ = [
    # Config
    "AGENT_FILE_SUFFIX",
    "AGENTS_DIR_NAME",
    "get_agent_roots",
    "get_repo_agents_root",
    "get_repo_agents_compat_root",
    "get_user_agents_root",
    "get_user_agents_compat_root",
    # Models
    "AgentScope",
    "UserAgentDefinition",
    "McpServerSpec",
    "AgentDefinitionError",
    "AgentLoadOutcome",
    "AgentDefinitionParseError",
    # Loader
    "discover_agent_files",
    "parse_agent_file",
    "parse_frontmatter",
    "strip_frontmatter",
    "normalize_tool_names",
    "load_agents_from_root",
    "load_agents_from_roots",
    "load_agents_for_cwd",
    # Renderer
    "render_agents_section",
    # Runtime
    "PreloadedSkill",
    "filter_tools_for_agent",
    "load_preloaded_skills",
    "resolve_effort_for_model",
    "open_agent_mcp_servers",
    # Convenience
    "get_agent_definition",
    "get_agents_section",
]
