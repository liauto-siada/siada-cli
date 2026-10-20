"""Console diagnostics for resume validation before the UI starts."""

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from siada.entrypoint import launch_ui_with_acp as launcher


@pytest.fixture
def session_lookup(monkeypatch):
    """Isolate session storage and its model dependencies from launcher tests."""
    state = SimpleNamespace(info=None, error=None, calls=[])

    class ResumeService:
        def __init__(self, workspace):
            self.workspace = workspace

        def get_session_info(self, identifier):
            state.calls.append((self.workspace, identifier))
            if state.error:
                raise state.error
            return state.info

    module = ModuleType("siada.support.resume_service")
    module.ResumeService = ResumeService
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return state


def test_workspace_mismatch_reports_to_stderr_before_ui(
    monkeypatch, capsys, session_lookup
):
    session_lookup.info = SimpleNamespace(
        project_root="/projects/original", session_id="saved-session-id"
    )
    args = SimpleNamespace(resume="saved")
    monkeypatch.setattr(sys, "argv", ["siada-cli", "--resume", "saved"])
    monkeypatch.setattr(launcher, "_run_first_time_setup_if_needed", lambda: None)
    monkeypatch.setattr(
        launcher, "_resolve_workspace", lambda: ("/projects/current", None)
    )
    monkeypatch.setattr(launcher, "_parse_args", lambda git_root: args)
    monkeypatch.setattr(
        launcher, "_launch_ui", lambda *args: pytest.fail("UI must not start")
    )

    assert launcher.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Session belongs to workspace: /projects/original\n"
        "To resume this session, run:  cd /projects/original "
        "&& siada-cli --resume saved-session-id\n"
    )


@pytest.mark.parametrize("identifier", ["missing-session", ""])
def test_missing_session_reports_to_stderr(capsys, session_lookup, identifier):
    resolved_id = identifier or "latest"
    assert launcher._check_resume_workspace(
        "/projects/current", SimpleNamespace(resume=identifier)
    ) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"Error: Session not found: {resolved_id}\n"
    assert session_lookup.calls == [("/projects/current", resolved_id)]


@pytest.mark.parametrize(
    "origin_root", ["/projects/current", "/projects/current/.", "", None, "Unknown"]
)
def test_compatible_workspace_has_no_console_error(
    capsys, session_lookup, origin_root
):
    session_lookup.info = SimpleNamespace(
        project_root=origin_root, session_id="saved-session-id"
    )
    assert launcher._check_resume_workspace(
        "/projects/current", SimpleNamespace(resume="saved")
    ) == 0
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("args", [SimpleNamespace(), SimpleNamespace(resume=None)])
def test_without_resume_skips_lookup(capsys, session_lookup, args):
    assert launcher._check_resume_workspace("/projects/current", args) == 0
    assert session_lookup.calls == []
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_lookup_failure_defers_to_backend(capsys, session_lookup):
    session_lookup.error = RuntimeError("storage unavailable")
    launcher.remove_console_handler()
    assert launcher._check_resume_workspace(
        "/projects/current", SimpleNamespace(resume="saved")
    ) == 0
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_launcher_subprocess_preserves_exit_code_and_diagnostic(tmp_path):
    """Exercise console-handler removal and process output with synthetic storage."""
    script = """
import sys
from types import ModuleType, SimpleNamespace
from siada.entrypoint import launch_ui_with_acp as launcher

module = ModuleType("siada.support.resume_service")
class ResumeService:
    def __init__(self, workspace):
        pass
    def get_session_info(self, identifier):
        return SimpleNamespace(project_root="/projects/original", session_id="saved-id")
module.ResumeService = ResumeService
sys.modules[module.__name__] = module
sys.argv = ["siada-cli", "--resume", "saved-id"]
launcher._run_first_time_setup_if_needed = lambda: None
launcher._resolve_workspace = lambda: ("/projects/current", None)
launcher._parse_args = lambda root: SimpleNamespace(resume="saved-id")
launcher._launch_ui = lambda *args: 99
sys.exit(launcher.main())
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(launcher.__file__).resolve().parents[2])
    env["SIADA_CLI_LOG_DIR"] = str(tmp_path / "logs")
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Session belongs to workspace: /projects/original\n"
        "To resume this session, run:  cd /projects/original "
        "&& siada-cli --resume saved-id\n"
    )