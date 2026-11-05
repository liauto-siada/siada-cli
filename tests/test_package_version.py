"""Version resolution must describe the loaded code, not an unrelated install."""

import importlib.metadata
from pathlib import Path

import pytest

import siada


def test_checkout_uses_manifest_even_with_stale_installed_metadata(tmp_path, monkeypatch):
    package = tmp_path / "siada"
    package.mkdir()
    monkeypatch.setattr(siada, "__file__", str(package / "__init__.py"))
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "siada-cli"\nversion = "9.8.7b3"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "1.0.0")
    assert siada._resolve_version() == "9.8.7b3"


def test_checkout_without_distribution_metadata_has_a_release_version(tmp_path, monkeypatch):
    monkeypatch.setattr(siada, "__file__", str(tmp_path / "siada" / "__init__.py"))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "siada-cli"\nversion = "9.8.7"\n', encoding="utf-8"
    )

    def missing(_name):
        raise importlib.metadata.PackageNotFoundError("siada-cli")

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert siada._resolve_version() == "9.8.7"


def test_installed_package_ignores_working_directory_manifest(tmp_path, monkeypatch):
    installed = tmp_path / "installed"
    installed.mkdir()
    monkeypatch.setattr(siada, "__file__", str(installed / "siada" / "__init__.py"))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "siada-cli"\nversion = "99.0.0"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: "9.8.7")
    assert siada._resolve_version() == "9.8.7"


@pytest.mark.parametrize("value", [None, "", "dev"])
def test_invalid_installed_metadata_is_reported_instead_of_displaying_dev(tmp_path, monkeypatch, value):
    monkeypatch.setattr(siada, "__file__", str(tmp_path / "siada" / "__init__.py"))
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: value)
    with pytest.raises(RuntimeError, match="metadata is invalid"):
        siada._resolve_version()


def test_missing_installed_metadata_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(siada, "__file__", str(tmp_path / "siada" / "__init__.py"))

    def missing(_name):
        raise importlib.metadata.PackageNotFoundError("siada-cli")

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(RuntimeError, match="metadata is missing"):
        siada._resolve_version()


def test_checkout_version_matches_packaging_manifest():
    import tomllib

    manifest = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with manifest.open("rb") as source:
        expected = tomllib.load(source)["tool"]["poetry"]["version"]
    assert siada._resolve_version() == expected
    assert siada.__version__ == expected


def test_setup_marker_uses_the_shared_version(tmp_path, monkeypatch):
    from siada.entrypoint import launch_ui_with_acp as launcher

    node = tmp_path / "node"
    node.touch()
    calls = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "_expected_node_path", lambda: node)
    monkeypatch.setattr(launcher, "_kill_proactive_processes", lambda: calls.append("cleanup"))
    monkeypatch.setattr(launcher, "_check_ui_bundle", lambda: calls.append("bundle"))
    monkeypatch.setattr(siada, "__version__", "9.8.7b3")

    launcher._run_first_time_setup_if_needed()
    assert (tmp_path / ".siada-cli" / ".setup_version").read_text() == "9.8.7b3"
    launcher._run_first_time_setup_if_needed()
    assert calls == ["cleanup", "bundle"]


def test_version_query_skips_setup_and_ui(monkeypatch, capsys):
    import sys
    from siada.entrypoint import launch_ui_with_acp as launcher

    def unexpected(*_args):
        pytest.fail("A version query must not start setup or the UI")

    monkeypatch.setattr(sys, "argv", ["siada-cli", "--version"])
    monkeypatch.setattr(siada, "__version__", "9.8.7b3")
    monkeypatch.setattr(launcher, "_run_first_time_setup_if_needed", unexpected)
    monkeypatch.setattr(launcher, "_launch_ui", unexpected)
    assert launcher.main() == 0
    assert capsys.readouterr().out == "siada-cli 9.8.7b3\n"