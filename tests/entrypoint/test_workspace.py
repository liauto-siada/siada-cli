"""Regression coverage for launch-directory workspace selection."""

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
def test_launcher_defaults_to_launch_directory(project_dirs, git_marker):
    project, launch_dir, _ = project_dirs
    if git_marker != "directory":
        (project / ".git").rmdir()
        if git_marker == "file":
            (project / ".git").write_text("gitdir: /synthetic/worktree\n")

    workspace, git_root = launcher._resolve_workspace()

    assert workspace == str(launch_dir)
    assert git_root == (str(project) if git_marker else None)
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("in_repository", [True, False])
def test_backend_defaults_to_launch_directory(project_dirs, in_repository):
    project, launch_dir, _ = project_dirs

    workspace = siadahub.get_workspace(None, str(project) if in_repository else None)

    assert workspace == str(launch_dir)
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("relative", [True, False])
@pytest.mark.parametrize("option", ["--workspace", "-w"])
def test_explicit_workspace_overrides_launch_directory(project_dirs, monkeypatch, relative, option):
    _, launch_dir, other_dir = project_dirs
    workspace_arg = "../../../other project" if relative else str(other_dir)
    monkeypatch.setattr("sys.argv", ["siada-cli", option, workspace_arg])

    workspace, git_root = launcher._resolve_workspace()

    assert workspace == str(other_dir)
    assert git_root is None
    assert Path.cwd() == launch_dir
    assert siadahub.get_workspace(workspace_arg, git_root) == workspace
    assert Path.cwd() == other_dir


def test_explicit_repository_workspace_preserves_env_search_root(project_dirs, monkeypatch):
    project, launch_dir, _ = project_dirs
    monkeypatch.setattr("sys.argv", ["siada-cli", "--workspace=."])

    workspace, git_root = launcher._resolve_workspace()

    assert workspace == str(launch_dir)
    assert git_root == str(project)


@pytest.mark.parametrize("workspace_arg", ["missing", "not-a-directory"])
def test_backend_rejects_invalid_workspace(project_dirs, workspace_arg):
    project, launch_dir, _ = project_dirs
    if workspace_arg == "not-a-directory":
        (launch_dir / workspace_arg).write_text("synthetic fixture")

    with pytest.raises(SystemExit) as error:
        siadahub.get_workspace(workspace_arg, str(project))

    assert error.value.code == 1
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("prompt", [None, "Inspect the project"])
@pytest.mark.parametrize("option", ["--workspace", "-w"])
def test_backend_parser_accepts_workspace(project_dirs, prompt, option):
    project, launch_dir, _ = project_dirs
    argv = [option, "."]
    if prompt:
        argv.extend(["--prompt", prompt])

    with patch.object(siadahub, "load_dotenv_files", return_value=[]) as load_env, \
            patch.object(siadahub, "toggle_console_output"):
        args, git_root, workspace_arg, _, interactive = siadahub._parse_args_and_setup_environment(argv)

    assert args.workspace == "."
    assert workspace_arg == "."
    assert git_root == str(project)
    assert interactive is (prompt is None)
    load_env.assert_called_once_with(str(project), args.env_file, args.encoding)
    assert Path.cwd() == launch_dir


def test_workspace_environment_override_is_consistent(project_dirs, monkeypatch):
    _, launch_dir, other_dir = project_dirs
    monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))

    workspace, git_root = launcher._resolve_workspace()
    with patch.object(siadahub, "load_dotenv_files", return_value=[]), \
            patch.object(siadahub, "toggle_console_output"):
        args, backend_git_root, workspace_arg, _, _ = siadahub._parse_args_and_setup_environment([])

    assert workspace == args.workspace == workspace_arg == str(other_dir)
    assert git_root is backend_git_root is None
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("option", ["--workspace", "-w"])
def test_cli_workspace_takes_precedence_over_environment(project_dirs, monkeypatch, option):
    project, launch_dir, other_dir = project_dirs
    monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
    monkeypatch.setattr("sys.argv", ["siada-cli", option, "."])

    assert launcher._resolve_workspace() == (str(launch_dir), str(project))
    with patch.object(siadahub, "load_dotenv_files", return_value=[]), \
            patch.object(siadahub, "toggle_console_output"):
        args, git_root, workspace_arg, _, _ = siadahub._parse_args_and_setup_environment([option, "."])
    assert args.workspace == workspace_arg == "."
    assert git_root == str(project)


@pytest.mark.parametrize("option", ["--workspace", "-w"])
@pytest.mark.parametrize("environment_override", [False, True])
@pytest.mark.parametrize("prompt", [None, "Inspect the project"])
def test_bare_workspace_option_uses_current_directory(
    project_dirs, monkeypatch, option, environment_override, prompt
):
    project, launch_dir, other_dir = project_dirs
    if environment_override:
        monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
    argv = [option]
    if prompt:
        argv.extend(["--prompt", prompt])
    monkeypatch.setattr("sys.argv", ["siada-cli", *argv])

    workspace, git_root = launcher._resolve_workspace()
    launcher_args = launcher._parse_args(git_root)
    with patch.object(siadahub, "load_dotenv_files", return_value=[]) as load_env, \
            patch.object(siadahub, "toggle_console_output"):
        args, backend_git_root, workspace_arg, _, interactive = siadahub._parse_args_and_setup_environment(argv)

    assert workspace == str(launch_dir)
    assert launcher_args.workspace == args.workspace == workspace_arg == "."
    assert git_root == backend_git_root == str(project)
    assert args.prompt == prompt
    assert interactive is (prompt is None)
    load_env.assert_called_once_with(str(project), args.env_file, args.encoding)
    assert siadahub.get_workspace(workspace_arg, backend_git_root) == str(launch_dir)
    assert Path.cwd() == launch_dir


def test_ui_command_receives_absolute_workspace(project_dirs, tmp_path, monkeypatch):
    _, _, other_dir = project_dirs
    monkeypatch.setattr("sys.argv", ["siada-cli", "--workspace", "../../../other project"])
    monkeypatch.setattr("sys.gettrace", lambda: None)
    monkeypatch.delenv("DEBUGPY_LAUNCHER_PORT", raising=False)
    monkeypatch.delenv("PYDEVD_LOAD_VALUES_ASYNC", raising=False)
    ui_dir = tmp_path / "ui"
    (ui_dir / "bundle").mkdir(parents=True)
    (ui_dir / "bundle" / "siada-ui.js").write_text("// Synthetic UI bundle.\n")
    workspace, _ = launcher._resolve_workspace()
    ui_launcher = launcher.UILauncher({"workspace": workspace})
    monkeypatch.setattr(ui_launcher, "_find_local_node", lambda: "node")

    command = ui_launcher._build_ui_command(ui_dir)

    assert command[-1] == str(other_dir)
    assert command[:2] == ["node", str(ui_dir / "bundle" / "siada-ui.js")]
    backend_args = shlex.split(command[command.index("--siada-args") + 1])
    assert backend_args == ["--workspace", str(other_dir)]


@pytest.mark.parametrize(
    "selection", ["default", "cli-relative", "env-relative", "cli-over-env", "bare", "bare-over-env"]
)
@pytest.mark.parametrize("option", ["--workspace", "-w"])
def test_ui_forwarding_preserves_workspace_in_backend(project_dirs, monkeypatch, selection, option):
    _, launch_dir, other_dir = project_dirs
    if selection == "cli-relative":
        monkeypatch.setattr("sys.argv", ["siada-cli", option, "../../../other project"])
    elif selection == "env-relative":
        monkeypatch.setenv("SIADA_WORKSPACE", "../../../other project")
    elif selection == "cli-over-env":
        monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
        monkeypatch.setattr("sys.argv", ["siada-cli", option, "."])
    elif selection in {"bare", "bare-over-env"}:
        if selection == "bare-over-env":
            monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
        monkeypatch.setattr("sys.argv", ["siada-cli", option])

    expected_dir = other_dir if selection in {"cli-relative", "env-relative"} else launch_dir
    workspace, _ = launcher._resolve_workspace()
    ui_launcher = launcher.UILauncher({"workspace": workspace, "args": SimpleNamespace(agent="coder")})
    backend_args = shlex.split(" ".join(ui_launcher._build_siada_args()))
    monkeypatch.chdir(workspace)

    with patch.object(siadahub, "load_dotenv_files", return_value=[]), \
            patch.object(siadahub, "toggle_console_output"):
        args, git_root, workspace_arg, _, _ = siadahub._parse_args_and_setup_environment(backend_args)

    assert args.agent == "coder"
    assert args.workspace == workspace_arg == str(expected_dir)
    assert siadahub.get_workspace(workspace_arg, git_root) == str(expected_dir)
    assert Path.cwd() == expected_dir


@pytest.mark.parametrize("option", [None, "--workspace", "-w"])
def test_launcher_main_passes_workspace_to_ui(project_dirs, monkeypatch, option):
    _, launch_dir, other_dir = project_dirs
    expected_dir = other_dir if option else launch_dir
    if option:
        monkeypatch.setattr("sys.argv", ["siada-cli", option, str(other_dir)])

    with patch.object(launcher, "_run_first_time_setup_if_needed"), \
            patch.object(launcher, "remove_console_handler"), \
            patch.object(launcher, "_launch_ui", return_value=0) as launch_ui:
        result = launcher.main()

    assert result == 0
    assert launch_ui.call_args.args[0] == str(expected_dir)
    assert launch_ui.call_args.args[1].workspace == (str(other_dir) if option else None)
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("option", ["--workspace", "-w"])
def test_launcher_main_passes_current_directory_for_bare_workspace(project_dirs, monkeypatch, option):
    _, launch_dir, other_dir = project_dirs
    monkeypatch.setenv("SIADA_WORKSPACE", str(other_dir))
    monkeypatch.setattr("sys.argv", ["siada-cli", option])

    with patch.object(launcher, "_run_first_time_setup_if_needed"), \
            patch.object(launcher, "remove_console_handler"), \
            patch.object(launcher, "_launch_ui", return_value=0) as launch_ui:
        result = launcher.main()

    assert result == 0
    assert launch_ui.call_args.args[0] == str(launch_dir)
    assert launch_ui.call_args.args[1].workspace == "."
    assert Path.cwd() == launch_dir


@pytest.mark.parametrize("entrypoint", ["launcher", "backend"])
@pytest.mark.parametrize("origin", ["launch_directory", "repository_root", "missing"])
def test_resume_check_uses_launch_directory(project_dirs, entrypoint, origin):
    project, launch_dir, _ = project_dirs
    args = SimpleNamespace(resume="synthetic-session")
    io = Mock()
    origin_root = project if origin == "repository_root" else launch_dir
    session_info = None if origin == "missing" else SimpleNamespace(
        project_root=str(origin_root), session_id=args.resume
    )

    with patch("siada.support.resume_service.ResumeService") as resume_service, \
            patch.object(siadahub, "_ensure_agents_ready"):
        resume_service.return_value.get_session_info.return_value = session_info
        if entrypoint == "launcher":
            workspace, _ = launcher._resolve_workspace()
            result = launcher._check_resume_workspace(workspace, args)
            success = 0
        else:
            result = siadahub._check_resume_workspace_early(args, str(project), None, io)
            success = None

    resume_service.assert_called_once_with(str(launch_dir))
    resume_service.return_value.get_session_info.assert_called_once_with(args.resume)
    assert result == (success if origin == "launch_directory" else 1)
    assert Path.cwd() == launch_dir


def test_resume_check_respects_relative_workspace_without_chdir(project_dirs):
    project, launch_dir, other_dir = project_dirs
    args = SimpleNamespace(resume="")
    session_info = SimpleNamespace(project_root=str(other_dir), session_id="synthetic-session")

    with patch("siada.support.resume_service.ResumeService") as resume_service, \
            patch.object(siadahub, "_ensure_agents_ready"):
        resume_service.return_value.get_session_info.return_value = session_info
        result = siadahub._check_resume_workspace_early(
            args, str(project), "../../../other project", Mock()
        )

    assert result is None
    resume_service.assert_called_once_with(str(other_dir))
    resume_service.return_value.get_session_info.assert_called_once_with("latest")
    assert Path.cwd() == launch_dir