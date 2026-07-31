from __future__ import annotations
from siada.services.plugins.types import BuiltinPluginDefinition, LoadedPlugin, PluginManifest

BUILTIN_MARKETPLACE_NAME = "builtin"

_BUILTIN_PLUGINS: dict[str, BuiltinPluginDefinition] = {}


def register_builtin_plugin(definition: BuiltinPluginDefinition) -> None:
    _BUILTIN_PLUGINS[definition.name] = definition


def clear_builtin_plugins() -> None:
    """For testing only."""
    _BUILTIN_PLUGINS.clear()


def get_builtin_plugins() -> tuple[list[LoadedPlugin], list[LoadedPlugin]]:
    """Return (enabled, disabled) LoadedPlugin lists from all registered built-ins."""
    from siada.services.plugins.marketplace_manager import MarketplaceManager

    config = MarketplaceManager().get_config()
    enabled_prefs: dict[str, bool] = config.get("enabledPlugins", {})

    enabled: list[LoadedPlugin] = []
    disabled: list[LoadedPlugin] = []

    for name, definition in _BUILTIN_PLUGINS.items():
        if definition.is_available and not definition.is_available():
            continue

        plugin_id = f"{name}@{BUILTIN_MARKETPLACE_NAME}"
        user_pref = enabled_prefs.get(plugin_id)
        is_enabled = user_pref if user_pref is not None else definition.default_enabled

        plugin = LoadedPlugin(
            name=name,
            manifest=PluginManifest(
                name=name,
                description=definition.description,
                version=definition.version,
            ),
            path=BUILTIN_MARKETPLACE_NAME,
            source=plugin_id,
            enabled=is_enabled,
            is_builtin=True,
        )

        if is_enabled:
            enabled.append(plugin)
        else:
            disabled.append(plugin)

    return enabled, disabled


def get_builtin_skill_commands() -> list:
    """Return slash commands from skills of all enabled built-in plugins."""
    enabled, _ = get_builtin_plugins()
    commands = []
    for plugin in enabled:
        definition = _BUILTIN_PLUGINS.get(plugin.name)
        if not definition or not definition.skills:
            continue
        for skill in definition.skills:
            commands.append({
                "name": getattr(skill, "name", ""),
                "description": getattr(skill, "description", ""),
                "source": "bundled",
            })
    return commands


def init_builtin_plugins() -> None:
    """Register all built-in plugins. Called at CLI startup.
    Add new built-in plugin registrations here."""
    pass  # No built-in plugins registered yet — scaffolding for future use
