"""Tests for siada.browser_addon (simplified: install + start/stop/status)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from siada.browser_addon import cli, installer, manager, paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(tmp_path))
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

        ext = tmp_path / "packages" / "chrome-extension"
        (ext / "dist").mkdir(parents=True)
        (ext / "dist" / "background.js").write_text("// stub")
        (ext / "icons").mkdir()
        (ext / "icons" / "icon16.png").write_bytes(b"\x89PNG")
        (ext / "rules").mkdir()
        (ext / "rules" / "strip_csp.json").write_text("{}")
        (ext / "manifest.json").write_text('{"name": "Siada", "version": "0.0.0"}')
        return tmp_path

    def test_install_layout(self, home, fake_repo, monkeypatch):
        monkeypatch.setattr(installer, "subprocess", _NoopNpm())
        installer.install_proxy(fake_repo)
        installer.install_extension(fake_repo)

        assert paths.proxy_entry() is not None
        assert (paths.proxy_dir() / "public" / "index.html").is_file()
        assert not (paths.browser_home() / "proxy.staging").exists()
        assert (paths.extension_dir() / "manifest.json").is_file()
        assert (paths.extension_dir() / "dist" / "background.js").is_file()
        assert not (paths.browser_home() / "extension.staging").exists()

    def test_install_replaces_existing(self, home, fake_repo, monkeypatch):
        monkeypatch.setattr(installer, "subprocess", _NoopNpm())
        installer.install_proxy(fake_repo)
        (paths.proxy_dir() / "dist" / "cli" / "bin.js").write_text("// v2")
        installer.install_proxy(fake_repo)
        assert (paths.proxy_dir() / "dist" / "cli" / "bin.js").read_text() == "// stub"

    def test_install_requires_built_repo(self, home, tmp_path):
        with pytest.raises(FileNotFoundError):
            installer.install_proxy(tmp_path)


class TestBosInstall:
    """BOS download path with the three network seams monkeypatched."""

    @staticmethod
    def _make_proxy_tgz(bos: Path, build_dir: Path, name: str, marker: str) -> Path:
        """Build a fake proxy tarball: root dir <name>/dist/cli/bin.js."""
        import hashlib
        import tarfile as tarfile_mod

        pkg = build_dir / name
        (pkg / "dist" / "cli").mkdir(parents=True)
        (pkg / "dist" / "cli" / "bin.js").write_text(marker)
        (pkg / "package.json").write_text("{}")
        tgz = bos / f"{name}.tar.gz"
        with tarfile_mod.open(tgz, "w:gz") as tar:
            tar.add(pkg, arcname=pkg.name)
        digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
        Path(str(tgz) + ".sha256").write_text(f"{digest}  {tgz.name}\n")
        return tgz

    @pytest.fixture
    def bos_dir(self, tmp_path, home):
        import hashlib
        import zipfile as zipfile_mod

        version = "9.9.9"
        bos = tmp_path / "bos"
        bos.mkdir()

        # noarch proxy tarball (fallback name, no platform suffix)
        self._make_proxy_tgz(
            bos, tmp_path / "pkg-build", f"chrome-acp-proxy-{version}", "// bos"
        )

        # extension zip: entries at root
        ext_stage = tmp_path / "ext-build"
        (ext_stage / "dist").mkdir(parents=True)
        (ext_stage / "dist" / "background.js").write_text("// bos")
        (ext_stage / "manifest.json").write_text('{"version": "%s"}' % version)
        ext_zip = bos / f"chrome-acp-extension-{version}.zip"
        with zipfile_mod.ZipFile(ext_zip, "w") as zf:
            for p in ext_stage.rglob("*"):
                zf.write(p, p.relative_to(ext_stage))

        digest = hashlib.sha256(ext_zip.read_bytes()).hexdigest()
        Path(str(ext_zip) + ".sha256").write_text(f"{digest}  {ext_zip.name}\n")
        (bos / "latest_version").write_text(version)
        return bos

    @pytest.fixture
    def fake_net(self, bos_dir, monkeypatch):
        def fetch_text(url):
            p = Path(url.replace("fake://bos/", str(bos_dir) + "/"))
            return p.read_text()

        def download(url, dest):
            p = Path(url.replace("fake://bos/", str(bos_dir) + "/"))
            shutil_copy(p, dest)

        def shutil_copy(src, dest):
            Path(dest).write_bytes(Path(src).read_bytes())

        monkeypatch.setattr(installer, "_fetch_text", fetch_text)
        monkeypatch.setattr(installer, "_download_file", lambda url, dest: download(url, dest))

    def test_bos_install(self, home, bos_dir, fake_net):
        # Only the noarch tarball exists → exercises the fallback path.
        v = installer.install_proxy_from_bos("fake://bos")
        assert v == "9.9.9"
        assert paths.proxy_entry() is not None
        assert (paths.proxy_dir() / "dist" / "cli" / "bin.js").read_text() == "// bos"

        ev = installer.install_extension_from_bos("fake://bos")
        assert ev == "9.9.9"
        assert (paths.extension_dir() / "manifest.json").is_file()
        assert (paths.extension_dir() / "dist" / "background.js").is_file()

    def test_bos_prefers_platform_tarball(self, home, bos_dir, fake_net, monkeypatch, tmp_path):
        monkeypatch.setattr(installer, "proxy_platform_tag", lambda: "linux-x64")
        self._make_proxy_tgz(
            bos_dir, tmp_path / "pkg-build-linux", "chrome-acp-proxy-9.9.9-linux-x64", "// linux"
        )
        v = installer.install_proxy_from_bos("fake://bos")
        assert v == "9.9.9"
        assert (paths.proxy_dir() / "dist" / "cli" / "bin.js").read_text() == "// linux"

    def test_bos_platform_sha_mismatch_not_downgraded(self, home, bos_dir, fake_net, monkeypatch, tmp_path):
        # Platform tarball exists but its hash is corrupted: must fail loudly
        # instead of silently downgrading to the noarch fallback.
        monkeypatch.setattr(installer, "proxy_platform_tag", lambda: "linux-x64")
        tgz = self._make_proxy_tgz(
            bos_dir, tmp_path / "pkg-build-linux", "chrome-acp-proxy-9.9.9-linux-x64", "// linux"
        )
        Path(str(tgz) + ".sha256").write_text(f"{'0' * 64}  {tgz.name}\n")
        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            installer.install_proxy_from_bos("fake://bos")
        assert not paths.proxy_dir().exists()

    def test_bos_sha256_mismatch(self, home, bos_dir, fake_net, monkeypatch):
        # Corrupt the expected hash → install must fail without touching proxy/
        monkeypatch.setattr(
            installer, "_fetch_text",
            lambda url: "deadbeef" if url.endswith(".sha256") else "9.9.9",
        )
        with pytest.raises(RuntimeError, match="SHA256 mismatch"):
            installer.install_proxy_from_bos("fake://bos")
        assert not paths.proxy_dir().exists()

    def test_bos_temp_cleanup_errors_ignored(self, home, bos_dir, fake_net, monkeypatch):
        # WinError 32 regression: AV scanners on Windows may briefly lock the
        # freshly downloaded archive in %TEMP%, so temp-dir cleanup can fail.
        # With ignore_cleanup_errors=True (Python 3.10+) that must not fail an
        # otherwise successful install; leftover dirs go to the OS temp cleaner.
        seen = []
        real_td = installer.tempfile.TemporaryDirectory

        def spy(*args, **kwargs):
            seen.append(kwargs)
            return real_td(*args, **kwargs)

        monkeypatch.setattr(installer.tempfile, "TemporaryDirectory", spy)
        installer.install_proxy_from_bos("fake://bos")
        installer.install_extension_from_bos("fake://bos")
        assert seen, "expected TemporaryDirectory usage to be recorded"
        assert all(kw.get("ignore_cleanup_errors") for kw in seen)


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
    """Stand-in for installer.subprocess so npm install is a no-op in tests."""

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

    def test_start_passes_effective_host_and_https_to_popen(self, home, monkeypatch):
        port = _free_port()
        manager.init_state(port, "0.0.0.0")
        # fake a minimal installed proxy so start() passes the entry check
        (paths.proxy_dir() / "dist" / "cli").mkdir(parents=True)
        (paths.proxy_dir() / "dist" / "cli" / "bin.js").write_text("// stub")
        monkeypatch.setattr(paths, "node_binary", lambda: "node")
        captured: dict[str, list[str]] = {}

        class FakeProc:
            pid = 4242

            def poll(self):
                return None

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
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
