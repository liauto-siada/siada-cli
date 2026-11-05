"""Ctrl+C in non-interactive mode must not surface a launcher traceback.

``siada-cli --prompt`` delegates to ``python -m siada.entrypoint.siadahub`` in
a child process. Both processes share the terminal's foreground process group,
so the backend owns the Ctrl+C shutdown; the launcher must wait for it instead
of dying with ``KeyboardInterrupt`` from ``subprocess.run()``.
"""

import subprocess
import sys
from unittest.mock import Mock

import pytest

from siada.entrypoint import launch_ui_with_acp as launcher


@pytest.fixture
def backend_argv(monkeypatch):
    argv = ["--prompt", "hello"]
    monkeypatch.setattr(sys, "argv", ["siada-cli", *argv])
    return argv


def _patch_popen(monkeypatch, proc):
    popen = Mock(return_value=proc)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    return popen


def test_backend_returns_child_status_when_not_interrupted(backend_argv, monkeypatch):
    proc = Mock()
    proc.wait.return_value = 0
    popen = _patch_popen(monkeypatch, proc)

    assert launcher._run_backend() == 0
    assert popen.call_args.args[0] == [
        sys.executable, "-m", "siada.entrypoint.siadahub", *backend_argv
    ]
    proc.terminate.assert_not_called()
    proc.kill.assert_not_called()


def test_interrupt_lets_backend_finish_its_own_shutdown(backend_argv, monkeypatch):
    proc = Mock()
    # First wait is interrupted; the backend then exits with 130 on its own.
    proc.wait.side_effect = [KeyboardInterrupt(), 130]
    proc.returncode = 130
    _patch_popen(monkeypatch, proc)

    assert launcher._run_backend() == 130
    proc.terminate.assert_not_called()
    proc.kill.assert_not_called()


def test_interrupt_escalates_when_backend_keeps_running(backend_argv, monkeypatch):
    proc = Mock()
    proc.wait.side_effect = [
        KeyboardInterrupt(),
        subprocess.TimeoutExpired("backend", launcher._BACKEND_INTERRUPT_GRACE_SECONDS),
        None,
    ]
    proc.poll.return_value = None
    _patch_popen(monkeypatch, proc)

    assert launcher._run_backend() == 130
    proc.terminate.assert_called_once()
    proc.kill.assert_not_called()


def test_second_interrupt_skips_the_grace_period_and_kills(backend_argv, monkeypatch):
    proc = Mock()
    proc.wait.side_effect = [
        KeyboardInterrupt(),
        KeyboardInterrupt(),
        subprocess.TimeoutExpired("backend", launcher._BACKEND_TERMINATE_GRACE_SECONDS),
        None,
    ]
    proc.poll.return_value = None
    _patch_popen(monkeypatch, proc)

    assert launcher._run_backend() == 130
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


def test_unexpected_wait_error_cleans_up_child_before_reraising(backend_argv, monkeypatch):
    proc = Mock()
    proc.wait.side_effect = [OSError("wait failed"), None]
    proc.poll.return_value = None
    _patch_popen(monkeypatch, proc)

    with pytest.raises(OSError):
        launcher._run_backend()
    proc.terminate.assert_called_once()
