"""Generic MCP configuration stays separate from installed plugin manifests."""

import json
from unittest.mock import Mock

import pytest

from siada.config.mcp_config_loader import MCPConfigLoader


@pytest.fixture
def config_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "private"
    home.mkdir()
    monkeypatch.setattr("siada.config.mcp_config_loader.SIADA_HOME", home)
    plugin_dir = home / "plugins" / "configured" / ".claude-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": "configured",
        "mcpServers": {
            "plugin-only": {"command": "plugin-command"},
            "shared": {"command": "plugin-command"},
        },
    }), encoding="utf-8")
    plugin_loader = Mock(side_effect=AssertionError("Generic MCP must not scan plugins"))
    monkeypatch.setattr("siada.services.plugins.plugin_loader.PluginLoader.load_all", plugin_loader)
    return tmp_path, home, plugin_loader


@pytest.mark.parametrize("source", ["explicit", "project", "home", "merged"])
def test_loads_only_json_mcp_sources(config_sources, monkeypatch, source):
    workspace, home, plugin_loader = config_sources
    monkeypatch.setenv("SYNTHETIC_MCP_COMMAND", "resolved-command")
    project_config = workspace / "siada_mcp_config.json"
    home_config = home / "mcp_config.json"
    home_config.write_text(json.dumps({"mcpServers": {
        "home-only": {"command": "home-command"},
        "shared": {"command": "home-command"},
    }}), encoding="utf-8")
    project_config.write_text(json.dumps({"mcpServers": {
        "project-only": {"command": "${SYNTHETIC_MCP_COMMAND}"},
        "shared": {"command": "project-command"},
    }}), encoding="utf-8")
    if source == "project":
        home_config.unlink()
    elif source == "home":
        project_config.unlink()

    config = MCPConfigLoader.load_config(str(project_config) if source == "explicit" else None)
    expected = {"shared", "home-only"} if source == "home" else {"shared", "project-only"}
    if source == "merged":
        expected.add("home-only")
    assert set(config.servers) == expected
    assert config.servers["shared"].command == ("home-command" if source == "home" else "project-command")
    if source != "home":
        assert config.servers["project-only"].command == "resolved-command"
    assert "plugin-only" not in config.servers
    plugin_loader.assert_not_called()


def test_installed_plugins_do_not_enable_missing_mcp_config(config_sources):
    workspace, _, plugin_loader = config_sources
    for path in (None, str(workspace / "missing.json")):
        config = MCPConfigLoader.load_config(path)
        assert config.enabled is False and config.servers == {}
    plugin_loader.assert_not_called()


def test_runtime_config_does_not_inject_plugin_mcp(config_sources, monkeypatch):
    from siada.config.config_loader import load_conf

    workspace, home, plugin_loader = config_sources
    (home / "mcp_config.json").write_text(json.dumps({"mcpServers": {
        "generic": {"command": "generic-command"},
    }}), encoding="utf-8")
    monkeypatch.setattr("siada.config.config_loader._ensure_config_up_to_date", lambda _: None)
    monkeypatch.setattr("siada.config.config_loader.load_user_model_config", lambda: None)

    assert set(load_conf(workspace / "conf.yaml").mcp_config.servers) == {"generic"}
    plugin_loader.assert_not_called()


def test_mcp_reload_does_not_inject_plugin_mcp(config_sources):
    from siada.services.mcp.manager_service import MCPManagerService

    _, home, plugin_loader = config_sources
    config_path = home / "mcp_config.json"
    config_path.write_text(json.dumps({"mcpServers": {
        "generic": {"command": "generic-command"},
    }}), encoding="utf-8")
    service = MCPManagerService(config_path=config_path)
    assert service.reload_config() is True
    assert set(service.get_mcp_config().servers) == {"generic"}
    assert service.is_initialized is False
    plugin_loader.assert_not_called()
