"""Public browser packages reject unsafe archives and preserve prior installs."""

from pathlib import Path
import stat
import zipfile

import pytest

from siada.browser_addon import cli, installer, manager, release_install


@pytest.mark.parametrize("member", ["../escape", "/absolute", "proxy/../../escape", "runtime\\evil", "runtime/C:evil"])
def test_archive_path_traversal_is_rejected(tmp_path, member):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(member, "synthetic")
    with pytest.raises(RuntimeError, match="Unsafe"):
        release_install._extract(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_archive_links_are_rejected(tmp_path):
    archive = tmp_path / "unsafe.zip"
    link = zipfile.ZipInfo("runtime/link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(link, "../../outside")
    with pytest.raises(RuntimeError, match="Unsafe"):
        release_install._extract(archive, tmp_path / "out")


def test_source_install_replacement_rolls_back(tmp_path, monkeypatch):
    target = tmp_path / "proxy"
    target.mkdir()
    (target / "old.txt").write_text("existing")
    stage = tmp_path / "staging"
    stage.mkdir()
    original = Path.rename

    def fail_stage(path, destination):
        if path == stage:
            raise OSError("synthetic replacement failure")
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", fail_stage)
    with pytest.raises(OSError):
        installer._replace_dir(target, stage)
    assert (target / "old.txt").read_text() == "existing"


def test_missing_licenses_rejects_source_package(tmp_path):
    with pytest.raises(RuntimeError, match="LICENSE"):
        installer._require_license_files(tmp_path)


def test_setup_uses_release_and_propagates_restart_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(release_install, "install_release", lambda base: calls.append(base))
    monkeypatch.setattr(manager, "init_state", lambda *args: {"token": "synthetic-token"})
    monkeypatch.setattr(manager, "restart", lambda: "error: synthetic failure")
    assert cli.main(["setup", "--base-url", "https://example.invalid/release"]) == 1
    assert calls == ["https://example.invalid/release"]