import pytest
from siada.services.plugins.hook_runner import HookRunner
from siada.services.plugins.types import HookEntry, HooksConfig, LoadedPlugin, PluginManifest, _HOOK_EVENTS


def _make_plugin(pre_turn_cmd=None, pre_tool_cmd=None, matcher=None) -> LoadedPlugin:
    hooks = HooksConfig()
    if pre_turn_cmd:
        hooks.PreTurn = [HookEntry(command=pre_turn_cmd)]
    if pre_tool_cmd:
        hooks.PreToolUse = [HookEntry(command=pre_tool_cmd, matcher=matcher)]
    return LoadedPlugin(
        name="test-plugin",
        manifest=PluginManifest(name="test-plugin"),
        path="/fake/path",
        source="test",
        hooks_config=hooks,
    )


class TestHookRunner:
    def test_run_preturn_executes_command(self, tmp_path):
        marker = tmp_path / "triggered.txt"
        plugin = _make_plugin(pre_turn_cmd=f"touch {marker}")
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        runner.run("PreTurn")
        assert marker.exists()

    def test_run_unknown_event_is_noop(self):
        runner = HookRunner()
        runner.run("NoSuchEvent")  # should not raise

    def test_pretooluse_matcher_filters_by_tool(self, tmp_path):
        marker = tmp_path / "bash_triggered.txt"
        plugin = _make_plugin(pre_tool_cmd=f"touch {marker}", matcher="BashTool")
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        # Wrong tool — should NOT trigger
        runner.run("PreToolUse", context={"tool_name": "ReadFile"})
        assert not marker.exists()
        # Correct tool — should trigger
        runner.run("PreToolUse", context={"tool_name": "BashTool"})
        assert marker.exists()

    def test_pretooluse_no_matcher_fires_for_all_tools(self, tmp_path):
        marker = tmp_path / "any_tool.txt"
        plugin = _make_plugin(pre_tool_cmd=f"touch {marker}")
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        runner.run("PreToolUse", context={"tool_name": "AnyTool"})
        assert marker.exists()

    def test_failing_hook_does_not_raise(self):
        plugin = _make_plugin(pre_turn_cmd="exit 1")
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        runner.run("PreTurn")  # must not raise

    def test_register_disabled_plugin_hooks_not_added(self, tmp_path):
        marker = tmp_path / "should_not_exist.txt"
        plugin = _make_plugin(pre_turn_cmd=f"touch {marker}")
        plugin.enabled = False
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        runner.run("PreTurn")
        assert not marker.exists()

    def test_clear_resets_all_hooks(self, tmp_path):
        marker = tmp_path / "cleared.txt"
        plugin = _make_plugin(pre_turn_cmd=f"touch {marker}")
        runner = HookRunner()
        runner.register_plugin_hooks(plugin)
        runner.clear()
        runner.run("PreTurn")
        assert not marker.exists()


def test_session_events_in_hook_events():
    assert "SessionStart" in _HOOK_EVENTS
    assert "SessionEnd" in _HOOK_EVENTS


def test_hooks_config_has_session_fields():
    cfg = HooksConfig()
    assert hasattr(cfg, "SessionStart")
    assert hasattr(cfg, "SessionEnd")
    assert cfg.SessionStart == []
    assert cfg.SessionEnd == []


def test_run_session_start_executes_command(tmp_path):
    marker = tmp_path / "session_start.txt"
    hooks = HooksConfig(SessionStart=[HookEntry(command=f"touch {marker}")])
    plugin = LoadedPlugin(
        name="test-plugin",
        manifest=PluginManifest(name="test-plugin"),
        path="/fake/path",
        source="test",
        hooks_config=hooks,
    )
    runner = HookRunner()
    runner.register_plugin_hooks(plugin)
    runner.run("SessionStart")
    assert marker.exists()


def test_run_session_end_executes_command(tmp_path):
    marker = tmp_path / "session_end.txt"
    hooks = HooksConfig(SessionEnd=[HookEntry(command=f"touch {marker}")])
    plugin = LoadedPlugin(
        name="test-plugin",
        manifest=PluginManifest(name="test-plugin"),
        path="/fake/path",
        source="test",
        hooks_config=hooks,
    )
    runner = HookRunner()
    runner.register_plugin_hooks(plugin)
    runner.run("SessionEnd", {"exit_reason": "normal"})
    assert marker.exists()
