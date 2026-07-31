"""
Injects MCP server configs from enabled plugins into the base MCP configuration.
Called by MCPConfigLoader after merging home + project configs.
"""
from __future__ import annotations
from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger


def inject_plugin_mcp_servers(base_config: dict) -> dict:
    """
    Merge mcpServers from all enabled plugins into base_config.
    Plugin servers have lowest priority — entries already in base_config win.
    Returns a new dict (does not mutate base_config).
    """
    try:
        from siada.services.plugins.plugin_loader import PluginLoader
        plugins = PluginLoader().load_all()
    except Exception as e:
        logger.warning(f"inject_plugin_mcp_servers: failed to load plugins: {e}")
        return base_config

    plugin_servers: dict = {}
    for plugin in plugins:
        if not plugin.enabled:
            continue
        for server_name, server_cfg in plugin.manifest.mcp_servers.items():
            if server_name not in plugin_servers:
                plugin_servers[server_name] = {
                    "command": server_cfg.command,
                    "args": server_cfg.args,
                    "env": server_cfg.env,
                    "url": server_cfg.url,
                }

    if not plugin_servers:
        return base_config

    result = dict(base_config)
    merged_servers = dict(plugin_servers)
    merged_servers.update(base_config.get("mcpServers") or {})
    result["mcpServers"] = merged_servers
    return result
