"""Restart-after-install contract for the public browser addon installer.

Sync of source 86f53689 (fix(installer): restart browser proxy after addon
installation): the internal tarball/local/PowerShell installers gained a
``siada-cli --browser-restart`` step that runs only after a successful addon
installation. Those installer scripts are internal-only. In this tree the
addon is installed by the public native helper — ``siada-browser setup`` /
``siada-cli --browser-setup`` — so the ported invariant is that this helper
restarts the CLI-managed browser proxy after installing, through the same
``manager.restart()`` that ``siada-cli --browser-restart`` dispatches to,
exactly once, and never restarts when the installation itself failed.
"""

from __future__ import annotations

import pytest

from siada.browser_addon import cli, installer, manager, paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(tmp_path))
    monkeypatch.setenv("SIADA_CLI_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("SIADA_PROXY_LOG_DIR", raising=False)
    return tmp_path


@pytest.fixture
def trace(home, monkeypatch):
    """Record the installer's side effects in execution order.

    Every external effect (dependency installation, proxy restart, Chrome
    GUI) is replaced by a recorder, so the tests pin ordering and failure
    semantics without touching a real proxy, browser or network.
    """
    order: list[str] = []
    monkeypatch.setattr(installer, "install_proxy", lambda repo: order.append("install_proxy"))
    monkeypatch.setattr(installer, "install_extension", lambda repo: order.append("install_extension"))
    monkeypatch.setattr(
        cli.release_install,
        "install_release",
        lambda base: order.append(f"install_release:{base}") or "1.7.32",
    )
    monkeypatch.setattr(manager, "restart", lambda: order.append("restart") or "started")
    monkeypatch.setattr(cli, "_open_url", lambda url: order.append(f"open_url:{url}"))
    monkeypatch.setattr(cli, "_copy_clipboard", lambda text: True)
    return order


def test_repo_install_restarts_the_managed_proxy_after_installing(home, trace):
    assert cli.main(["setup", "/built/chrome-acp"]) == 0
    assert trace == [
        "install_proxy",
        "install_extension",
        "restart",  # exactly once, only after both components are in place
        "open_url:chrome://extensions",
    ]


def test_release_install_restarts_the_managed_proxy_after_installing(home, trace):
    assert cli.main(["setup", "--base-url", "https://example.test/releases"]) == 0
    assert trace == [
        "install_release:https://example.test/releases",
        "restart",
        "open_url:chrome://extensions",
    ]


def test_restart_failure_is_reported_and_keeps_the_install(home, trace, monkeypatch, capsys):
    # The addon is on disk; only the restart fails (e.g. the freshly installed
    # proxy exits immediately). The installation must survive and the failure
    # must be reported instead of silently keeping the previous proxy.
    entry = paths.proxy_dir() / "dist" / "cli" / "bin.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("// installed proxy")
    monkeypatch.setattr(
        manager,
        "restart",
        lambda: trace.append("restart") or "error: proxy not healthy within 30s (see log)",
    )

    assert cli.main(["setup", "/built/chrome-acp"]) == 1

    assert "error: proxy not healthy" in capsys.readouterr().out
    assert trace == ["install_proxy", "install_extension", "restart"]
    assert entry.read_text() == "// installed proxy"
    assert paths.state_path().is_file()  # token initialized before the restart attempt


def test_failed_install_never_restarts_the_proxy(home, monkeypatch, capsys):
    def missing_repo(repo):
        raise FileNotFoundError("/built/chrome-acp not built - run `bun run build:proxy`")

    monkeypatch.setattr(installer, "install_proxy", missing_repo)
    monkeypatch.setattr(
        manager, "restart", lambda: pytest.fail("restart must not run after a failed install")
    )
    monkeypatch.setattr(
        cli, "_open_url", lambda url: pytest.fail("no Chrome guidance after a failed install")
    )

    assert cli.main(["setup", "/built/chrome-acp"]) == 1
    assert "not built" in capsys.readouterr().out
    assert not paths.state_path().exists()


def test_browser_restart_flag_shares_the_setup_restart_path(home, trace):
    """``--browser-restart`` must use the same CLI-managed proxy lifecycle as
    setup's post-install restart, not a second restart mechanism."""
    from siada.entrypoint import siadahub
    from siada.entrypoint.args_parser.args import get_parser

    args = get_parser(git_root=None, default_config_files=[]).parse_args(["--browser-restart"])
    assert siadahub._handle_browser_commands(args) == 0
    assert cli.main(["restart"]) == 0
    assert cli.main(["setup", "/built/chrome-acp"]) == 0
    assert trace == [
        "restart",  # siada-cli --browser-restart
        "restart",  # siada-browser restart
        "install_proxy",
        "install_extension",
        "restart",  # setup's post-install restart: the same lifecycle call
        "open_url:chrome://extensions",
    ]
