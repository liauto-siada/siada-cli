import json
import pytest
from pathlib import Path

from siada.services.plugins.mcp_integration import inject_plugin_mcp_servers


class TestInjectPluginMcpServers:
    def test_injects_plugin_servers(self, tmp_path, monkeypatch):
        plugin_dir = tmp_path / "plugins" / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(json.dumps({
            "name": "my-plugin",
            "mcpServers": {
                "plugin-server": {"command": "npx", "args": ["-y", "my-pkg"]}
            }
        }))

        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.mcp_integration.SIADA_HOME", tmp_path)

        base_config = {"mcpServers": {}}
        result = inject_plugin_mcp_servers(base_config)
        assert "plugin-server" in result["mcpServers"]

    def test_user_config_overrides_plugin(self, tmp_path, monkeypatch):
        plugin_dir = tmp_path / "plugins" / "my-plugin"
        claude_plugin = plugin_dir / ".claude-plugin"
        claude_plugin.mkdir(parents=True)
        (claude_plugin / "plugin.json").write_text(json.dumps({
            "name": "my-plugin",
            "mcpServers": {
                "shared-server": {"command": "plugin-version"}
            }
        }))

        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.mcp_integration.SIADA_HOME", tmp_path)

        base_config = {
            "mcpServers": {
                "shared-server": {"command": "user-version"}
            }
        }
        result = inject_plugin_mcp_servers(base_config)
        assert result["mcpServers"]["shared-server"]["command"] == "user-version"

    def test_no_plugins_returns_base_config_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr("siada.services.plugins.plugin_loader.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.marketplace_manager.SIADA_HOME", tmp_path)
        monkeypatch.setattr("siada.services.plugins.mcp_integration.SIADA_HOME", tmp_path)

        base_config = {"mcpServers": {"existing": {"command": "cmd"}}}
        result = inject_plugin_mcp_servers(base_config)
        assert result == base_config
