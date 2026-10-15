"""Check that UI children share the CLI's resolved logging directory."""


def test_ui_environment_receives_resolved_log_root(monkeypatch, tmp_path):
    from siada.entrypoint import launch_ui_with_acp as launcher

    root = str(tmp_path / "fallback-logs")
    monkeypatch.setattr(launcher, "get_log_directory", lambda: root)
    assert launcher.UILauncher({})._setup_node_env()["SIADA_CLI_LOG_DIR"] == root