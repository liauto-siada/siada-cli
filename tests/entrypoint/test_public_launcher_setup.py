"""Public-launcher startup guarantees for ``siada-cli``'s console entry point.

``siada.entrypoint.launch_ui_with_acp`` is the ``siada-cli`` entry point.  Two
host-level side effects used to leak out of its one-time version setup:

* the setup killed *every* ``siada.agent_hub.proactive`` process found in the
  process table (then respawned one) before ``--no-daemon`` was even parsed;
* it downloaded nvm/Node.js into the venv even when a usable ``node`` was
  already on ``PATH``.

Plain ``--version`` / ``--help`` / ``-h`` queries also ran that whole startup
path first.  These tests pin the public contract instead:

* the one-time setup only checks the UI bundle and records a version marker;
* background process management stays with ``DaemonManager`` / the explicit
  ``--daemon-*`` backend commands — the launcher never scans or signals other
  processes;
* Node.js is resolved from the venv install layout, then from ``PATH``; a
  missing Node fails with the launcher's install guidance, never a download;
* ``--version`` / ``--help`` / ``-h`` exit during argument parsing — before the
  one-time setup, the backend and the UI — and ``-V`` is not part of the public
  parser (which defines ``-v``/``--version``);
* the normal path (one-time setup, then UI launch with workspace /
  ``--siada-module`` passthrough, or backend delegation) is preserved.

Every test runs against a throwaway ``HOME`` — installed before the launcher
module is imported and re-pointed per test — and keeps the metadata, file,
subprocess, process-table and daemon boundaries mocked, so nothing here can
reach real user state or spawn a real process.
"""

from __future__ import annotations

import importlib.metadata
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# HOME isolation must happen before the entry point is imported: nothing in the
# module graph may resolve the real ~/.siada-cli while this file is collected.
# ---------------------------------------------------------------------------
_ORIGINAL_HOME = os.environ.get("HOME")
_TEMP_HOME = tempfile.mkdtemp(prefix="siada-launcher-home-")
os.environ["HOME"] = _TEMP_HOME
os.environ.pop("NVM_DIR", None)

import siada  # noqa: E402
from siada.entrypoint import launch_ui_with_acp as launch  # noqa: E402
from siada.entrypoint.args_parser.args import get_parser  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_process_home_after_module():
    """Give the rest of the process its HOME back when this module is done."""
    yield
    import shutil

    shutil.rmtree(_TEMP_HOME, ignore_errors=True)
    if _ORIGINAL_HOME is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = _ORIGINAL_HOME


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point HOME (and ``Path.home()``) at a throwaway directory per test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("NVM_DIR", raising=False)
    # SIADA_HOME can be captured before this fixture redirects Path.home().
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(home / ".siada-cli" / "browser"))
    monkeypatch.delenv("SIADA_BROWSER_NODE", raising=False)
    # Keep the debug branches of ``_build_ui_command`` out of the way.
    monkeypatch.delenv("DEBUGPY_LAUNCHER_PORT", raising=False)
    monkeypatch.delenv("PYDEVD_LOAD_VALUES_ASYNC", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


class _SubprocessRecorder:
    """Fails the test if anything spawns a real process."""

    def __init__(self) -> None:
        self.runs: list[list[str]] = []
        self.popens: list[list[str]] = []

    def run(self, args, *a, **kwargs):
        self.runs.append(list(args) if isinstance(args, (list, tuple)) else [args])
        raise AssertionError(f"unexpected subprocess.run: {args!r}")

    def Popen(self, args, *a, **kwargs):  # noqa: N802 - mimics subprocess.Popen
        self.popens.append(list(args) if isinstance(args, (list, tuple)) else [args])
        raise AssertionError(f"unexpected subprocess.Popen: {args!r}")


class _ProcessTableRecorder:
    """Fake ``psutil`` whose process scan always fails the test."""

    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    def __init__(self) -> None:
        self.iter_calls: list[tuple] = []

    def process_iter(self, attrs=None):
        self.iter_calls.append(tuple(attrs or ()))
        raise AssertionError("the launcher scanned the process table")


class _DaemonBoundaryRecorder:
    """Fake ``DaemonManager``: constructing one fails the test."""

    def __init__(self) -> None:
        self.instantiations: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.instantiations.append((args, kwargs))
        raise AssertionError("the launcher tried to manage the proactive daemon")


@pytest.fixture
def host_side_effect_boundaries(monkeypatch):
    """Mock the subprocess/process-table/daemon boundaries.

    Anything the launcher does across those boundaries (spawning a process,
    scanning the process table, constructing a daemon manager) is recorded and
    turned into a test failure instead of touching the host.  Package metadata
    (``importlib.metadata``) is patched per test where it matters.
    """
    subprocess_recorder = _SubprocessRecorder()
    process_table = _ProcessTableRecorder()
    daemon_calls = _DaemonBoundaryRecorder()

    monkeypatch.setattr(launch.subprocess, "run", subprocess_recorder.run)
    monkeypatch.setattr(launch.subprocess, "Popen", subprocess_recorder.Popen)

    psutil_stub = ModuleType("psutil")
    psutil_stub.process_iter = process_table.process_iter
    psutil_stub.NoSuchProcess = _ProcessTableRecorder.NoSuchProcess
    psutil_stub.AccessDenied = _ProcessTableRecorder.AccessDenied
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)

    daemon_module = ModuleType("siada.agent_hub.proactive.daemon_manager")
    daemon_module.DaemonManager = daemon_calls
    proactive_package = ModuleType("siada.agent_hub.proactive")
    proactive_package.daemon_manager = daemon_module
    agent_hub_package = ModuleType("siada.agent_hub")
    agent_hub_package.proactive = proactive_package
    monkeypatch.setitem(sys.modules, "siada.agent_hub", agent_hub_package)
    monkeypatch.setitem(sys.modules, "siada.agent_hub.proactive", proactive_package)
    monkeypatch.setitem(
        sys.modules, "siada.agent_hub.proactive.daemon_manager", daemon_module
    )

    return SimpleNamespace(
        subprocess=subprocess_recorder,
        process_table=process_table,
        daemon=daemon_calls,
    )


class TestOneTimeSetupStaysLocal:
    """The version setup may only touch its own marker file and the bundle."""

    _VERSION = "9.9.9-test"

    @staticmethod
    def _patch_metadata_version(monkeypatch, version_or_error) -> None:
        if isinstance(version_or_error, Exception):

            def _version(distribution_name):
                raise version_or_error

        else:

            def _version(distribution_name):
                assert distribution_name == "siada-cli"
                return version_or_error

        monkeypatch.setattr(importlib.metadata, "version", _version)

    def test_setup_checks_bundle_and_writes_marker_only(
        self, monkeypatch, isolated_home, host_side_effect_boundaries
    ):
        bundle_checks: list[bool] = []
        monkeypatch.setattr(launch, "_check_ui_bundle", lambda: bundle_checks.append(True))
        self._patch_metadata_version(monkeypatch, self._VERSION)

        launch._run_first_time_setup_if_needed()

        marker = isolated_home / ".siada-cli" / ".setup_version"
        assert marker.read_text(encoding="utf-8") == self._VERSION
        assert bundle_checks == [True]
        assert host_side_effect_boundaries.subprocess.runs == []
        assert host_side_effect_boundaries.subprocess.popens == []
        assert host_side_effect_boundaries.process_table.iter_calls == []
        assert host_side_effect_boundaries.daemon.instantiations == []
        # The host-mutating helpers must be gone, not merely unused.
        assert not hasattr(launch, "_ensure_nodejs")
        assert not hasattr(launch, "_kill_proactive_processes")

    def test_setup_never_resolves_or_installs_nodejs(
        self, monkeypatch, isolated_home, host_side_effect_boundaries
    ):
        """A missing venv-local Node must not trigger a download in setup."""
        monkeypatch.setattr(
            launch, "_expected_node_path", lambda: pytest.fail("setup resolved Node")
        )
        monkeypatch.setattr(
            "shutil.which", lambda name: pytest.fail("setup probed PATH for Node")
        )
        monkeypatch.setattr(launch, "_check_ui_bundle", lambda: None)
        self._patch_metadata_version(monkeypatch, self._VERSION)

        launch._run_first_time_setup_if_needed()

        marker = isolated_home / ".siada-cli" / ".setup_version"
        assert marker.read_text(encoding="utf-8") == self._VERSION
        assert host_side_effect_boundaries.subprocess.runs == []

    def test_setup_is_a_noop_when_marker_matches(
        self, monkeypatch, isolated_home, host_side_effect_boundaries
    ):
        marker = isolated_home / ".siada-cli" / ".setup_version"
        marker.parent.mkdir(parents=True)
        marker.write_text(self._VERSION, encoding="utf-8")
        bundle_checks: list[bool] = []
        monkeypatch.setattr(launch, "_check_ui_bundle", lambda: bundle_checks.append(True))
        self._patch_metadata_version(monkeypatch, self._VERSION)

        launch._run_first_time_setup_if_needed()

        assert bundle_checks == []
        assert marker.read_text(encoding="utf-8") == self._VERSION
        assert host_side_effect_boundaries.process_table.iter_calls == []

    def test_setup_records_dev_when_package_metadata_is_missing(
        self, monkeypatch, isolated_home, host_side_effect_boundaries
    ):
        monkeypatch.setattr(launch, "_check_ui_bundle", lambda: None)
        self._patch_metadata_version(
            monkeypatch, importlib.metadata.PackageNotFoundError("siada-cli")
        )

        launch._run_first_time_setup_if_needed()

        marker = isolated_home / ".siada-cli" / ".setup_version"
        assert marker.read_text(encoding="utf-8") == "dev"


class TestNodeResolutionNeverDownloads:
    """Node.js comes from the venv layout or PATH; never from a download."""

    def test_venv_local_node_is_used_first(self, monkeypatch, tmp_path):
        local_node = tmp_path / "venv-node"
        local_node.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(launch, "_expected_node_path", lambda: local_node)
        monkeypatch.setattr(
            "shutil.which",
            lambda name: pytest.fail("PATH lookup ran although the venv node exists"),
        )

        assert launch.UILauncher({})._find_local_node() == str(local_node)

    def test_path_node_is_used_when_venv_layout_is_missing(
        self, monkeypatch, tmp_path, host_side_effect_boundaries
    ):
        monkeypatch.setattr(launch, "_expected_node_path", lambda: tmp_path / "missing-node")
        probed: list[str] = []
        monkeypatch.setattr(
            "shutil.which", lambda name: probed.append(name) or "/toolchain/bin/node"
        )

        assert launch.UILauncher({})._find_local_node() == "/toolchain/bin/node"
        assert probed == ["node"]
        # Using an installed Node must not run any install command.
        assert host_side_effect_boundaries.subprocess.runs == []
        assert host_side_effect_boundaries.process_table.iter_calls == []

    def test_missing_node_raises_install_guidance(
        self, monkeypatch, tmp_path, host_side_effect_boundaries
    ):
        monkeypatch.setattr(launch, "_expected_node_path", lambda: tmp_path / "missing-node")
        monkeypatch.setattr("shutil.which", lambda name: None)

        with pytest.raises(RuntimeError) as excinfo:
            launch.UILauncher({})._find_local_node()

        message = str(excinfo.value)
        assert "Node.js" in message
        assert "nodejs.org" in message
        assert "PATH" in message
        assert host_side_effect_boundaries.subprocess.runs == []
        assert host_side_effect_boundaries.process_table.iter_calls == []


class TestUILauncherCommandContract:
    """The installed layout, workspace and module arguments stay intact."""

    def test_build_ui_command_keeps_install_layout(
        self, monkeypatch, tmp_path
    ) -> None:
        node = tmp_path / "node"
        node.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(launch, "_expected_node_path", lambda: node)

        ui_dir = tmp_path / "siada_cli_ui"
        (ui_dir / "bundle").mkdir(parents=True)
        (ui_dir / "bundle" / "siada-ui.js").write_text("// bundle\n", encoding="utf-8")

        module_root = str(Path(launch.__file__).parent.parent.parent)
        workspace = str(tmp_path / "workspace")
        launcher = launch.UILauncher(
            {
                "workspace": workspace,
                "python_path": sys.executable,
                "siada_module": module_root,
                "args": SimpleNamespace(no_daemon=True),
            }
        )

        cmd = launcher._build_ui_command(ui_dir)

        assert cmd == [
            str(node),
            str(ui_dir / "bundle" / "siada-ui.js"),
            "--use-module-mode",
            "--python-path",
            sys.executable,
            "--siada-module",
            module_root,
            "--siada-args",
            "--no-daemon",
            workspace,
        ]

    def test_launch_ui_spawns_the_bundle_with_workspace_and_env(
        self, monkeypatch, tmp_path
    ) -> None:
        node = tmp_path / "node"
        node.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(launch, "_expected_node_path", lambda: node)

        ui_dir = tmp_path / "siada_cli_ui"
        (ui_dir / "bundle").mkdir(parents=True)
        (ui_dir / "bundle" / "siada-ui.js").write_text("// bundle\n", encoding="utf-8")
        monkeypatch.setattr(launch.UILauncher, "_find_ui_directory", lambda self: ui_dir)

        spawned: list[SimpleNamespace] = []

        class _FakeProcess:
            returncode = 0

            def wait(self):
                return 0

            def kill(self):
                raise AssertionError("the fake UI process must not be killed")

        def _fake_popen(cmd, *a, **kwargs):
            spawned.append(SimpleNamespace(cmd=cmd, **kwargs))
            return _FakeProcess()

        monkeypatch.setattr(launch.subprocess, "Popen", _fake_popen)

        workspace = str(tmp_path / "workspace")
        module_root = str(Path(launch.__file__).parent.parent.parent)

        assert launch._launch_ui(workspace, SimpleNamespace(no_daemon=True)) == 0

        assert len(spawned) == 1
        child = spawned[0]
        assert child.cwd == str(ui_dir)
        assert child.cmd == [
            str(node),
            str(ui_dir / "bundle" / "siada-ui.js"),
            "--use-module-mode",
            "--python-path",
            sys.executable,
            "--siada-module",
            module_root,
            "--siada-args",
            "--no-daemon",
            workspace,
        ]
        assert child.env["SIADA_PARENT_MODE"] == "1"
        assert child.env["SIADA_PYTHON_PATH"] == sys.executable
        assert child.env["PYTHONIOENCODING"] == "utf-8"


class TestEnvironmentAssignments:
    """Credential values reach children through env without argv copies."""

    def test_set_env_values_are_not_forwarded_as_arguments(self, monkeypatch, tmp_path):
        monkeypatch.setenv("API_KEY", "sk-test-parent")
        monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/parent")
        parent_env = os.environ.copy()
        key = "sk-test-with spaces-and=equals"
        args = SimpleNamespace(
            set_env=[f"API_KEY={key}", "BASE_URL=http://127.0.0.1:9/v1"],
            model="gpt-4o",
        )
        launcher = launch.UILauncher({"args": args})
        monkeypatch.setattr(launcher, "_find_local_node", lambda: "node")
        (tmp_path / "bundle").mkdir()
        (tmp_path / "bundle" / "siada-ui.js").touch()

        command = launcher._build_ui_command(tmp_path)
        env = launcher._setup_node_env()

        assert "--set-env" not in command
        assert key not in " ".join(command)
        assert env["API_KEY"] == key
        assert env["BASE_URL"] == "http://127.0.0.1:9/v1"
        assert "--model gpt-4o" == command[command.index("--siada-args") + 1]
        assert os.environ == parent_env
        assert key not in env["_SIADA_CLI_ENV_KEYS"]

    def test_explicit_env_survives_dotenv_without_changing_other_precedence(
        self, monkeypatch, tmp_path
    ):
        from siada.support.envprocessor import load_dotenv_files

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("API_KEY", "sk-test-parent")
        monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/parent")
        monkeypatch.setenv("DOTENV_ONLY_VALUE", "parent-value")
        (tmp_path / ".env").write_text(
            "API_KEY=sk-test-dotenv\n"
            "BASE_URL=http://127.0.0.1:9/dotenv\n"
            "DOTENV_ONLY_VALUE=dotenv-value\n",
            encoding="utf-8",
        )
        key = "sk-test-cli with spaces=and=equals"
        launcher = launch.UILauncher({
            "args": SimpleNamespace(set_env=[
                f"API_KEY={key}", "BASE_URL=http://127.0.0.1:9/cli"
            ])
        })
        child_env = launcher._setup_node_env()
        # Simulate the inherited child environment using the real dotenv loader.
        for name, value in child_env.items():
            monkeypatch.setenv(name, value)

        loaded = load_dotenv_files(tmp_path, None)

        assert str(tmp_path / ".env") in loaded
        assert os.environ["API_KEY"] == key
        assert os.environ["BASE_URL"] == "http://127.0.0.1:9/cli"
        assert os.environ["DOTENV_ONLY_VALUE"] == "dotenv-value"
        assert "_SIADA_CLI_ENV_KEYS" not in os.environ

    @pytest.mark.parametrize("marker", ['{"API_KEY": "sk-test-marker"}', "invalid"])
    def test_malformed_env_marker_does_not_report_credential_values(
        self, monkeypatch, tmp_path, capsys, marker
    ):
        from siada.support.envprocessor import load_dotenv_files

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("_SIADA_CLI_ENV_KEYS", marker)

        load_dotenv_files(None, None)

        assert "_SIADA_CLI_ENV_KEYS" not in os.environ
        assert "sk-test-marker" not in capsys.readouterr().out

    @pytest.mark.parametrize("error_type", [OSError, ValueError])
    def test_dotenv_failure_preserves_explicit_values_without_exposing_payload(
        self, monkeypatch, tmp_path, capsys, error_type
    ):
        from siada.support import envprocessor

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("API_KEY=sk-test-dotenv\n", encoding="utf-8")
        monkeypatch.setenv("API_KEY", "sk-test-cli")
        monkeypatch.setenv("_SIADA_CLI_ENV_KEYS", '["API_KEY"]')

        def fail_load(*args, **kwargs):
            monkeypatch.setenv("API_KEY", "sk-test-partial")
            raise error_type("API_KEY=sk-test-exception-payload")

        monkeypatch.setattr(envprocessor, "load_dotenv", fail_load)

        assert envprocessor.load_dotenv_files(tmp_path, None) == []
        assert os.environ["API_KEY"] == "sk-test-cli"
        assert "_SIADA_CLI_ENV_KEYS" not in os.environ
        captured = capsys.readouterr()
        assert captured.out == ""
        assert error_type.__name__ in captured.err
        assert "sk-test-" not in captured.err

    @pytest.mark.parametrize("setting", ["", "=sk-test-value", "API_KEY\0=sk-test-value"])
    def test_invalid_assignments_do_not_print_values(self, setting):
        with pytest.raises(ValueError) as excinfo:
            launch._parse_env_assignments(SimpleNamespace(set_env=[setting]))
        assert "sk-test-value" not in str(excinfo.value)


class TestQueryOnlyFlagsHaveNoStartupSideEffects:
    """``--version`` / ``--help`` / ``-h`` exit during argument parsing.

    The one-time setup is scheduled *after* ``_parse_args()``, so argparse's
    "print and exit" actions answer these flags before any startup work runs —
    no marker file, no bundle check, no daemon handling, no UI spawn.
    """

    @pytest.fixture
    def startup_boundaries(self, monkeypatch, isolated_home):
        setup_calls: list[bool] = []
        ui_calls: list[tuple] = []
        backend_calls: list[bool] = []
        monkeypatch.setattr(
            launch, "_run_first_time_setup_if_needed", lambda: setup_calls.append(True)
        )
        monkeypatch.setattr(
            launch, "_launch_ui", lambda *a, **k: ui_calls.append((a, k)) or 0
        )
        monkeypatch.setattr(
            launch, "_run_backend", lambda *a, **k: backend_calls.append(True) or 0
        )
        return SimpleNamespace(
            setup=setup_calls,
            ui=ui_calls,
            backend=backend_calls,
            home=isolated_home,
        )

    def test_version_prints_and_exits_without_setup(
        self, monkeypatch, capsys, startup_boundaries
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["siada-cli", "--version"])

        with pytest.raises(SystemExit) as excinfo:
            launch.main()

        assert excinfo.value.code == 0
        assert siada.__version__ in capsys.readouterr().out
        assert startup_boundaries.setup == []
        assert startup_boundaries.ui == []
        assert startup_boundaries.backend == []
        assert not (startup_boundaries.home / ".siada-cli").exists()

    @pytest.mark.parametrize("flag", ["--help", "-h"])
    def test_help_prints_and_exits_without_setup(
        self, flag, monkeypatch, capsys, startup_boundaries
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["siada-cli", flag])

        with pytest.raises(SystemExit) as excinfo:
            launch.main()

        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out
        assert "--version" in out
        assert startup_boundaries.setup == []
        assert startup_boundaries.ui == []
        assert not (startup_boundaries.home / ".siada-cli").exists()

    def test_invalid_invocation_exits_before_any_setup(
        self, monkeypatch, capsys, startup_boundaries
    ) -> None:
        """An argparse error must not run the setup path either."""
        monkeypatch.setattr(sys, "argv", ["siada-cli", "--model"])  # missing value

        with pytest.raises(SystemExit) as excinfo:
            launch.main()

        assert excinfo.value.code == 2
        assert "expected one argument" in capsys.readouterr().err
        assert startup_boundaries.setup == []
        assert startup_boundaries.ui == []
        assert not (startup_boundaries.home / ".siada-cli").exists()

    def test_version_and_help_flags_are_the_parser_contract(self) -> None:
        """The launcher relies on argparse; ``-V`` is not a parser flag."""
        parser = get_parser(default_config_files=[], git_root=None)

        # The parser defines the print-and-exit flags the launcher depends on.
        assert "--version" in parser._option_string_actions
        assert "-h" in parser._option_string_actions
        assert "--help" in parser._option_string_actions
        # ``-V`` is not part of the contract (short options are -a/-h/-p/-v), so
        # it stays an unknown token argparse ignores — the launcher must not
        # invent a version flag the CLI does not define.
        assert "-V" not in parser._option_string_actions
        _args, unknown = parser.parse_known_args(["-V"])
        assert unknown == ["-V"]


class TestNormalLauncherPathIsPreserved:
    """The one-time setup still runs, then dispatch stays as before."""

    def test_ui_launch_parses_then_runs_setup_then_launches_ui(self, monkeypatch) -> None:
        calls: list[tuple] = []
        monkeypatch.setattr(
            launch, "_run_first_time_setup_if_needed", lambda: calls.append(("setup",))
        )
        monkeypatch.setattr(launch, "_resolve_workspace", lambda: ("/tmp/ws-test", None))
        args = SimpleNamespace(ui=True)
        monkeypatch.setattr(
            launch, "_parse_args", lambda git_root: calls.append(("parse", git_root)) or args
        )
        monkeypatch.setattr(launch, "_check_resume_workspace", lambda workspace, a: 0)
        monkeypatch.setattr(
            launch,
            "_launch_ui",
            lambda workspace, a: calls.append(("ui", workspace, a)) or 0,
        )
        monkeypatch.setattr(sys, "argv", ["siada-cli"])

        assert launch.main() == 0
        # Parsing comes first (so version/help exit before setup); setup still
        # runs before the UI is launched.
        assert calls == [("parse", None), ("setup",), ("ui", "/tmp/ws-test", args)]

    def test_no_ui_delegates_to_backend_after_setup(self, monkeypatch) -> None:
        from siada.entrypoint import siadahub

        calls: list[str] = []
        monkeypatch.setattr(
            launch, "_run_first_time_setup_if_needed", lambda: calls.append("setup")
        )
        monkeypatch.setattr(launch, "_resolve_workspace", lambda: ("/tmp/ws-test", None))
        args = SimpleNamespace(ui=False)
        monkeypatch.setattr(
            launch, "_parse_args", lambda git_root: calls.append("parse") or args
        )
        monkeypatch.setattr(launch, "_check_resume_workspace", lambda workspace, a: 0)
        monkeypatch.setattr(siadahub, "main", lambda: calls.append("backend") or 7)
        monkeypatch.setattr(sys, "argv", ["siada-cli", "--no-ui"])

        assert launch.main() == 7
        assert calls == ["parse", "setup", "backend"]


class TestLauncherSourceBoundary:
    """The launcher source carries no host-mutating escape hatches."""

    SOURCE = Path(launch.__file__).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "marker",
        [
            "psutil",
            "process_iter",
            "_kill_proactive_processes",
            "_ensure_nodejs",
            "_install_node_unix",
            "_install_node_windows",
            "_NVM_INSTALL_URL",
            "nvm.sh",
            "urlretrieve",
            "curl",
            "wget",
            "DaemonManager(",
        ],
    )
    def test_launcher_has_no_process_or_toolchain_management_code(self, marker) -> None:
        assert marker not in self.SOURCE