"""Validate selection, environment isolation, and the offline enforcement gate."""

import importlib.util
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def launcher():
    path = Path(__file__).resolve().parents[2] / "run_session_baseline.py"
    spec = importlib.util.spec_from_file_location("session_baseline_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("scope", ["new", "full"])
def test_list_has_exact_existing_absolute_selection(launcher, monkeypatch, capsys, scope):
    monkeypatch.setattr(sys, "argv", ["baseline", "--scope", scope, "--list"])
    run = MagicMock()
    monkeypatch.setattr(pytest, "main", run)
    assert launcher.main() == 0
    paths = capsys.readouterr().out.splitlines()
    expected = [launcher.NEW_TESTS]
    if scope == "full":
        expected.extend(launcher.REGRESSION_TESTS)
    assert paths == [str(launcher.REPO_ROOT / path) for path in expected]
    assert all(Path(path).is_absolute() and Path(path).exists() for path in paths)
    run.assert_not_called()


@pytest.mark.parametrize("error", [False, True])
@pytest.mark.parametrize("separator", [[], ["--"]], ids=["poetry-forwarding", "explicit-separator"])
def test_execution_isolates_then_restores_environment_and_import_path(launcher, monkeypatch, error, separator):
    monkeypatch.setattr(sys, "argv", ["baseline", "--scope", "new", *separator, "--collect-only"])
    before_env = dict(os.environ)
    before_path = list(sys.path)
    observed = []

    def run(args, plugins):
        sandbox = Path(os.environ["HOME"])
        observed.append(sandbox)
        assert sandbox.is_dir()
        assert str(sandbox) != before_env["HOME"]
        assert os.environ["SIADA_REMOTE_MODEL_CONFIG"] == "0"
        assert Path(os.environ["SIADA_CLI_LOG_DIR"]).parent == sandbox
        assert Path(os.environ["XDG_CACHE_HOME"]).parent == sandbox
        assert args[0] == str(launcher.REPO_ROOT / launcher.NEW_TESTS)
        assert args[-1] == "--collect-only"
        assert len(plugins) == 1 and isinstance(plugins[0], launcher.OfflineGuard)
        if error:
            raise RuntimeError("synthetic pytest startup failure")
        return pytest.ExitCode.OK

    monkeypatch.setattr(pytest, "main", run)
    if error:
        with pytest.raises(RuntimeError, match="synthetic pytest startup failure"):
            launcher.main()
    else:
        assert launcher.main() == 0
    assert len(observed) == 1 and not observed[0].exists()
    assert dict(os.environ) == before_env
    assert sys.path == before_path


def test_missing_selected_test_is_not_silently_skipped(launcher, monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["baseline", "--scope", "new"])
    run = MagicMock()
    monkeypatch.setattr(pytest, "main", run)
    with pytest.raises(SystemExit) as error:
        launcher.main()
    assert error.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize("connect", ["connect", "connect_ex", "create_connection"])
def test_swallowed_network_attempt_still_fails_baseline(launcher, connect):
    guard = launcher.OfflineGuard()
    session = SimpleNamespace(exitstatus=pytest.ExitCode.OK)
    original_connect = socket.socket.connect
    original_create = socket.create_connection
    guard.pytest_sessionstart(session)
    try:
        if connect == "create_connection":
            with pytest.raises(RuntimeError, match="prohibited"):
                socket.create_connection(("127.0.0.1", 9))
        else:
            with socket.socket() as sock:
                with pytest.raises(RuntimeError, match="prohibited"):
                    getattr(sock, connect)(("127.0.0.1", 9))
    finally:
        guard.pytest_sessionfinish(session, 0)
    assert guard.attempts == 1
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert socket.socket.connect is original_connect
    assert socket.create_connection is original_create
    reporter = SimpleNamespace(write_sep=MagicMock())
    guard.pytest_terminal_summary(reporter)
    reporter.write_sep.assert_called_once_with("!", "Blocked 1 unexpected network attempts", red=True)