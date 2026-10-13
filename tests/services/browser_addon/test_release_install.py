"""Versioned browser package validation and transactional installation."""

import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile

import pytest

from siada.browser_addon import cli, manager, paths, release_install
from siada.foundation import node_runtime


@pytest.fixture
def package(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(home))
    monkeypatch.setattr(release_install, "package_version", lambda name: "1.7.32")
    monkeypatch.setattr(release_install.installer, "proxy_platform_tag", lambda: "linux-x64")
    stage = tmp_path / "build"
    files = {
        "runtime/bin/node": "synthetic executable",
        "runtime/LICENSE": "synthetic Node license",
        "proxy/dist/cli/bin.js": "// synthetic proxy",
        "proxy/public/index.html": "<html></html>",
        "proxy/package.json": "{}",
        "proxy/package-lock.json": "{}",
        "proxy/node_modules/stub/index.js": "// synthetic dependency",
        "proxy/LICENSE": "synthetic license",
        "proxy/THIRD_PARTY_NOTICES.md": "synthetic notices",
        "extension/manifest.json": '{"version":"1.0.45"}',
        "extension/dist/background.js": "// synthetic extension",
        "extension/icons/icon16.png": "synthetic image",
        "extension/rules/rules.json": "{}",
        "extension/LICENSE": "synthetic license",
        "extension/THIRD_PARTY_NOTICES.md": "synthetic notices",
    }
    for name, content in files.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (stage / "runtime/bin/node").chmod(0o755)
    archive = tmp_path / "siada-browser-1.7.32-linux-x64.zip"

    def repack():
        with zipfile.ZipFile(archive, "w") as zf:
            for target in stage.rglob("*"):
                zf.write(target, target.relative_to(stage))
        manifest["platforms"]["linux-x64"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()

    manifest = {
        "schema_version": 1, "version": "1.7.32",
        "node_version": node_runtime.NODE_VERSION,
        "platforms": {"linux-x64": {"filename": archive.name, "sha256": ""}},
    }
    repack()
    urls = []
    monkeypatch.setattr(
        release_install.installer, "_fetch_text",
        lambda url: urls.append(url) or json.dumps(manifest),
    )
    monkeypatch.setattr(
        release_install.installer, "_download_file",
        lambda url, dest: urls.append(url) or shutil.copyfile(archive, dest),
    )
    monkeypatch.setattr(manager, "is_running", lambda: False)
    stopped = []
    monkeypatch.setattr(manager, "stop", lambda: stopped.append(True) or "stopped")
    runs = []

    def run(argv, **kwargs):
        runs.append(argv)
        return subprocess.CompletedProcess(argv, 0, f"v{node_runtime.NODE_VERSION}\n", "")

    monkeypatch.setattr(release_install.subprocess, "run", run)
    return home, stage, archive, manifest, repack, urls, runs, stopped


def test_install_default_release_preserves_state_and_permissions(package):
    home, _, _, _, _, urls, runs, stopped = package
    home.mkdir()
    state = home / "state.json"
    state.write_text('{"token":"synthetic-token"}')
    assert release_install.install_release() == "1.7.32"
    assert urls == [
        f"{release_install.RELEASE_BASE}/v1.7.32/browser-manifest.json",
        f"{release_install.RELEASE_BASE}/v1.7.32/siada-browser-1.7.32-linux-x64.zip",
    ]
    assert paths.proxy_entry().is_file()
    assert (home / "extension/dist/background.js").is_file()
    assert (home / "runtime/bin/node").stat().st_mode & 0o111
    assert json.loads((home / "installed.json").read_text())["version"] == "1.7.32"
    assert state.read_text() == '{"token":"synthetic-token"}'
    assert len(runs) == 2
    assert stopped == [True]


@pytest.mark.parametrize("broken", ["hash", "version", "node_version", "platform", "filename", "schema"])
def test_invalid_release_leaves_old_install(package, broken):
    home, _, _, manifest, _, _, runs, stopped = package
    home.mkdir()
    old = home / "proxy"
    old.mkdir()
    (old / "old.txt").write_text("existing")
    if broken == "hash":
        manifest["platforms"]["linux-x64"]["sha256"] = "0" * 64
    elif broken == "version":
        manifest["version"] = "1.7.31"
    elif broken == "node_version":
        manifest["node_version"] = "22.0.0"
    elif broken == "platform":
        manifest["platforms"] = {}
    elif broken == "filename":
        manifest["platforms"]["linux-x64"]["filename"] = "../other.zip"
    else:
        manifest["schema_version"] = 2
    with pytest.raises(RuntimeError):
        release_install.install_release()
    assert (old / "old.txt").read_text() == "existing"
    assert stopped == []
    assert runs == []


@pytest.mark.parametrize("missing", [
    "proxy/LICENSE", "proxy/THIRD_PARTY_NOTICES.md", "runtime/LICENSE",
    "proxy/node_modules", "extension/dist/background.js",
])
def test_incomplete_package_is_rejected_before_stopping(package, missing):
    _, stage, _, _, repack, _, _, stopped = package
    target = stage / missing
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    repack()
    with pytest.raises(RuntimeError):
        release_install.install_release()
    assert stopped == []
    assert not paths.proxy_dir().exists()


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "proxy/../../escape", "runtime\\evil", "runtime/C:evil"])
def test_unsafe_zip_members_rejected(package, unsafe):
    _, _, archive, manifest, _, _, _, stopped = package
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr(unsafe, "unsafe")
    manifest["platforms"]["linux-x64"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="Unsafe"):
        release_install.install_release()
    assert stopped == []


def test_zip_symlink_rejected(package):
    _, _, archive, manifest, _, _, _, stopped = package
    info = zipfile.ZipInfo("runtime/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr(info, "../../outside")
    manifest["platforms"]["linux-x64"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="Unsafe"):
        release_install.install_release()
    assert stopped == []


def test_runtime_smoke_failure_preserves_old_install(package, monkeypatch):
    home, _, _, _, _, _, _, stopped = package
    (home / "proxy").mkdir(parents=True)
    (home / "proxy/old.txt").write_text("old")

    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(release_install.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        release_install.install_release()
    assert (home / "proxy/old.txt").read_text() == "old"
    assert stopped == []


def test_replacement_failure_rolls_back_all_components(package, monkeypatch):
    home, _, _, _, _, _, _, _ = package
    for kind in ("runtime", "proxy", "extension"):
        (home / kind).mkdir(parents=True)
        (home / kind / "old.txt").write_text(kind)
    (home / "installed.json").write_text('{"version":"old"}')
    rename = Path.rename

    def fail(self, target):
        if self.name == "extension" and self.parent.name == "stage":
            raise OSError("synthetic replacement failure")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="synthetic"):
        release_install.install_release()
    for kind in ("runtime", "proxy", "extension"):
        assert (home / kind / "old.txt").read_text() == kind
    assert (home / "installed.json").read_text() == '{"version":"old"}'


def test_ui_and_proxy_share_browser_node(package, monkeypatch):
    home, stage, _, _, _, _, _, _ = package
    shutil.copytree(stage / "runtime", home / "runtime")
    from siada.entrypoint import launch_ui_with_acp

    monkeypatch.setattr(launch_ui_with_acp, "_expected_node_path", lambda: home / "missing")
    expected = str(home / "runtime/bin/node")
    assert paths.node_binary() == expected
    assert launch_ui_with_acp.UILauncher({})._find_local_node() == expected


def test_cli_returns_failure_when_proxy_start_fails(package, monkeypatch, capsys):
    monkeypatch.setattr(manager, "restart", lambda: "error: synthetic start failure")
    monkeypatch.setattr(cli, "_open_url", lambda url: pytest.fail("must not open Chrome"))
    assert cli.main(["setup"]) == 1
    assert "synthetic start failure" in capsys.readouterr().out


@pytest.mark.parametrize("base", ["http://example.com", "file:///tmp/test", "https://example.com/?token=x"])
def test_base_url_requires_https_directory(package, base):
    with pytest.raises(ValueError, match="HTTPS"):
        release_install.install_release(base)