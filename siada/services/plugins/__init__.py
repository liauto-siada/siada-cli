from siada.services.plugins.types import (
    MCPServerConfig,
    HookEntry,
    HooksConfig,
    PluginManifest,
    LoadedPlugin,
    BuiltinPluginDefinition,
    parse_plugin_manifest,
)
from siada.services.plugins.plugin_loader import PluginLoader
from siada.services.plugins.marketplace_manager import MarketplaceManager
from siada.services.plugins.hook_runner import HookRunner
from siada.services.plugins.mcp_integration import inject_plugin_mcp_servers
from siada.services.plugins.builtin_registry import (
    register_builtin_plugin,
    get_builtin_plugins,
    get_builtin_skill_commands,
    init_builtin_plugins,
    BUILTIN_MARKETPLACE_NAME,
)

__all__ = [
    "MCPServerConfig",
    "HookEntry",
    "HooksConfig",
    "PluginManifest",
    "LoadedPlugin",
    "BuiltinPluginDefinition",
    "parse_plugin_manifest",
    "PluginLoader",
    "MarketplaceManager",
    "HookRunner",
    "inject_plugin_mcp_servers",
    "register_builtin_plugin",
    "get_builtin_plugins",
    "get_builtin_skill_commands",
    "init_builtin_plugins",
    "BUILTIN_MARKETPLACE_NAME",
]
