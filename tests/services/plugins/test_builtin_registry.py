import json
import pytest
from pathlib import Path

from siada.services.plugins.builtin_registry import (
    register_builtin_plugin,
    get_builtin_plugins,
    get_builtin_skill_commands,
    clear_builtin_plugins,
    init_builtin_plugins,
    BUILTIN_MARKETPLACE_NAME,
)
from siada.services.plugins.types import BuiltinPluginDefinition


class TestBuiltinRegistry:
    def setup_method(self):
        clear_builtin_plugins()

    def teardown_method(self):
        clear_builtin_plugins()

    def test_register_and_retrieve(self):
        defn = BuiltinPluginDefinition(name="test-builtin", description="Test")
        register_builtin_plugin(defn)
        enabled, disabled = get_builtin_plugins()
        assert any(p.name == "test-builtin" for p in enabled)

    def test_default_enabled_true(self):
        register_builtin_plugin(BuiltinPluginDefinition(name="on-by-default", description=""))
        enabled, disabled = get_builtin_plugins()
        names = [p.name for p in enabled]
        assert "on-by-default" in names
        assert all(p.name != "on-by-default" for p in disabled)

    def test_default_enabled_false(self):
        register_builtin_plugin(
            BuiltinPluginDefinition(name="off-by-default", description="", default_enabled=False)
        )
        enabled, disabled = get_builtin_plugins()
        assert all(p.name != "off-by-default" for p in enabled)
        assert any(p.name == "off-by-default" for p in disabled)

    def test_is_available_false_hides_plugin(self):
        register_builtin_plugin(
            BuiltinPluginDefinition(
                name="unavailable", description="", is_available=lambda: False
            )
        )
        enabled, disabled = get_builtin_plugins()
        all_names = [p.name for p in enabled] + [p.name for p in disabled]
        assert "unavailable" not in all_names

    def test_builtin_id_format(self):
        register_builtin_plugin(BuiltinPluginDefinition(name="my-builtin", description=""))
        enabled, _ = get_builtin_plugins()
        plugin = next(p for p in enabled if p.name == "my-builtin")
        assert plugin.source == f"my-builtin@{BUILTIN_MARKETPLACE_NAME}"
        assert plugin.is_builtin is True

    def test_user_preference_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path
        )
        config = {
            "marketplaces": [],
            "disabled_skills": [],
            "enabledPlugins": {"pref-plugin@builtin": False},
        }
        (tmp_path / "plugin_config.json").write_text(json.dumps(config))

        register_builtin_plugin(
            BuiltinPluginDefinition(name="pref-plugin", description="", default_enabled=True)
        )
        enabled, disabled = get_builtin_plugins()
        assert all(p.name != "pref-plugin" for p in enabled)
        assert any(p.name == "pref-plugin" for p in disabled)

    def test_init_builtin_plugins_runs_without_error(self):
        init_builtin_plugins()  # currently empty — must not raise
