import json
import pytest
from pathlib import Path

from siada.services.plugins.plugin_loader import PluginLoader


class TestPluginLoaderLoadAll:
    def test_load_all_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        loader = PluginLoader()
        plugins = loader.load_all()
        assert plugins == []

    def test_load_all_finds_plugin_with_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        plugin_dir = tmp_path / "plugins" / "my-plugin" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "description": "Test"})
        )
        loader = PluginLoader()
        plugins = loader.load_all()
        assert len(plugins) == 1
        assert plugins[0].name == "my-plugin"

    def test_load_all_skips_directory_without_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        plugin_dir = tmp_path / "plugins" / "bare-dir"
        plugin_dir.mkdir(parents=True)
        loader = PluginLoader()
        plugins = loader.load_all()
        assert plugins == []


class TestPluginLoaderEnableDisable:
    def test_set_enabled_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        loader = PluginLoader()
        loader.set_enabled("my-plugin", False)
        config_path = tmp_path / "plugin_config.json"
        config = json.loads(config_path.read_text())
        assert "my-plugin" in config.get("disabled_skills", [])

    def test_set_enabled_true_removes_from_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        loader = PluginLoader()
        loader.set_enabled("my-plugin", False)
        loader.set_enabled("my-plugin", True)
        config_path = tmp_path / "plugin_config.json"
        config = json.loads(config_path.read_text())
        assert "my-plugin" not in config.get("disabled_skills", [])


class TestPluginLoaderValidate:
    def test_valid_plugin(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "description": "test", "version": "1.0.0"})
        )
        (plugin_dir / "skills").mkdir()
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert errors == []

    def test_missing_plugin_json(self, tmp_path):
        plugin_dir = tmp_path / "no-manifest"
        plugin_dir.mkdir()
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert any("plugin.json" in e for e in errors)

    def test_missing_name_field(self, tmp_path):
        plugin_dir = tmp_path / "bad-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(json.dumps({"description": "no name"}))
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert any("name" in e for e in errors)

    def test_name_with_spaces_is_error(self, tmp_path):
        plugin_dir = tmp_path / "bad-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(json.dumps({"name": "bad name"}))
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert any("spaces" in e for e in errors)

    def test_missing_version_is_warning(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(json.dumps({"name": "my-plugin"}))
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert errors == []
        assert any("version" in w for w in warnings)

    def test_declared_skills_path_missing_is_error(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "skills": "skills/", "version": "1.0.0"})
        )
        # skills/ NOT created
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert any("skills" in e for e in errors)

    def test_invalid_hooks_json_is_error(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "hooks.json").write_text("{invalid json")
        (claude_plugin / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "version": "1.0.0", "hooks": "hooks/hooks.json"})
        )
        errors, warnings = PluginLoader.validate(str(plugin_dir))
        assert any("hooks" in e.lower() for e in errors)
