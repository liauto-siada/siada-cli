"""Command interactivity depends on ACP mode, not the parent's terminal."""

import shlex
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.tools.coder import cmd_runner


@pytest.mark.parametrize("system", ["Darwin", "Linux", "Windows"])
@pytest.mark.parametrize("is_tty", [False, True])
@pytest.mark.parametrize("acp_mode", [False, True])
@pytest.mark.parametrize("spawn_available", [False, True])
def test_command_routing_ignores_parent_tty(
    monkeypatch, tmp_path, system, is_tty, acp_mode, spawn_available,
):
    monkeypatch.setattr(cmd_runner.platform, "system", lambda: system)
    monkeypatch.setattr(cmd_runner.sys, "stdin", SimpleNamespace(isatty=lambda: is_tty))
    monkeypatch.setenv("SIADA_ACP_MODE", "1" if acp_mode else "0")
    monkeypatch.setattr(
        cmd_runner,
        "pexpect",
        SimpleNamespace(spawn=Mock()) if spawn_available else SimpleNamespace(),
    )
    traditional_runner = Mock(return_value=(0, "traditional"))
    acp_runner = Mock(return_value=(0, "acp"))
    subprocess_runner = Mock(return_value=(0, "subprocess"))
    monkeypatch.setattr(cmd_runner, "run_cmd_pexpect", traditional_runner)
    monkeypatch.setattr(cmd_runner, "run_cmd_pexpect_acp", acp_runner)
    monkeypatch.setattr(cmd_runner, "run_cmd_subprocess", subprocess_runner)

    uses_acp = system != "Windows" and acp_mode and spawn_available
    selected_runner = acp_runner if uses_acp else subprocess_runner
    expected_output = "acp" if uses_acp else "subprocess"

    assert cmd_runner.run_cmd_impl(
        "echo test", verbose=True, cwd=str(tmp_path), timeout=7,
    ) == (0, expected_output)

    selected_runner.assert_called_once_with("echo test", True, str(tmp_path), timeout=7)
    for runner in (traditional_runner, acp_runner, subprocess_runner):
        if runner is not selected_runner:
            runner.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Uses POSIX shell quoting.")
def test_non_acp_parent_tty_does_not_supply_subprocess_input(monkeypatch, tmp_path):
    monkeypatch.setenv("SIADA_ACP_MODE", "0")
    monkeypatch.setattr(cmd_runner.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    traditional_runner = Mock(side_effect=AssertionError("Must not take over the terminal"))
    monkeypatch.setattr(cmd_runner, "run_cmd_pexpect", traditional_runner)
    script = (
        "import sys; "
        "print('stdin_eof=' + str(sys.stdin.read() == '')); "
        "print('stdout_marker'); "
        "print('stderr_marker', file=sys.stderr); "
        "sys.exit(3)"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

    returncode, output = cmd_runner.run_cmd_impl(command, cwd=str(tmp_path), timeout=5)

    assert returncode == 3
    assert "stdin_eof=True" in output
    assert "stdout_marker" in output
    assert "stderr_marker" in output
    traditional_runner.assert_not_called()