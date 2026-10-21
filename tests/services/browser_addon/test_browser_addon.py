"""Tests for siada.browser_addon (simplified: install + start/stop/status)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest

from siada.browser_addon import cli, installer, manager, paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(tmp_path))
    monkeypatch.setenv("SIADA_CLI_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("SIADA_PROXY_LOG_DIR", raising=False)
    return tmp_path


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestState:
    def test_init_state_keeps_token_stable(self, home):
        s1 = manager.init_state(9315)
        s2 = manager.init_state(9316)
        assert s1["token"] == s2["token"]
        assert s2["port"] == 9316

    def test_state_file_is_0600(self, home):
        manager.init_state(9315)
        assert paths.state_path().stat().st_mode & 0o777 == 0o600

    def test_effective_port_default(self, home):
        assert manager.effective_port() == paths.DEFAULT_PORT

    def test_init_state_default_host(self, home):
        assert manager.init_state(9315)["host"] == "127.0.0.1"

    def test_init_state_persists_host(self, home):
        state = manager.init_state(9315, "0.0.0.0")
        assert state["host"] == "0.0.0.0"
        assert manager.load_state()["host"] == "0.0.0.0"

    def test_effective_host_default(self, home):
        assert manager.effective_host() == "127.0.0.1"

    def test_effective_host_from_state(self, home):
        manager.init_state(9315, "0.0.0.0")
        assert manager.effective_host() == "0.0.0.0"


class TestInstaller:
    @pytest.fixture
    def fake_repo(self, tmp_path):
        proxy = tmp_path / "packages" / "proxy-server"
        (proxy / "dist" / "cli").mkdir(parents=True)
        (proxy / "dist" / "cli" / "bin.js").write_text("// stub")
        (proxy / "public").mkdir()
        (proxy / "public" / "index.html").write_text("<html>")
        (proxy / "package.json").write_text('{"name": "@chrome-acp/proxy-server"}')
        (proxy / "package-lock.json").write_text(
            '{"name": "@chrome-acp/proxy-server", "lockfileVersion": 3, "packages": {}}'
        )

        ext = tmp_path / "packages" / "chrome-extension"
        (ext / "dist").mkdir(parents=True)
        (ext / "dist" / "background.js").write_text("// stub")
        (ext / "icons").mkdir()
        (ext / "icons" / "icon16.png").write_bytes(b"\x89PNG")
        (ext / "rules").mkdir()
        (ext / "rules" / "strip_csp.json").write_text("{}")
        (ext / "manifest.json").write_text('{"name": "Siada", "version": "0.0.0"}')
        for package in (proxy, ext):
            (package / "LICENSE").write_text("Synthetic upstream license fixture")
            (package / "THIRD_PARTY_NOTICES.md").write_text("Synthetic dependency notices")
        return tmp_path

    def test_install_layout(self, home, fake_repo, monkeypatch):
        monkeypatch.setattr(installer, "subprocess", _NoopNpm())
        installer.install_proxy(fake_repo)
        installer.install_extension(fake_repo)

        assert paths.proxy_entry() is not None
        assert (paths.proxy_dir() / "public" / "index.html").is_file()
        assert (paths.proxy_dir() / "package-lock.json").is_file()
        assert not (paths.browser_home() / "proxy.staging").exists()
        assert (paths.extension_dir() / "manifest.json").is_file()
        assert (paths.extension_dir() / "dist" / "background.js").is_file()
        assert not (paths.browser_home() / "extension.staging").exists()
        for package in (paths.proxy_dir(), paths.extension_dir()):
            assert (package / "LICENSE").read_text() == "Synthetic upstream license fixture"
            assert (package / "THIRD_PARTY_NOTICES.md").read_text() == "Synthetic dependency notices"

    def test_install_replaces_existing(self, home, fake_repo, monkeypatch):
        monkeypatch.setattr(installer, "subprocess", _NoopNpm())
        installer.install_proxy(fake_repo)
        (paths.proxy_dir() / "dist" / "cli" / "bin.js").write_text("// v2")
        installer.install_proxy(fake_repo)
        assert (paths.proxy_dir() / "dist" / "cli" / "bin.js").read_text() == "// stub"

    def test_install_requires_built_repo(self, home, tmp_path):
        with pytest.raises(FileNotFoundError):
            installer.install_proxy(tmp_path)

    def test_install_requires_reviewed_lockfile(self, home, fake_repo, monkeypatch):
        (fake_repo / "packages" / "proxy-server" / "package-lock.json").unlink()
        monkeypatch.setattr(installer, "subprocess", _NoopNpm())

        with pytest.raises(FileNotFoundError, match="package-lock.json"):
            installer.install_proxy(fake_repo)

        assert not paths.proxy_dir().exists()

    def test_install_uses_locked_production_dependencies(self, home, fake_repo, monkeypatch):
        calls = []
        monkeypatch.setattr(paths, "npm_argv", lambda: ["npm"])
        monkeypatch.setattr(
            installer.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs))
        )

        installer.install_proxy(fake_repo)

        assert calls[0][0] == [
            "npm", "ci", "--omit=dev", "--ignore-scripts",
            "--no-audit", "--no-fund", "--loglevel=error",
        ]
        assert calls[0][1]["check"] is True
        assert calls[0][1]["cwd"] == str(home / "proxy.staging")


class TestProxyPlatformTag:
    @pytest.mark.parametrize(
        "sys_platform, machine, expected",
        [
            ("darwin", "arm64", "macos-arm64"),
            ("darwin", "x86_64", "macos-x64"),
            ("linux", "x86_64", "linux-x64"),
            ("linux", "aarch64", "linux-arm64"),
            ("win32", "AMD64", "windows-x64"),
            ("freebsd", "x86_64", None),
            ("linux", "riscv64", None),
        ],
    )
    def test_mapping(self, monkeypatch, sys_platform, machine, expected):
        monkeypatch.setattr(sys, "platform", sys_platform)
        monkeypatch.setattr(installer.platform, "machine", lambda: machine)
        assert installer.proxy_platform_tag() == expected


class _NoopNpm:
    """Stand-in for installer.subprocess so dependency installation is inert."""

    def run(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        raise AttributeError(f"unexpected subprocess.{name} in test")


_FAKE_PROXY = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status": "ok", "extensionConnected": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""


class TestDetach:
    """The proxy must survive the spawning shell/console (SIGHUP on POSIX,
    CTRL_CLOSE_EVENT / Ctrl+C on Windows)."""

    def test_detach_kwargs_posix(self):
        if sys.platform.startswith("win"):
            pytest.skip("POSIX branch")
        assert manager._popen_detach_kwargs() == {"start_new_session": True}

    def test_detach_kwargs_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        kwargs = manager._popen_detach_kwargs()
        assert set(kwargs) == {"creationflags"}
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        assert kwargs["creationflags"] == 0x00000008 | 0x00000200


class TestManager:
    def test_start_without_install(self, home):
        manager.init_state(_free_port())  # isolate from a real proxy on 9315
        assert manager.start() == (
            "error: proxy not installed (run `siada-cli --browser-setup` or `siada-browser setup` first)"
        )

    def test_start_stop_lifecycle(self, home, monkeypatch, tmp_path):
        port = _free_port()
        manager.init_state(port)
        script = tmp_path / "fake_proxy.py"
        script.write_text(_FAKE_PROXY)
        monkeypatch.setenv(
            "SIADA_BROWSER_PROXY_CMD",
            f"{sys.executable} {script} {port}",
        )
        # fake a minimal installed proxy so start() passes the entry check
        (paths.proxy_dir() / "dist" / "cli").mkdir(parents=True)
        (paths.proxy_dir() / "dist" / "cli" / "bin.js").write_text("// stub")

        try:
            assert manager.is_running() is False
            assert manager.start() == "started"
            assert manager.is_running() is True
            assert manager.start() == "running"  # idempotent
            assert (paths.browser_home() / "proxy.pid").exists()
        finally:
            assert manager.stop() == "stopped"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and manager.is_running():
            time.sleep(0.1)
        assert manager.is_running() is False

    @pytest.mark.parametrize("public_key", [None, "c3ludGhldGljLXB1YmxpYy1rZXk="])
    def test_start_passes_effective_host_and_https_to_popen(self, home, monkeypatch, public_key):
        import base64
        import hashlib
        import json

        monkeypatch.setenv("SIADA_BROWSER_EXTENSION_IDS", "b" * 32)
        paths.extension_dir().mkdir()
        (paths.extension_dir() / "manifest.json").write_text(json.dumps({"key": public_key}))
        port = _free_port()
        manager.init_state(port, "0.0.0.0")
        # fake a minimal installed proxy so start() passes the entry check
        (paths.proxy_dir() / "dist" / "cli").mkdir(parents=True)
        (paths.proxy_dir() / "dist" / "cli" / "bin.js").write_text("// stub")
        monkeypatch.setattr(paths, "node_binary", lambda: "node")
        captured: dict[str, Any] = {}

        class FakeProc:
            pid = 4242

            def poll(self):
                return None

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs["env"]
            return FakeProc()

        monkeypatch.setattr(manager.subprocess, "Popen", fake_popen)
        calls = {"n": 0}

        def fake_is_running():
            calls["n"] += 1
            return calls["n"] > 1  # healthy right after spawn

        monkeypatch.setattr(manager, "is_running", fake_is_running)
        assert manager.start() == "started"
        argv = captured["cmd"]
        assert argv[argv.index("--host") + 1] == "0.0.0.0"
        assert "--https" in argv
        assert captured["env"]["SIADA_CLI_LOG_DIR"] == str(home / "logs")
        assert captured["env"]["SIADA_PROXY_LOG_DIR"] == str(home / "logs" / "proxy")
        assert captured["env"]["SIADA_PROXY_MANAGED"] == "1"
        identity = base64.b64decode(public_key) if public_key else str(paths.extension_dir().absolute()).encode()
        digest = hashlib.sha256(identity).hexdigest()[:32]
        expected_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
        assert captured["env"]["SIADA_BROWSER_EXTENSION_IDS"] == f"{expected_id},{'b' * 32}"


class TestProxySpawn:
    @pytest.fixture
    def node(self, monkeypatch):
        monkeypatch.setattr(paths, "node_binary", lambda: "node")

    def test_is_loopback(self):
        for host in ("", "localhost", "127.0.0.1", "::1"):
            assert manager._is_loopback(host)
        for host in ("0.0.0.0", "192.168.1.23", "10.0.0.5"):
            assert not manager._is_loopback(host)

    def test_proxy_argv_default_loopback(self, home, node):
        argv = manager._proxy_argv(
            Path("/p/dist/cli/bin.js"), 9315, "127.0.0.1", "siada-cli"
        )
        assert argv[argv.index("--host") + 1] == "127.0.0.1"
        assert "--https" not in argv
        assert argv[-3:] == ["siada-cli", "--", "--acp"]

    def test_proxy_argv_remote_bind_adds_https(self, home, node):
        argv = manager._proxy_argv(
            Path("/p/dist/cli/bin.js"), 9315, "0.0.0.0", "siada-cli"
        )
        assert argv[argv.index("--host") + 1] == "0.0.0.0"
        assert "--https" in argv


class TestLogLocations:
    def test_default_uses_shared_root_and_honors_proxy_override(self, home, monkeypatch):
        assert paths.log_path() == home / "logs" / "proxy" / "acp-proxy-launch.log"
        monkeypatch.setenv("SIADA_PROXY_LOG_DIR", str(home / "custom"))
        assert paths.log_path() == home / "custom" / "acp-proxy-launch.log"

    def test_bootstrap_log_is_bounded_between_launches(self, home, monkeypatch):
        monkeypatch.setattr(manager, "_LAUNCH_LOG_MAX_BYTES", 32)
        for _ in range(6):
            with manager._open_launch_log() as output:
                output.write(b"x" * 32)
        assert paths.log_path().stat().st_size == 32
        assert len(list(paths.log_directory().glob("acp-proxy-launch.log*"))) == 4


class TestHealthProbe:
    def test_probe_scheme_loopback(self, home):
        manager.init_state(_free_port())
        assert manager._probe_scheme() == "http"

    def test_probe_scheme_remote_bind_is_https(self, home):
        manager.init_state(_free_port(), "0.0.0.0")
        assert manager._probe_scheme() == "https"


class TestCli:
    @pytest.fixture
    def fake_setup(self, home, monkeypatch):
        monkeypatch.setattr(installer, "install_proxy", lambda repo: None)
        monkeypatch.setattr(installer, "install_extension", lambda repo: None)
        monkeypatch.setattr(cli, "_open_url", lambda url: None)
        monkeypatch.setattr(cli, "_copy_clipboard", lambda text: True)
        monkeypatch.setattr(manager, "lan_ip", lambda: "192.168.1.50")
        monkeypatch.setattr(manager, "restart", lambda: "started")

    def test_setup_remote_host_prints_wss_guide(self, home, fake_setup, capsys):
        assert cli.main(["setup", "/fake/repo", "--host", "0.0.0.0", "--port", "9350"]) == 0
        out = capsys.readouterr().out
        assert "wss://192.168.1.50:9350/ws" in out
        assert manager.load_state()["host"] == "0.0.0.0"

    def test_setup_default_host_omits_wss_guide(self, home, fake_setup, capsys):
        assert cli.main(["setup", "/fake/repo", "--port", "9351"]) == 0
        out = capsys.readouterr().out
        assert "wss://" not in out
        assert manager.load_state()["host"] == "127.0.0.1"

    def test_setup_without_host_downloads_matching_release(
        self, home, fake_setup, monkeypatch, capsys
    ):
        calls = []
        monkeypatch.setattr(
            cli.release_install, "install_release",
            lambda base: calls.append(base) or "1.7.32",
        )

        assert cli.main(["setup"]) == 0
        assert calls == [None]
        assert paths.state_path().exists()

    def test_setup_download_failure_does_not_initialize_state(
        self, home, fake_setup, monkeypatch, capsys
    ):
        def fail(base):
            raise RuntimeError("Browser package SHA256 mismatch")

        monkeypatch.setattr(cli.release_install, "install_release", fail)
        assert cli.main(["setup"]) == 1
        assert "SHA256 mismatch" in capsys.readouterr().out
        assert not paths.state_path().exists()

    @pytest.mark.parametrize("nested", [False, True])
    def test_setup_download_404_reports_failed_url(
        self, home, fake_setup, monkeypatch, capsys, nested
    ):
        from urllib.error import HTTPError

        url = "https://example.test/releases/browser-manifest.json"

        def fail(base):
            error = HTTPError(url, 404, "Not Found", {}, None)
            if nested:
                raise RuntimeError("no downloadable browser package") from error
            raise error

        monkeypatch.setattr(cli.release_install, "install_release", fail)
        monkeypatch.setattr(manager, "restart", lambda: pytest.fail("must not launch on failure"))
        assert cli.main(["setup", "--base-url", "https://example.test/releases"]) == 1
        out = capsys.readouterr().out
        assert "HTTP 404" in out
        assert url in out
        assert "--base-url" in out
        assert not paths.state_path().exists()
