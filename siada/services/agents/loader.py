"""
siada/services/agents/loader.py
Agent definition loader - directory discovery, frontmatter parsing, validation.

The file format follows Claude Code's custom-agent definitions: a Markdown file
whose YAML frontmatter carries ``name`` / ``description`` / ``tools`` / ... and
whose body becomes the agent's system prompt.
"""

import logging
import re
from pathlib import Path
from typing import Generator, Optional

import yaml

from .config import (
    AGENT_FILE_SUFFIX,
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    get_agent_roots,
)
from .models import (
    AgentDefinitionError,
    AgentDefinitionParseError,
    AgentLoadOutcome,
    AgentScope,
    McpServerSpec,
    UserAgentDefinition,
)

logger = logging.getLogger(__name__)

# YAML frontmatter regex pattern (same shape as the skill loader's)
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---",
    re.DOTALL | re.MULTILINE,
)

# Reasoning effort levels a definition may request. Model-family mapping to the
# levels the effective sub-agent model accepts happens at spawn time.
VALID_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# Tool names in existing Claude Code agent definitions, mapped onto their Siada
# equivalents so a definition copied from `.claude/agents/` keeps working.
# Siada tool names themselves pass through untouched (matched case-insensitively).
TOOL_NAME_ALIASES = {
    "read": "read_file",
    "notebookread": "read_file",
    "write": "edit_file",
    "edit": "edit_file",
    "multiedit": "edit_file",
    "applypatch": "apply_patch",
    "bash": "run_cmd",
    "shell": "run_cmd",
    "grep": "regex_search_files",
    "glob": "regex_search_files",
    "task": "run_subtask",
    "agent": "run_subtask",
    "todowrite": "todo_write",
    "websearch": "web_search",
    "webfetch": "web_fetch",
}


def discover_agent_files(root: Path) -> Generator[Path, None, None]:
    """Yield every ``*.md`` agent definition file under *root* (recursively)."""
    if not root.exists() or not root.is_dir():
        return

    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir():
                yield from discover_agent_files(entry)
            elif entry.is_file() and entry.name.endswith(AGENT_FILE_SUFFIX):
                yield entry
    except PermissionError:
        logger.warning(f"Permission denied when scanning: {root}")


def parse_frontmatter(content: str) -> Optional[dict]:
    """Parse the YAML frontmatter block; None when absent or invalid.

    Third-party agent packs occasionally ship frontmatter that is not valid
    YAML — most often a plain ``description`` containing ``": "`` (e.g.
    ``... Triggers on: 'analyze A/B test'``). Such a file is retried with those
    scalars quoted (see ``_load_lenient_frontmatter``) instead of being
    rejected outright.
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None

    block = match.group(1)
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return _load_lenient_frontmatter(block)
    return parsed if isinstance(parsed, dict) else None


def _load_lenient_frontmatter(block: str) -> Optional[dict]:
    """Retry a failed YAML parse after quoting the scalars that broke it.

    Only top-level plain scalars containing ``": "`` are quoted; flow
    collections (``[a, b]`` / ``{k: v}``), already-quoted values, and nested
    lines are left untouched, so ``tools`` / ``mcpServers`` keep their shape.
    """
    fixed_lines: list[str] = []
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s+(\S.*)$", line)
        if m:
            key, value = m.group(1), m.group(2)
            if ": " in value and not value.startswith(("[", "{", '"', "'")):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                line = f'{key}: "{escaped}"'
        fixed_lines.append(line)

    try:
        parsed = yaml.safe_load("\n".join(fixed_lines))
    except yaml.YAMLError:
        return None
    if isinstance(parsed, dict):
        logger.debug("Recovered agent frontmatter with lenient YAML parsing")
        return parsed
    return None


def strip_frontmatter(content: str) -> str:
    """Return the Markdown body with the frontmatter block removed."""
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return content.strip()
    return content[match.end():].lstrip("\n").strip()


def _validate_name_description(frontmatter: dict, path: Path) -> tuple[str, str]:
    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if not name:
        raise AgentDefinitionParseError(path, "Missing required field: name")
    if not description:
        raise AgentDefinitionParseError(path, "Missing required field: description")
    if not isinstance(name, str):
        raise AgentDefinitionParseError(path, "Field 'name' must be a string")
    if not isinstance(description, str):
        raise AgentDefinitionParseError(path, "Field 'description' must be a string")
    if len(name) > MAX_NAME_LENGTH:
        raise AgentDefinitionParseError(
            path, f"Field 'name' exceeds max length ({len(name)} > {MAX_NAME_LENGTH})"
        )
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise AgentDefinitionParseError(
            path,
            f"Field 'description' exceeds max length "
            f"({len(description)} > {MAX_DESCRIPTION_LENGTH})",
        )

    return name, description


def _parse_string_list(
    value, path: Path, field_name: str, *, lowercase: bool = False
) -> list[str] | None:
    """Parse a frontmatter list field that may be a YAML list or a comma string.

    Returns None when the field is absent, so callers can tell "not configured"
    apart from "configured as empty".
    """
    if value is None:
        return None

    items: list[str]
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        items = []
        for item in value:
            if not isinstance(item, str):
                logger.warning(
                    f"Agent file {path} has non-string item in '{field_name}': {item!r}"
                )
                continue
            items.append(item.strip())
    else:
        logger.warning(
            f"Agent file {path} has invalid '{field_name}' "
            f"(expected list or comma-separated string, got {type(value).__name__})"
        )
        return None

    items = [item for item in items if item]
    if lowercase:
        items = [item.lower() for item in items]
    return items


def normalize_tool_names(names: list[str]) -> list[str]:
    """Map known external tool names onto their Siada equivalents.

    Duplicates are dropped (e.g. Claude Code's ``Write`` and ``Edit`` both map
    to ``edit_file``), preserving the order in which the tools were listed.
    """
    normalized: list[str] = []
    for name in names:
        mapped = name if name == "*" else TOOL_NAME_ALIASES.get(name.lower(), name)
        if mapped not in normalized:
            normalized.append(mapped)
    return normalized


def _parse_tools(value, path: Path) -> list[str] | None:
    names = _parse_string_list(value, path, "tools")
    if names is None:
        return None
    return normalize_tool_names(names)


def _parse_mcp_servers(value, path: Path) -> list[McpServerSpec]:
    """Parse ``mcpServers``: a list of server names and/or inline definitions."""
    if value is None:
        return []

    if isinstance(value, str):
        # Single server name, or a comma-separated list of them.
        return [part.strip() for part in value.split(",") if part.strip()]

    if not isinstance(value, list):
        logger.warning(
            f"Agent file {path} has invalid 'mcpServers' "
            f"(expected list, got {type(value).__name__})"
        )
        return []

    specs: list[McpServerSpec] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                specs.append(item.strip())
        elif isinstance(item, dict):
            for server_name, server_config in item.items():
                if not isinstance(server_name, str) or not isinstance(server_config, dict):
                    logger.warning(
                        f"Agent file {path} has invalid inline mcpServers entry: {item!r}"
                    )
                    continue
                specs.append({server_name: server_config})
        else:
            logger.warning(
                f"Agent file {path} has invalid mcpServers item: {item!r}"
            )
    return specs


def _parse_background(value, path: Path) -> bool:
    """Parse the ``background`` flag; invalid values degrade to False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    logger.warning(
        f"Agent file {path} has invalid 'background' value {value!r}. "
        "Must be true, false, or omitted."
    )
    return False


def _parse_effort(value, path: Path) -> Optional[str]:
    """Parse the ``effort`` level; invalid values are dropped with a warning."""
    if value is None:
        return None
    if not isinstance(value, str) or value.strip().lower() not in VALID_EFFORT_LEVELS:
        logger.warning(
            f"Agent file {path} has invalid 'effort' value {value!r}. "
            f"Valid options: {', '.join(VALID_EFFORT_LEVELS)}."
        )
        return None
    return value.strip().lower()


def _parse_model(value, path: Path) -> Optional[str]:
    """Parse the ``model`` field; invalid values are dropped with a warning.

    ``inherit`` — Claude Code's explicit "same model as the main agent" — maps
    to None ("not configured"), which already resolves to the conf.yaml
    sub-agent model or, failing that, the parent session's model.

    Whether the name matches a known model is not checked here: definitions are
    static files while the model catalog can change between loads, so the
    effective run validates it at spawn time (unknown names are ignored there
    with a warning).
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        name = value.strip()
        if name.lower() == "inherit":
            return None
        return name
    logger.warning(
        f"Agent file {path} has invalid 'model' value {value!r}. "
        "Must be a model name string (or 'inherit')."
    )
    return None


def parse_agent_file(path: Path, scope: AgentScope) -> UserAgentDefinition:
    """Parse one agent definition file.

    Raises:
        AgentDefinitionParseError: the file has no frontmatter, or is missing /
            malformed ``name`` / ``description``.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - surface any read failure as a parse error
        raise AgentDefinitionParseError(path, f"Failed to read file: {e}")

    frontmatter = parse_frontmatter(content)
    if frontmatter is None:
        raise AgentDefinitionParseError(
            path,
            "Missing or invalid YAML frontmatter (must start with '---')",
        )

    name, description = _validate_name_description(frontmatter, path)

    return UserAgentDefinition(
        name=name,
        description=description,
        prompt=strip_frontmatter(content),
        path=path.resolve(),
        scope=scope,
        tools=_parse_tools(frontmatter.get("tools"), path),
        skills=_parse_string_list(
            frontmatter.get("skills"), path, "skills", lowercase=True
        )
        or [],
        mcp_servers=_parse_mcp_servers(frontmatter.get("mcpServers"), path),
        background=_parse_background(frontmatter.get("background"), path),
        effort=_parse_effort(frontmatter.get("effort"), path),
        model=_parse_model(frontmatter.get("model"), path),
    )


def load_agents_from_root(root: Path, scope: AgentScope) -> AgentLoadOutcome:
    """Load every agent definition under a single root directory."""
    agents: list[UserAgentDefinition] = []
    errors: list[AgentDefinitionError] = []

    for path in discover_agent_files(root):
        try:
            agents.append(parse_agent_file(path, scope))
        except AgentDefinitionParseError as e:
            errors.append(AgentDefinitionError(path=e.path, message=e.message, scope=scope))
            logger.warning(f"Failed to load agent definition: {e}")

    return AgentLoadOutcome(agents=agents, errors=errors)


def load_agents_from_roots(
    roots: dict[AgentScope, list[Path]],
) -> AgentLoadOutcome:
    """Load agent definitions from every root with priority-based deduplication.

    Within a scope, later roots override earlier ones for the same agent name
    (last-write-wins, so the canonical ``.siada-cli/agents`` layout beats the
    compatibility ones). Across scopes, the lower ``AgentScope`` wins
    (USER > REPO). The first definition seen for a name therefore wins the
    cross-scope comparison, while later roots still replace earlier ones inside
    a scope.
    """
    by_name: dict[str, UserAgentDefinition] = {}
    errors: list[AgentDefinitionError] = []

    for scope in sorted(roots.keys()):
        for root in roots[scope]:
            outcome = load_agents_from_root(root, scope)
            errors.extend(outcome.errors)
            for agent in outcome.agents:
                existing = by_name.get(agent.name.lower())
                if existing is not None and existing.scope < agent.scope:
                    # A higher-priority scope already provided this name.
                    logger.debug(
                        f"Agent '{agent.name}' from {agent.path} shadowed by "
                        f"{existing.path} (higher-priority scope)"
                    )
                    continue
                by_name[agent.name.lower()] = agent

    agents = sorted(by_name.values(), key=lambda a: a.name.lower())
    return AgentLoadOutcome(agents=agents, errors=errors)


def load_agents_for_cwd(cwd: Path, siada_home: Optional[Path] = None) -> AgentLoadOutcome:
    """Load all agent definitions visible from *cwd* (all scopes)."""
    roots = get_agent_roots(Path(cwd), siada_home=siada_home)
    return load_agents_from_roots(roots)
