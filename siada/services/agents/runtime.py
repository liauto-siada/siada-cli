"""
siada/services/agents/runtime.py
Apply a user-defined agent definition to a sub-agent run.

The loader (``loader.py``) only parses definition files. This module turns a
parsed ``UserAgentDefinition`` into the pieces a spawn needs:

* the tool surface (``tools`` frontmatter filtered against the default set),
* the preloaded skill bodies (``skills`` frontmatter),
* the MCP servers (``mcpServers`` frontmatter, by name or inline),
* the reasoning effort (``effort`` frontmatter, mapped onto the effective model).

Prompt composition stays in ``siada/agent_hub/coder/sub_task_agent.py``; this
module never imports from ``siada.tools`` so the layering stays
services → (tools consume services).
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

from .models import McpServerSpec, UserAgentDefinition

logger = logging.getLogger(__name__)


@dataclass
class PreloadedSkill:
    """A skill whose SKILL.md body is inlined into the sub-agent prompt."""

    name: str
    path: Path
    content: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

# The file-editing surface is model-dependent: native-patch models expose
# `read_file` + `apply_patch`, every other family exposes `edit_file`. A
# definition naming any member of this group keeps whichever members the
# default set actually provides, so the same file survives a model switch.
_FILE_TOOL_GROUP = frozenset({"read_file", "edit_file", "apply_patch"})


def filter_tools_for_agent(
    default_tools: list,
    definition: UserAgentDefinition,
) -> list:
    """Restrict the default sub-agent tool set to the definition's ``tools``.

    ``tools`` omitted → the default set is kept as-is.
    ``tools: ["*"]`` → the default set is kept as-is.
    Otherwise only tools whose name is listed are kept. Unknown names are
    dropped with a warning; when that leaves nothing at all the default set is
    kept, so a definition written against another CLI's tool vocabulary can
    never produce a tool-less agent.
    """
    if definition.tools is None or "*" in definition.tools:
        return list(default_tools)

    wanted = {name.lower() for name in definition.tools}
    if wanted & _FILE_TOOL_GROUP:
        wanted |= _FILE_TOOL_GROUP

    available = {
        str(getattr(tool, "name", "")).lower() for tool in default_tools
    }
    kept = [
        tool
        for tool in default_tools
        if str(getattr(tool, "name", "")).lower() in wanted
    ]

    unknown = sorted(
        name for name in wanted - available if name not in _FILE_TOOL_GROUP
    )
    if unknown:
        logger.warning(
            "[user-agent] agent '%s' lists unknown tool(s): %s (available: %s)",
            definition.name,
            ", ".join(unknown),
            ", ".join(sorted(n for n in available if n)),
        )

    if not kept:
        logger.warning(
            "[user-agent] agent '%s' tool list matched no available tool; "
            "falling back to the default tool set",
            definition.name,
        )
        return list(default_tools)

    return kept


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


def load_preloaded_skills(
    definition: UserAgentDefinition,
    cwd: Path,
    siada_home: Optional[Path] = None,
) -> list[PreloadedSkill]:
    """Read the SKILL.md body of every skill named in the definition.

    Skills resolve through the same manager the main agent's catalog uses, so
    ``.agents/skills`` / ``.siada-cli/skills`` / plugin skills are all
    reachable. Unknown names are logged and skipped.
    """
    if not definition.skills:
        return []

    from siada.services.skills import SkillsManager

    from .loader import strip_frontmatter

    manager = SkillsManager.get_instance()
    preloaded: list[PreloadedSkill] = []

    for skill_name in definition.skills:
        metadata = manager.get_skill_by_name(Path(cwd), skill_name)
        if metadata is None:
            logger.warning(
                "[user-agent] agent '%s' references unknown skill '%s'",
                definition.name,
                skill_name,
            )
            continue
        try:
            content = metadata.path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - a broken skill must not break the spawn
            logger.warning(
                "[user-agent] failed to read skill '%s' (%s): %s",
                skill_name,
                metadata.path,
                e,
            )
            continue
        preloaded.append(
            PreloadedSkill(
                name=metadata.name,
                path=metadata.path,
                content=strip_frontmatter(content),
            )
        )

    return preloaded


# ---------------------------------------------------------------------------
# Effort
# ---------------------------------------------------------------------------


def resolve_effort_for_model(
    effort: Optional[str],
    model_name: Optional[str],
    model_default: Optional[str] = None,
) -> Optional[str]:
    """Map a definition's effort level onto the levels the model accepts."""
    if not effort or not model_name:
        return None
    from siada.models.model_base_config import coerce_reasoning_effort

    return coerce_reasoning_effort(model_name, effort, model_default)


# ---------------------------------------------------------------------------
# MCP servers
# ---------------------------------------------------------------------------


def _global_connected_servers() -> dict:
    """Name → connected MCPServer, from the global MCP manager (best-effort)."""
    try:
        from siada.services.mcp.manager_service import _mcp_manager_service

        return {
            server.name: server
            for server in (_mcp_manager_service.get_mcp_servers_for_agent() or [])
        }
    except Exception as e:  # noqa: BLE001 - MCP is optional
        logger.debug("[user-agent] global MCP lookup unavailable: %s", e)
        return {}


def _configured_server_configs() -> dict:
    """Name → MCPServerConfig from the merged MCP configuration (best-effort)."""
    try:
        from siada.services.mcp.manager_service import _mcp_manager_service

        config = _mcp_manager_service.get_mcp_config()
        return dict(config.servers) if config else {}
    except Exception as e:  # noqa: BLE001 - MCP is optional
        logger.debug("[user-agent] MCP config lookup unavailable: %s", e)
        return {}


def _inline_server_config(spec: dict):
    """Build an MCPServerConfig from an inline ``{name: {...}}`` spec."""
    from siada.config.mcp_config_loader import MCPConfigLoader

    resolved = MCPConfigLoader._resolve_env_variables(spec)
    return MCPConfigLoader._create_server_config(resolved)


def _split_mcp_specs(specs: list[McpServerSpec]) -> tuple[list, list]:
    """Split specs into reusable connected servers and servers to connect.

    Returns ``(reused, to_create)`` where ``reused`` holds servers the global
    MCP manager already connected and ``to_create`` holds freshly built (but not
    yet connected) ``MCPServer`` objects for the caller to manage.
    """
    from siada.services.mcp.manager_service import MCPServerFactory

    connected = _global_connected_servers()
    configured = _configured_server_configs()

    reused: list = []
    to_create: list = []
    seen: set[str] = set()

    for spec in specs:
        if isinstance(spec, str):
            name = spec
            config = None
        else:
            (name, raw_config), = spec.items()
            config = None if name in configured else raw_config

        if name in seen:
            continue
        seen.add(name)

        if name in connected:
            reused.append(connected[name])
            continue

        try:
            if config is not None:
                server = MCPServerFactory.create_server(name, _inline_server_config(config))
            elif name in configured:
                server = MCPServerFactory.create_server(name, configured[name])
            else:
                logger.warning(
                    "[user-agent] mcpServers entry '%s' is neither configured "
                    "nor an inline definition; skipping",
                    name,
                )
                continue
        except Exception as e:  # noqa: BLE001 - one bad entry must not break the spawn
            logger.warning(
                "[user-agent] failed to build MCP server '%s': %s", name, e
            )
            continue

        if server is not None:
            to_create.append(server)

    return reused, to_create


async def _preload_tool_lists(servers: list) -> None:
    """Populate each server's tool cache so name conflicts can be resolved."""
    for server in servers:
        try:
            await server.list_tools(None, None)
        except Exception as e:  # noqa: BLE001 - conflict resolution is best-effort
            logger.warning(
                "[user-agent] failed to list tools for MCP server '%s': %s",
                getattr(server, "name", "?"),
                e,
            )


@asynccontextmanager
async def open_agent_mcp_servers(
    definition: UserAgentDefinition,
) -> AsyncIterator[list]:
    """Yield the MCP servers an agent definition asks for, connected and ready.

    Servers already connected by the global MCP manager are reused as-is;
    servers that are only configured (or defined inline) are created and
    connected for the duration of the spawn, then cleaned up on exit.
    """
    if not definition.mcp_servers:
        yield []
        return

    reused, to_create = _split_mcp_specs(definition.mcp_servers)
    if not to_create:
        yield list(reused)
        return

    from agents.mcp import MCPServerManager

    from siada.services.mcp.manager_service import MCPToolNameResolver

    manager = MCPServerManager(
        servers=list(to_create),
        connect_timeout_seconds=10.0,
        cleanup_timeout_seconds=10.0,
        drop_failed_servers=True,
        strict=False,
    )
    try:
        await manager.connect_all()
        servers = list(reused) + list(manager.active_servers)
        if manager.failed_servers:
            logger.warning(
                "[user-agent] agent '%s' could not connect MCP server(s): %s",
                definition.name,
                ", ".join(getattr(s, "name", "?") for s in manager.failed_servers),
            )
        # Same conflict handling the global manager applies: rename MCP tools
        # that would shadow Siada's native tool names.
        await _preload_tool_lists(servers)
        MCPToolNameResolver().resolve_tool_conflicts(servers)
        yield servers
    finally:
        await manager.cleanup_all()
