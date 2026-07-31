import pytest
from siada.services.plugins.types import (
    MCPServerConfig,
    HookEntry,
    HooksConfig,
    PluginManifest,
    LoadedPlugin,
    BuiltinPluginDefinition,
    parse_plugin_manifest,
)


class TestMCPServerConfig:
    def test_command_based(self):
        cfg = MCPServerConfig(command="npx", args=["-y", "pkg"])
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "pkg"]

    def test_url_based(self):
        cfg = MCPServerConfig(url="http://localhost:8080")
        assert cfg.url == "http://localhost:8080"
        assert cfg.command is None

    def test_from_dict_command(self):
        cfg = MCPServerConfig.from_dict({"command": "python", "args": ["-m", "mod"]})
        assert cfg.command == "python"
        assert cfg.args == ["-m", "mod"]

    def test_from_dict_url(self):
        cfg = MCPServerConfig.from_dict({"url": "http://host:9000"})
        assert cfg.url == "http://host:9000"


class TestHookEntry:
    def test_basic(self):
        entry = HookEntry(command="echo hi")
        assert entry.command == "echo hi"
        assert entry.matcher is None

    def test_with_matcher(self):
        entry = HookEntry(command="audit.sh", matcher="BashTool")
        assert entry.matcher == "BashTool"


class TestHooksConfig:
    def test_empty_defaults(self):
        cfg = HooksConfig()
        assert cfg.PreTurn == []
        assert cfg.PostTurn == []
        assert cfg.PreToolUse == []
        assert cfg.PostToolUse == []
        assert cfg.OnError == []

    def test_from_dict(self):
        data = {
            "PreTurn": [{"command": "echo start"}],
            "PostToolUse": [{"command": "log.sh", "matcher": "BashTool"}],
        }
        cfg = HooksConfig.from_dict(data)
        assert len(cfg.PreTurn) == 1
        assert cfg.PreTurn[0].command == "echo start"
        assert len(cfg.PostToolUse) == 1
        assert cfg.PostToolUse[0].matcher == "BashTool"

    def test_from_dict_unknown_event_ignored(self):
        data = {"UnknownEvent": [{"command": "x"}]}
        cfg = HooksConfig.from_dict(data)
        assert cfg.PreTurn == []


class TestPluginManifest:
    def test_defaults(self):
        m = PluginManifest(name="my-plugin")
        assert m.skills == "skills/"
        assert m.hooks == "hooks/hooks.json"
        assert m.mcp_servers == {}

    def test_name_required(self):
        with pytest.raises(ValueError, match="name"):
            PluginManifest(name="")

    def test_name_no_spaces(self):
        with pytest.raises(ValueError, match="spaces"):
            PluginManifest(name="my plugin")


class TestParsePluginManifest:
    def test_valid(self):
        data = {
            "name": "test-plugin",
            "description": "A test plugin",
            "version": "1.0.0",
            "skills": "custom-skills/",
        }
        m = parse_plugin_manifest(data)
        assert m.name == "test-plugin"
        assert m.skills == "custom-skills/"

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            parse_plugin_manifest({})

    def test_mcp_servers_parsed(self):
        data = {
            "name": "mcp-plugin",
            "mcpServers": {
                "my-server": {"command": "npx", "args": ["-y", "pkg"]}
            },
        }
        m = parse_plugin_manifest(data)
        assert "my-server" in m.mcp_servers
        assert m.mcp_servers["my-server"].command == "npx"
