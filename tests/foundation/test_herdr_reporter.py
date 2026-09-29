"""Tests for the Herdr state reporter.

The reporter is the whole contract with Herdr: it must be a no-op outside a
Herdr pane, must never let a failure reach the agent, and must keep sequence
numbers strictly increasing so a slow report cannot overwrite a newer state.

The last two tests exercise the real dispatch path (background worker thread,
subprocess, `atexit` release) against a stub `herdr` CLI on disk, so the
command line and the lifecycle sequence are verified without a Herdr install.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from siada.foundation import herdr_reporter

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Recorder:
    """Capture dispatched argv lists instead of spawning the herdr CLI."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))


def _env(**overrides):
    env = {
        "HERDR_ENV": "1",
        "HERDR_PANE_ID": "w1:p1",
        "HERDR_BIN_PATH": "/opt/herdr",
    }
    env.update(overrides)
    return env


def _flag(argv, name):
    return argv[argv.index(name) + 1]


def test_no_reports_outside_herdr():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env={}, runner=recorder)

    assert reporter.available() is False
    reporter.report_state(herdr_reporter.STATE_WORKING)
    reporter.release()

    assert recorder.calls == []
    assert reporter.has_reported() is False


def test_herdr_env_without_pane_id_is_not_a_herdr_session():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env={"HERDR_ENV": "1"}, runner=recorder)

    reporter.report_state(herdr_reporter.STATE_WORKING)

    assert recorder.calls == []


def test_report_agent_command_line():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    reporter.report_state(herdr_reporter.STATE_WORKING, session_id="sess-1")

    argv = recorder.calls[0]
    assert argv == [
        "/opt/herdr",
        "pane",
        "report-agent",
        "w1:p1",
        "--source",
        "custom:siada",
        "--agent",
        "siada",
        "--state",
        "working",
        "--seq",
        _flag(argv, "--seq"),
        "--agent-session-id",
        "sess-1",
    ]
    assert _flag(argv, "--seq").isdigit()


def test_blocked_report_carries_the_prompt_as_message():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    reporter.report_state(herdr_reporter.STATE_BLOCKED, message="Password:")

    argv = recorder.calls[0]
    assert _flag(argv, "--state") == "blocked"
    assert _flag(argv, "--message") == "Password:"
    assert "--agent-session-id" not in argv


def test_release_agent_command_line():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    reporter.release()

    argv = recorder.calls[0]
    assert argv[:4] == ["/opt/herdr", "pane", "release-agent", "w1:p1"]
    assert _flag(argv, "--source") == "custom:siada"
    assert _flag(argv, "--agent") == "siada"


def test_sequence_numbers_are_strictly_increasing():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    for _ in range(5):
        reporter.report_state(herdr_reporter.STATE_WORKING)

    seqs = [int(_flag(call, "--seq")) for call in recorder.calls]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_unknown_state_is_ignored():
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    reporter.report_state("sleeping")

    assert recorder.calls == []


def test_runner_failure_never_reaches_the_agent():
    def boom(argv):
        raise OSError("herdr is gone")

    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=boom)

    reporter.report_state(herdr_reporter.STATE_WORKING)
    reporter.release()

    assert reporter.has_reported() is True


def test_bin_path_falls_back_to_path_lookup():
    reporter = herdr_reporter.HerdrReporter(
        env={"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}
    )

    assert reporter.bin_path() == "herdr"


def test_exit_release_hands_back_authority(monkeypatch):
    commands = []
    monkeypatch.setattr(
        herdr_reporter, "_run_command", lambda argv, **kwargs: commands.append(argv)
    )
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=lambda argv: None)
    monkeypatch.setattr(herdr_reporter, "reporter", reporter)

    # Nothing was reported yet, so exiting must not talk to herdr at all.
    herdr_reporter._release_at_exit()
    assert commands == []

    reporter.report_state(herdr_reporter.STATE_WORKING)
    herdr_reporter._release_at_exit()

    assert len(commands) == 1
    assert commands[0][1:3] == ["pane", "release-agent"]


def test_module_helpers_delegate_to_the_process_reporter(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(
        herdr_reporter,
        "reporter",
        herdr_reporter.HerdrReporter(env=_env(), runner=recorder),
    )

    assert herdr_reporter.available() is True
    herdr_reporter.report_state(herdr_reporter.STATE_IDLE, session_id="sess-9")
    herdr_reporter.release()

    assert _flag(recorder.calls[0], "--state") == "idle"
    assert _flag(recorder.calls[0], "--agent-session-id") == "sess-9"
    assert recorder.calls[1][2] == "release-agent"


@pytest.mark.parametrize(
    "state",
    [
        herdr_reporter.STATE_IDLE,
        herdr_reporter.STATE_WORKING,
        herdr_reporter.STATE_BLOCKED,
    ],
)
def test_supported_states_are_dispatched(state):
    recorder = _Recorder()
    reporter = herdr_reporter.HerdrReporter(env=_env(), runner=recorder)

    reporter.report_state(state)

    assert _flag(recorder.calls[0], "--state") == state


def _write_stub_herdr(directory: Path, log: Path) -> Path:
    """Write a fake `herdr` that appends every invocation to `log`."""
    stub = directory / "herdr"
    stub.write_text('#!/bin/sh\necho "$@" >> "' + str(log) + '"\n')
    stub.chmod(0o755)
    return stub


def _wait_for_lines(log: Path, expected: int, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists() and len(log.read_text().splitlines()) >= expected:
            break
        time.sleep(0.05)
    return log.read_text().splitlines() if log.exists() else []


def test_reports_reach_the_herdr_cli_through_the_worker(tmp_path):
    log = tmp_path / "calls.log"
    stub = _write_stub_herdr(tmp_path, log)
    reporter = herdr_reporter.HerdrReporter(
        env={
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": "w9:p9",
            "HERDR_BIN_PATH": str(stub),
        }
    )

    reporter.report_state(herdr_reporter.STATE_WORKING)
    reporter.report_state(herdr_reporter.STATE_BLOCKED, message="Password:")
    reporter.report_state(herdr_reporter.STATE_IDLE)
    reporter.release()

    lines = _wait_for_lines(log, expected=4)

    assert len(lines) == 4
    assert lines[0].split()[:3] == ["pane", "report-agent", "w9:p9"]
    assert "--state working" in lines[0]
    assert "--state blocked" in lines[1]
    assert "--message Password:" in lines[1]
    assert "--state idle" in lines[2]
    assert lines[3].split()[:3] == ["pane", "release-agent", "w9:p9"]
    assert "--source custom:siada" in lines[3]


def test_process_exit_releases_the_pane(tmp_path):
    log = tmp_path / "calls.log"
    stub = _write_stub_herdr(tmp_path, log)
    env = dict(
        os.environ,
        HERDR_ENV="1",
        HERDR_PANE_ID="w7:p7",
        HERDR_BIN_PATH=str(stub),
        PYTHONPATH=str(REPO_ROOT),
    )
    script = (
        "from siada.foundation import herdr_reporter as r;"
        "r.report_state(r.STATE_WORKING, session_id='sess-1')"
    )

    subprocess.run(
        [sys.executable, "-c", script], env=env, check=True, timeout=60
    )

    lines = _wait_for_lines(log, expected=2)
    assert len(lines) == 2
    assert "--state working" in lines[0]
    assert "--agent-session-id sess-1" in lines[0]
    assert "release-agent" in lines[1]
