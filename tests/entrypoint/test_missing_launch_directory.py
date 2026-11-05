"""Friendly diagnostics when the launch directory has been deleted."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from siada.entrypoint import launch_ui_with_acp as launcher
from siada.entrypoint import siadahub
from siada.entrypoint.helpers import startup_guard


@pytest.fixture
def removed_launch_directory(tmp_path, monkeypatch):
    """Start the CLI from a directory that no longer exists on disk."""
    launch_dir = tmp_path / "removed-worktree"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    launch_dir.rmdir()
    monkeypatch.setattr(sys, "argv", ["siada-cli"])
    monkeypatch.delenv("SIADA_WORKSPACE", raising=False)
    return launch_dir


@pytest.fixture
def usable_directory(tmp_path, monkeypatch):
    directory = tmp_path / "workspace"
    directory.mkdir()
    monkeypatch.delenv("SIADA_WORKSPACE", raising=False)
    return directory


def test_missing_launch_directory_is_reported(removed_launch_directory):
    error = startup_guard.missing_launch_directory_error()

    assert error == startup_guard.MISSING_LAUNCH_DIRECTORY_MESSAGE
    assert "cd ~" in error and "--workspace" in error


def test_existing_launch_directory_is_accepted(usable_directory, monkeypatch):
    monkeypatch.chdir(usable_directory)

    assert startup_guard.missing_launch_directory_error() is None


def test_existing_absolute_workspace_is_accepted(removed_launch_directory, usable_directory):
    assert startup_guard.missing_launch_directory_error(str(usable_directory)) is None


def test_relative_workspace_needs_the_launch_directory(removed_launch_directory):
    assert startup_guard.missing_launch_directory_error(".") is not None


def test_workspace_argument_ignores_prompt_after_separator(usable_directory, monkeypatch):
    monkeypatch.setenv("SIADA_WORKSPACE", str(usable_directory))

    assert startup_guard.workspace_argument(
        ["--prompt", "explain", "--", "--workspace", "/tmp/not-an-option"]
    ) == str(usable_directory)
    assert startup_guard.workspace_argument(["-w", "/tmp/explicit"]) == "/tmp/explicit"
    assert startup_guard.workspace_argument(["--workspace=/tmp/joined"]) == "/tmp/joined"


def test_launcher_exits_with_friendly_message(removed_launch_directory, capsys):
    with patch.object(launcher, "_run_first_time_setup_if_needed") as first_time_setup, \
            patch.object(launcher, "_launch_ui") as launch_ui:
        result = launcher.main()

    assert result == 1
    first_time_setup.assert_not_called()
    launch_ui.assert_not_called()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == startup_guard.MISSING_LAUNCH_DIRECTORY_MESSAGE + "\n"


def test_backend_exits_with_friendly_message(removed_launch_directory, capsys):
    with patch.object(siadahub, "_preload_c_extensions_on_main_thread") as preload, \
            patch.object(siadahub, "_start_litellm_init_async") as litellm_init, \
            patch.object(siadahub, "_start_agents_init_async") as agents_init:
        result = siadahub.main()

    assert result == 1
    preload.assert_not_called()
    litellm_init.assert_not_called()
    agents_init.assert_not_called()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == startup_guard.MISSING_LAUNCH_DIRECTORY_MESSAGE + "\n"


def test_launcher_still_honors_explicit_workspace(removed_launch_directory, usable_directory, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["siada-cli", "--workspace", str(usable_directory)])

    with patch.object(launcher, "_run_first_time_setup_if_needed"), \
            patch.object(launcher, "_launch_ui", return_value=0) as launch_ui:
        result = launcher.main()

    assert result == 0
    assert launch_ui.call_args.args[0] == str(usable_directory)


def test_launcher_subprocess_prints_no_traceback(tmp_path):
    """End-to-end check that the console script exits cleanly in a deleted cwd."""
    removed_dir = tmp_path / "removed-worktree"
    removed_dir.mkdir()
    script = """
import os
import sys

work = os.environ["SIADA_TEST_REMOVED_DIR"]
os.chdir(work)
os.rmdir(work)

from siada.entrypoint import launch_ui_with_acp as launcher

sys.argv = ["siada-cli"]
sys.exit(launcher.main())
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(launcher.__file__).resolve().parents[2])
    env["SIADA_CLI_LOG_DIR"] = str(tmp_path / "logs")
    env["SIADA_TEST_REMOVED_DIR"] = str(removed_dir)
    env.pop("SIADA_WORKSPACE", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert result.stderr == startup_guard.MISSING_LAUNCH_DIRECTORY_MESSAGE + "\n"
