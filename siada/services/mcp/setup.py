"""MCP configuration bootstrap shared across all entry points.

The MCP service is consumed via the global singleton
``_mcp_manager_service`` (see ``manager_service.py``).  ``siada_runner``
only initializes / attaches MCP servers when this singleton already has a
configuration loaded — i.e. ``_mcp_manager_service.has_config()`` is True.

Each process entry point (CLI ``siadahub.main``, IM ``LarkController``,
A2A server, daemon, etc.) is therefore responsible for registering the
``MCPConfig`` it loads from ``conf.yaml`` into this singleton **once**
during startup.  This module centralises that registration so every
entry point gets identical validation and side effects.

This decouples the entry-point boot code from the singleton's internal
contract, and ensures any new entry point can opt into MCP simply by
calling ``setup_mcp_config(running_config)``.
"""

from __future__ import annotations

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger
from siada.services.mcp.manager_service import _mcp_manager_service as mcp_service


def setup_mcp_config(config) -> None:
    """Register the running config's MCP settings into the global MCP manager.

    Idempotent: safe to call multiple times in the same process — later
    calls simply overwrite the stored config (the singleton intentionally
    only holds one active configuration at a time).

    Network connections are NOT established here; they are deferred to
    the agent execution path (``siada_runner``) so they live on the
    correct event loop and respect lifecycle cancellation.

    Args:
        config: Any object exposing ``.mcp_config`` (and optionally ``.io``).
                Typically a ``RunningConfig`` instance.
    """
    mcp_config = getattr(config, "mcp_config", None)
    if not mcp_config or not mcp_config.enabled:
        return
    if not mcp_config.servers:
        return

    try:
        validate_mcp_config(mcp_config)

        # Persist config in the global manager. Connections happen lazily
        # on the agent's event loop the first time an agent runs.
        io = getattr(config, "io", None)
        if io is not None:
            mcp_service.set_io(io)
        mcp_service.set_mcp_config(mcp_config)
        mcp_service.config_path = SIADA_HOME / "mcp_config.json"

        server_count = len(mcp_config.servers)
        logger.info(f"MCP: {server_count} servers configured (connections deferred)")
        if io is not None:
            try:
                io.print_info(
                    f"MCP: Configuration validated with {server_count} servers"
                )
            except Exception:
                # Some IOs (e.g. LarkIO) may not support print_info during boot.
                pass

    except Exception as e:
        # Never let an MCP misconfiguration kill the whole entry point.
        logger.error(f"MCP configuration setup failed: {e}", exc_info=True)
        io = getattr(config, "io", None)
        if io is not None:
            try:
                io.print_warning(f"MCP configuration setup failed: {e}")
            except Exception:
                pass


def validate_mcp_config(mcp_config) -> None:
    """Validate an ``MCPConfig`` instance without establishing connections."""
    if not mcp_config.servers:
        raise ValueError("No MCP servers configured")

    for server_name, server_config in mcp_config.servers.items():
        try:
            transport_type = server_config.get_transport_type()

            if transport_type.value == "stdio":
                if not server_config.command:
                    raise ValueError(
                        f"Server '{server_name}': command is required for stdio transport"
                    )
            elif transport_type.value == "http":
                # http transport accepts either url or http_url.
                if not (server_config.url or server_config.http_url):
                    raise ValueError(
                        f"Server '{server_name}': url or http_url is required for http transport"
                    )
            elif transport_type.value == "sse":
                if not server_config.url:
                    raise ValueError(
                        f"Server '{server_name}': url is required for sse transport"
                    )
            else:
                raise ValueError(
                    f"Server '{server_name}': unsupported transport type '{transport_type}'"
                )

            if server_config.timeout <= 0:
                raise ValueError(f"Server '{server_name}': timeout must be positive")

        except Exception as e:
            raise ValueError(f"Invalid configuration for server '{server_name}': {e}")

    logger.info(
        f"MCP configuration validation passed for {len(mcp_config.servers)} servers"
    )
