"""Offline coverage for launch-directory defaults and explicit workspaces."""

import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from siada.entrypoint import launch_ui_with_acp as launcher
from siada.entrypoint import siadahub


@pytest.fixture
def project_dirs(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    launch_dir = project / "src" / "package"
    launch_dir.mkdir(parents=True)
    other_dir = tmp_path / "other project"
    other_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setattr("sys.argv", ["siada-cli"])
    monkeypatch.delenv("SIADA_WORKSPACE", raising=False)
    return project.resolve(), launch_dir.resolve(), other_dir.resolve()


@pytest.mark.parametrize("git_marker", ["directory", "file", None])
def test_launch_directory_default(project_dirs, git_marker):
    project, launch_dir, _ = project_dirs
    if git_marker != "directory":
        (project / ".git").rmdir()
        if git_marker == "file":
            (project / ".git").write_text("gitdir: /synthetic/worktree\n")
    workspace, git_root = launcher._resolve_workspace()
    assert workspace == str(launch_dir)
    assert git_root == (str(project) if git_marker else None)
    assert siadahub.get_workspace(None, git_root) == workspace
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("option", ["--workspace", "-w"])
@pytest.mark.parametrize(
    "selection", ["default", "cli-relative", "cli-absolute", "env-relative", "cli-over-env", "bare", "bare-over-env"]
)
@pytest.mark.parametrize("prompt", [None, "Inspect the project"])
def test_workspace_precedence_and_backend_forwarding(
    project_dirs, monkeypatch, option, selection, prompt
):
    project, launch_dir, other_dir = project_dirs
    argv = []
    if selection == "cli-relative":
        argv = [option, "../../../other project"]
    elif selection == "cli-absolute":
        argv = [option, str(other_dir)]
    elif selection == "env-relative":
        monkeypatch.setenv("SIADA_WORKSPACE", "../../../other project")
    elif selection == "cli-over-env":
        monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
        argv = [option, "."]
    elif selection in {"bare", "bare-over-env"}:
        if selection == "bare-over-env":
            monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
        argv = [option]
    if prompt:
        argv.extend(["--prompt", prompt])
    monkeypatch.setattr("sys.argv", ["siada-cli", *argv])
    expected_dir = other_dir if selection in {"cli-relative", "cli-absolute", "env-relative"} else launch_dir
    workspace, git_root = launcher._resolve_workspace()
    assert workspace == str(expected_dir)
    assert git_root == (str(project) if expected_dir == launch_dir else None)

    with patch.object(siadahub, "load_dotenv_files", return_value=[]) as load_env, \
            patch.object(siadahub, "toggle_console_output"):
        args, backend_root, workspace_arg, _, interactive = siadahub._parse_args_and_setup_environment(argv)
    assert args.prompt == prompt
    assert interactive is (prompt is None)
    assert backend_root == git_root
    load_env.assert_called_once_with(git_root, args.env_file, args.encoding)
    assert siadahub.get_workspace(workspace_arg, backend_root) == workspace

    ui = launcher.UILauncher({"workspace": workspace, "args": SimpleNamespace(agent="coder")})
    forwarded = shlex.split(" ".join(ui._build_siada_args()))
    with patch.object(siadahub, "load_dotenv_files", return_value=[]), \
            patch.object(siadahub, "toggle_console_output"):
        forwarded_args, _, forwarded_workspace, _, _ = siadahub._parse_args_and_setup_environment(forwarded)
    assert forwarded_args.agent == "coder"
    assert forwarded_args.workspace == forwarded_workspace == workspace
    assert Path.cwd() == expected_dir


@pytest.mark.parametrize("workspace_arg", ["missing", "not-a-directory"])
def test_invalid_workspace_is_rejected(project_dirs, workspace_arg):
    project, launch_dir, _ = project_dirs
    if workspace_arg == "not-a-directory":
        (launch_dir / workspace_arg).write_text("synthetic fixture")
    with pytest.raises(SystemExit) as error:
        siadahub.get_workspace(workspace_arg, str(project))
    assert error.value.code == 1
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("entrypoint", ["launcher", "backend"])
@pytest.mark.parametrize("origin", ["launch_directory", "repository_root", "missing"])
def test_resume_uses_launch_directory(project_dirs, entrypoint, origin):
    project, launch_dir, _ = project_dirs
    args = SimpleNamespace(resume="synthetic-session")
    origin_root = project if origin == "repository_root" else launch_dir
    session_info = None if origin == "missing" else SimpleNamespace(
        project_root=str(origin_root), session_id=args.resume
    )
    with patch("siada.support.resume_service.ResumeService") as service, \
            patch.object(siadahub, "_ensure_agents_ready"):
        service.return_value.get_session_info.return_value = session_info
        if entrypoint == "launcher":
            result = launcher._check_resume_workspace(str(launch_dir), args)
            success = 0
        else:
            result = siadahub._check_resume_workspace_early(args, str(project), None, Mock())
            success = None
    service.assert_called_once_with(str(launch_dir))
    assert result == (success if origin == "launch_directory" else 1)
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("mode", ["default", "env", "cli", "bare", "prompt"])
def test_main_dispatch_keeps_workspace_and_arguments(project_dirs, monkeypatch, mode):
    _, launch_dir, other_dir = project_dirs
    argv = []
    if mode in {"env", "bare"}:
        monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
    if mode == "bare":
        argv = ["-w"]
    elif mode == "cli":
        argv = ["--workspace", str(other_dir)]
    elif mode == "prompt":
        argv = ["-w", "--prompt", "Inspect the current directory"]
    monkeypatch.setattr("sys.argv", ["siada-cli", *argv])
    monkeypatch.setattr(launcher, "remove_console_handler", Mock())
    monkeypatch.setattr("siada.foundation.logging.redirect_agents_logger", Mock())
    monkeypatch.setattr(launcher, "_run_first_time_setup_if_needed", Mock())
    launch_ui = Mock(return_value=11)
    run_backend = Mock(return_value=17)
    monkeypatch.setattr(launcher, "_launch_ui", launch_ui)
    monkeypatch.setattr(launcher, "_run_backend", run_backend)

    assert launcher.main() == (17 if mode == "prompt" else 11)
    if mode == "prompt":
        run_backend.assert_called_once_with()
        launch_ui.assert_not_called()
    else:
        expected_dir = other_dir if mode in {"env", "cli"} else launch_dir
        assert launch_ui.call_args.args[0] == str(expected_dir)
        run_backend.assert_not_called()
    assert launcher.sys.argv == ["siada-cli", *argv]
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("args", [None, SimpleNamespace()])
def test_ui_command_forwards_workspace_without_other_options(project_dirs, tmp_path, monkeypatch, args):
    _, _, other_dir = project_dirs
    ui_dir = tmp_path / "ui"
    (ui_dir / "bundle").mkdir(parents=True)
    (ui_dir / "bundle" / "siada-ui.js").write_text("// synthetic UI fixture\n")
    monkeypatch.setattr(launcher.UILauncher, "_find_local_node", lambda _: "synthetic-node")
    command = launcher.UILauncher({"workspace": str(other_dir), "args": args})._build_ui_command(ui_dir)
    assert command[-1] == str(other_dir)
    assert shlex.split(command[command.index("--siada-args") + 1]) == ["--workspace", str(other_dir)]