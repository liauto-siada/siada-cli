#!/usr/bin/env python
"""Launch UI as a Node.js subprocess and block until it exits."""

import os
import subprocess
import sys
import time as _time
import warnings
from pathlib import Path
from typing import Any, Dict, List

# Suppress jieba SyntaxWarning on Python 3.12+ (invalid escape sequences in jieba source)
# Must be set at module level before jieba is ever imported in this process.
warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")

_LAUNCH_START = _time.perf_counter()


from siada.foundation.logging import logger, remove_console_handler  # noqa: E402



_NODE_VERSION = "20.11.0"
_NVM_VERSION = "0.39.7"
_NVM_INSTALL_URL = f"https://gitee.com/mirrors/nvm/raw/v{_NVM_VERSION}/install.sh"
_NODE_MIRROR = "https://npmmirror.com/mirrors/node"


class UILauncher:
    """Build and run the Node UI subprocess, inheriting the terminal TTY."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def _find_ui_directory(self) -> Path:
        """Find the UI directory."""
        current_file = Path(__file__).resolve()
        ui_dir = current_file.parent.parent.parent / "siada_cli_ui"
        ui_dir_legacy = current_file.parent.parent / "siada_cli_ui"

        if ui_dir.exists() and (ui_dir / "bundle" / "siada-ui.js").exists():
            return ui_dir
        if ui_dir.exists() and (ui_dir / "package.json").exists():
            return ui_dir
        if ui_dir_legacy.exists() and (ui_dir_legacy / "package.json").exists():
            return ui_dir_legacy

        logger.error("UI directory not found. Checked:")
        logger.error(f"  1. {ui_dir}")
        logger.error(f"  2. {ui_dir_legacy}")
        raise FileNotFoundError("UI directory not found. Please ensure siada-cli is properly installed.")

    def _quote_arg(self, arg: str) -> str:
        """Quote argument if it contains spaces or special characters."""
        import shlex

        if ' ' in arg or '"' in arg or "'" in arg or '\\' in arg:
            return shlex.quote(arg)
        return arg

    def _build_siada_args(self) -> List[str]:
        """Build arguments to pass to Python backend via --siada-args."""
        args = []
        config_args = self.config.get("args")

        if not config_args:
            return args

        if hasattr(config_args, "agent") and config_args.agent:
            args.extend(["--agent", config_args.agent])

        if hasattr(config_args, "resume") and config_args.resume is not None:
            if config_args.resume:
                args.extend(["--resume", config_args.resume])
            else:
                args.append("--resume")

        if hasattr(config_args, "env_file") and config_args.env_file:
            args.extend(["--env-file", self._quote_arg(config_args.env_file)])

        if hasattr(config_args, "set_env") and config_args.set_env:
            for env_val in config_args.set_env:
                args.extend(["--set-env", self._quote_arg(env_val)])

        if hasattr(config_args, "model") and config_args.model:
            args.extend(["--model", config_args.model])

        if hasattr(config_args, "reasoning_effort") and config_args.reasoning_effort:
            args.extend(["--reasoning-effort", config_args.reasoning_effort])

        if hasattr(config_args, "thinking_tokens") and config_args.thinking_tokens:
            args.extend(["--thinking-tokens", str(config_args.thinking_tokens)])

        if hasattr(config_args, "thinking") and config_args.thinking is not None:
            args.append("--thinking" if config_args.thinking else "--no-thinking")

        if hasattr(config_args, "parallel_tool_calls") and config_args.parallel_tool_calls is not None:
            args.append(
                "--parallel-tool-calls" if config_args.parallel_tool_calls else "--no-parallel-tool-calls"
            )

        if hasattr(config_args, "provider") and config_args.provider:
            args.extend(["--provider", config_args.provider])

        if hasattr(config_args, "pretty") and config_args.pretty is not None:
            args.append("--pretty" if config_args.pretty else "--no-pretty")

        if hasattr(config_args, "fancy_input") and config_args.fancy_input is not None:
            args.append("--fancy-input" if config_args.fancy_input else "--no-fancy-input")

        if hasattr(config_args, "banner") and config_args.banner is not None:
            args.append("--banner" if config_args.banner else "--no-banner")

        if hasattr(config_args, "check_update") and config_args.check_update is not None:
            args.append("--check-update" if config_args.check_update else "--no-check-update")

        if hasattr(config_args, "checkpointing") and config_args.checkpointing is not None:
            args.append("--checkpointing" if config_args.checkpointing else "--no-checkpointing")

        if hasattr(config_args, "max_checkpoint_files") and config_args.max_checkpoint_files:
            args.extend(["--max-checkpoint-files", str(config_args.max_checkpoint_files)])

        if hasattr(config_args, "no_daemon") and config_args.no_daemon:
            args.append("--no-daemon")

        if hasattr(config_args, "vim") and config_args.vim:
            args.append("--vim")

        if hasattr(config_args, "verbose") and config_args.verbose:
            args.append("--verbose")

        if hasattr(config_args, "encoding") and config_args.encoding:
            args.extend(["--encoding", config_args.encoding])

        if hasattr(config_args, "editor") and config_args.editor:
            args.extend(["--editor", self._quote_arg(config_args.editor)])

        if hasattr(config_args, "disable_console_output") and config_args.disable_console_output is not None:
            args.append(
                "--disable-console-output"
                if config_args.disable_console_output
                else "--no-disable-console-output"
            )

        # Headroom proxy integration: forward these flags to the Python backend
        # so that launching via the `siada` entrypoint (which spawns the Node UI,
        # which in turn spawns the backend) still activates headroom. Without
        # this passthrough, `siada --headroom` is parsed here but never reaches
        # the backend, so the proxy never starts.
        if hasattr(config_args, "headroom") and config_args.headroom:
            args.append("--headroom")

        if hasattr(config_args, "no_headroom") and config_args.no_headroom:
            args.append("--no-headroom")

        if hasattr(config_args, "headroom_port") and config_args.headroom_port is not None:
            args.extend(["--headroom-port", str(config_args.headroom_port)])

        if hasattr(config_args, "headroom_budget") and config_args.headroom_budget is not None:
            args.extend(["--headroom-budget", str(config_args.headroom_budget)])

        return args


    def _find_local_node(self) -> str:
        """Return the Node.js binary installed by the siada install script."""
        return str(_expected_node_path()) if _expected_node_path().exists() else _raise_missing_node()

    def _setup_node_env(self) -> Dict[str, str]:
        """Setup environment variables for Node.js execution."""
        env = os.environ.copy()
        venv_dir = Path(sys.executable).parent.parent

        if sys.platform == "win32":
            node_dir = venv_dir / "node"
            if node_dir.exists():
                env["PATH"] = f"{node_dir}{os.pathsep}{env.get('PATH', '')}"
        else:
            node_bin_dir = venv_dir / "node" / "bin"
            nvm_dir = venv_dir / "nvm"
            if node_bin_dir.exists():
                env["PATH"] = f"{node_bin_dir}{os.pathsep}{env.get('PATH', '')}"
            if nvm_dir.exists():
                env["NVM_DIR"] = str(nvm_dir)

        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["SIADA_PARENT_MODE"] = "1"
        env["SIADA_ACP_MODE"] = env.get("SIADA_ACP_MODE", "1")
        # Prevent the Python backend subprocess from picking up CWD in
        # sys.path, so a local directory (e.g. agents/) in the user's
        # project cannot shadow installed packages like openai-agents.
        env["PYTHONSAFEPATH"] = "1"
        # Expose the project's Python interpreter to the Node UI so that
        # subprocess helpers (e.g. clipboard image reader on macOS, which
        # depends on PyObjC/AppKit) can use the same env that the backend
        # was launched with.  System `python3` on macOS does not ship with
        # PyObjC and Homebrew python3 is unlikely to have it either.
        env["SIADA_PYTHON_PATH"] = self.config.get("python_path", sys.executable)
        # Propagate debug mode: --verbose flag → SIADA_DEBUG=1 for Node UI
        config_args = self.config.get("args")
        if hasattr(config_args, "verbose") and config_args.verbose:
            env["SIADA_DEBUG"] = "1"
        return env

    def _build_ui_command(self, ui_dir: Path) -> list[str]:
        """Build the command to launch UI."""
        node_path = self._find_local_node()
        is_debugging = (
            "DEBUGPY_LAUNCHER_PORT" in os.environ
            or "PYDEVD_LOAD_VALUES_ASYNC" in os.environ
            or sys.gettrace() is not None
        )

        bundle_cli = ui_dir / "bundle" / "siada-ui.js"
        dist_cli = ui_dir / "dist" / "cli.js"
        cli_script = ui_dir / "src" / "cli.ts"

        if is_debugging and cli_script.exists():
            cmd = ["npm", "start", "--"]
        elif bundle_cli.exists():
            cmd = [node_path, str(bundle_cli)]
        elif dist_cli.exists():
            cmd = [node_path, str(dist_cli)]
        elif cli_script.exists():
            cmd = ["npm", "start", "--"]
        else:
            raise FileNotFoundError("UI entry point not found (bundle/siada-ui.js, dist/cli.js, or src/cli.ts)")

        workspace = self.config.get("workspace", os.getcwd())
        cmd.extend(
            [
                "--use-module-mode",
                "--python-path",
                self.config.get("python_path", sys.executable),
                "--siada-module",
                self.config.get("siada_module", str(Path(__file__).parent.parent.parent)),
            ]
        )

        siada_args = self._build_siada_args()
        if siada_args:
            cmd.extend(["--siada-args", " ".join(siada_args)])

        cmd.append(str(workspace))
        return cmd


def _raise_missing_node() -> str:
    from siada.services.auto_update import get_curl_install_flags

    node = _expected_node_path()
    raise RuntimeError(
        f"Node.js {_NODE_VERSION} not found at {node}.\n"
        "Please re-run the siada install script:\n"
        f"  curl {get_curl_install_flags()} https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh"
    )



# ---------------------------------------------------------------------------
# First-run initialization
# ---------------------------------------------------------------------------


def _kill_proactive_processes() -> None:
    """Kill any running siada.agent_hub.proactive processes, then re-spawn
    a fresh one using the current venv.

    Context: this helper runs from the version-change one-time setup path
    (see ``_run_first_time_setup_if_needed``).  The original intent is to
    make sure no daemon is left running old bytecode after an upgrade.
    However the proactive daemon's auto-updater may have **already**
    spawned a helper that restarted the daemon on the new version; in that
    case blindly killing it here would leave the user with no daemon at
    all until the next CLI invocation re-creates one.

    To stay safe in both scenarios we:
      1. Kill every matching process (the original behaviour), so any
         orphaned old-bytecode daemon is cleaned up.
      2. Immediately re-spawn a fresh daemon from the *current* venv via
         ``DaemonManager.start_daemon()``.  This guarantees that after
         this function returns there is exactly one daemon running the
         current version.
    """
    try:
        import psutil
    except ImportError:
        return

    killed: list[int] = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "siada.agent_hub.proactive" in cmdline:
                proc.kill()
                killed.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        logger.info(f"[siada] Terminated {len(killed)} stale proactive process(es): {killed}")

    # Compensate: re-spawn a daemon from the current venv so we don't leave
    # the user daemon-less.  Fire-and-forget; failures are non-fatal.
    try:
        from siada.foundation.constants import SIADA_HOME
        from siada.agent_hub.proactive.daemon_manager import DaemonManager
        from pathlib import Path as _Path

        pid_file = SIADA_HOME / "siada-daemon.pid"
        daemon_script = (
            _Path(__file__).parent.parent / "agent_hub/proactive/daemon.py"
        )
        manager = DaemonManager(pid_file, daemon_script)
        # Small grace delay so the OS has fully reaped the killed processes
        # before our scanner in start_daemon() checks whether one is alive.
        import time as _time
        _time.sleep(0.3)
        if manager.start_daemon():
            logger.info("[siada] Re-spawned proactive daemon from current venv")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[siada] Failed to re-spawn proactive daemon: {exc}")

def _locate_siada_cli_ui_dir() -> Path | None:
    """Locate the installed ``siada_cli_ui`` directory.

    ``siada_cli_ui`` is distributed as a data directory alongside the ``siada``
    package (it contains a Node.js bundle, not Python code). Depending on how
    the wheel is built, ``siada_cli_ui/__init__.py`` may or may not be present
    in the installed copy — so we cannot rely solely on ``importlib`` to find
    it. Fall back to resolving it relative to the installed ``siada`` package
    location, which is the canonical layout used by the wheel.
    """
    import importlib.util

    # Prefer a proper Python package lookup when the marker file is installed.
    spec = importlib.util.find_spec("siada_cli_ui")
    if spec is not None:
        if spec.origin:
            return Path(spec.origin).parent
        locations = list(getattr(spec, "submodule_search_locations", None) or [])
        if locations:
            return Path(locations[0])

    # Fall back to the sibling directory next to the installed ``siada``
    # package (this is how the wheel ships ``siada_cli_ui`` as a data dir).
    siada_spec = importlib.util.find_spec("siada")
    candidates: list[Path] = []
    if siada_spec is not None and siada_spec.origin:
        candidates.append(Path(siada_spec.origin).parent.parent / "siada_cli_ui")
    # Also check alongside this file for source-tree layouts.
    candidates.append(Path(__file__).resolve().parent.parent.parent / "siada_cli_ui")
    for cand in candidates:
        if cand.is_dir():
            return cand
    return None


def _check_ui_bundle() -> None:
    """Warn if the UI bundle is missing from the installed package."""
    try:
        ui_dir = _locate_siada_cli_ui_dir()
        if ui_dir is None:
            logger.warning("[siada] Warning: siada_cli_ui package not found — UI may not work.")
            return
        bundle = ui_dir / "bundle" / "siada-ui.js"
        if not bundle.exists():
            logger.warning(
                f"[siada] Warning: UI bundle not found at {bundle}.\n"
                "[siada] The package may not be properly built."
            )
    except Exception:
        pass


def _expected_node_path() -> Path:
    """Return the expected Node.js binary path inside the siada venv.

    Two layouts are supported:
    1. Prebuilt tarball: ``venv/node/bin/node``  (bundled by build_venv_tarball.sh)
    2. nvm-installed:    ``venv/nvm/versions/node/v{ver}/bin/node``  (runtime fallback)
    """
    venv_dir = Path(sys.executable).parent.parent
    if sys.platform == "win32":
        # tarball layout
        p = venv_dir / "node" / "node.exe"
        if p.exists():
            return p
        return venv_dir / "nvm" / "versions" / "node" / f"v{_NODE_VERSION}" / "node.exe"
    # tarball layout first
    p = venv_dir / "node" / "bin" / "node"
    if p.exists():
        return p
    # nvm layout fallback
    return venv_dir / "nvm" / "versions" / "node" / f"v{_NODE_VERSION}" / "bin" / "node"


def _install_node_unix() -> bool:
    """Download nvm and use it to install Node.js on Unix/macOS."""
    venv_dir = Path(sys.executable).parent.parent
    nvm_dir = venv_dir / "nvm"
    nvm_install_script = venv_dir / "nvm_install.sh"

    logger.info(f"[siada] Downloading nvm from {_NVM_INSTALL_URL} ...")
    if subprocess.run(["which", "curl"], capture_output=True).returncode == 0:
        dl = subprocess.run(
            ["curl", "-fsSL", "-o", str(nvm_install_script), _NVM_INSTALL_URL],
            capture_output=True,
        )
    elif subprocess.run(["which", "wget"], capture_output=True).returncode == 0:
        dl = subprocess.run(
            ["wget", "-q", "-O", str(nvm_install_script), _NVM_INSTALL_URL],
            capture_output=True,
        )
    else:
        logger.warning("[siada] Neither curl nor wget found. Cannot install nvm.")
        return False

    if dl.returncode != 0:
        logger.error(f"[siada] Failed to download nvm: {dl.stderr.decode().strip()}")
        return False

    bash_script = f'''set -e
export NVM_DIR="{nvm_dir}"
export NVM_NODEJS_ORG_MIRROR="{_NODE_MIRROR}"
mkdir -p "$NVM_DIR"
bash "{nvm_install_script}"
. "$NVM_DIR/nvm.sh"
nvm install "{_NODE_VERSION}"
nvm use "{_NODE_VERSION}"
'''
    logger.info(f"[siada] Installing Node.js v{_NODE_VERSION} via nvm ...")
    result = subprocess.run(["bash", "-c", bash_script])
    nvm_install_script.unlink(missing_ok=True)

    if result.returncode != 0:
        logger.error(f"[siada] nvm/Node.js installation failed (exit {result.returncode}).")
        return False

    if not _expected_node_path().exists():
        logger.error("[siada] Node.js binary not found after installation.")
        return False

    logger.info(f"[siada] Node.js v{_NODE_VERSION} installed successfully.")
    return True


def _install_node_windows() -> bool:
    """Download the Node.js zip and extract it on Windows."""
    import shutil
    import urllib.request
    import zipfile

    venv_dir = Path(sys.executable).parent.parent
    node_dir = venv_dir / "node"
    node_url = f"https://nodejs.org/dist/v{_NODE_VERSION}/node-v{_NODE_VERSION}-win-x64.zip"
    temp_zip = venv_dir / "node.zip"

    logger.info(f"[siada] Downloading Node.js v{_NODE_VERSION} for Windows ...")
    try:
        urllib.request.urlretrieve(node_url, temp_zip)
    except Exception as e:
        logger.error(f"[siada] Failed to download Node.js: {e}")
        return False

    logger.info("[siada] Extracting Node.js ...")
    try:
        with zipfile.ZipFile(temp_zip) as zf:
            zf.extractall(venv_dir)
        extracted = venv_dir / f"node-v{_NODE_VERSION}-win-x64"
        if node_dir.exists():
            shutil.rmtree(node_dir)
        extracted.rename(node_dir)
    except Exception as e:
        logger.error(f"[siada] Failed to extract Node.js: {e}")
        return False
    finally:
        temp_zip.unlink(missing_ok=True)

    if not _expected_node_path().exists():
        logger.error("[siada] Node.js binary not found after extraction.")
        return False

    logger.info(f"[siada] Node.js v{_NODE_VERSION} installed successfully.")
    return True


def _ensure_nodejs() -> bool:
    """Install Node.js into the siada venv if not already present."""
    if _expected_node_path().exists():
        return True

    logger.info(f"[siada] Node.js v{_NODE_VERSION} not found, installing ...")
    try:
        if sys.platform == "win32":
            return _install_node_windows()
        return _install_node_unix()
    except Exception as e:
        logger.error(f"[siada] Node.js installation error: {e}")
        return False


def _run_first_time_setup_if_needed() -> None:
    """Run one-time setup tasks when the installed version changes."""
    import importlib.metadata

    try:
        current_version = importlib.metadata.version("siada-cli")
    except importlib.metadata.PackageNotFoundError:
        current_version = "dev"
    # Defensive: importlib.metadata.version() may return None in rare cases
    # (e.g. broken package METADATA), which would crash marker_file.write_text().
    if not current_version:
        current_version = "dev"

    marker_dir = Path.home() / ".siada-cli"
    marker_file = marker_dir / ".setup_version"

    if not _expected_node_path().exists():
        _ensure_nodejs()

    if marker_file.exists():
        try:
            if marker_file.read_text().strip() == current_version:
                return
        except OSError:
            pass

    _kill_proactive_processes()
    _check_ui_bundle()

    try:
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_file.write_text(str(current_version) if current_version else "dev")
    except OSError:
        pass


_BACKEND_ONLY_ARGS = {
    "--upgrade",
    "--update",
    "--just-check-update",

    "--list-models",
    "--models",
    "--prompt",
    "-p",
    "--stop-daemon",
    "--restart-daemon",
    "--daemon-status",
    "--resume-list",
    "--user-id",
    "--access-token",
}


def _run_backend() -> int:
    """Delegate to the Python backend (siadahub) as a subprocess."""
    result = subprocess.run([sys.executable, "-m", "siada.entrypoint.siadahub", *sys.argv[1:]])
    return result.returncode


def _fast_git_root(path=None):
    """Fast git root detection without importing GitPython (~95ms saved).

    Walks up the directory tree looking for a ``.git`` entry (file or dir).
    This is sufficient for workspace resolution; the full GitPython-backed
    ``get_git_root()`` is used later in siadahub.py when the backend starts.
    """
    from pathlib import Path
    p = Path(path or os.getcwd()).resolve()
    while p != p.parent:
        if (p / ".git").exists():
            return str(p)
        p = p.parent
    return None


def _resolve_workspace() -> tuple:
    """Return (workspace, git_root) derived from --workspace or the cwd."""
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", default=None)
    temp_args, _ = parser.parse_known_args()

    git_root = _fast_git_root(temp_args.workspace)
    workspace = temp_args.workspace or git_root or os.getcwd()
    return workspace, git_root


def _parse_args(git_root):
    """Build the full argument parser and parse sys.argv."""
    from siada.entrypoint.args_parser.args import get_parser

    parser = get_parser(default_config_files=[], git_root=git_root)
    args, _ = parser.parse_known_args()
    return args


def _check_resume_workspace(workspace: str, args) -> int:
    """Validate that the resume session belongs to the current workspace."""
    if not (hasattr(args, "resume") and args.resume is not None):
        return 0

    resume_id = args.resume or "latest"
    try:
        from siada.support.resume_service import ResumeService

        session_info = ResumeService(workspace).get_session_info(resume_id)
        if session_info is None:
            logger.error(f"Error: Session not found: {resume_id}")
            return 1

        origin_root = session_info.project_root or ""
        if (
            origin_root
            and origin_root != "Unknown"
            and os.path.normpath(origin_root) != os.path.normpath(workspace)
        ):
            logger.error(f"Session belongs to workspace: {origin_root}")
            logger.error(
                f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}"
            )
            return 1
    except Exception as e:
        logger.warning(f"Early resume workspace check failed: {e}")

    return 0


def _launch_ui(workspace: str, args) -> int:
    """Build and run the Node UI subprocess, inheriting the terminal TTY.

    On Windows, Ctrl+C sends CTRL_C_EVENT to **all** processes sharing the
    same console – including this Python parent.  ``subprocess.run()``
    internally catches *all* exceptions (including ``KeyboardInterrupt``)
    and calls ``process.kill()`` on the child, which would immediately
    destroy the Node.js UI before it has a chance to handle the interrupt
    itself.

    To avoid this we use ``Popen`` directly and swallow
    ``KeyboardInterrupt`` while waiting, letting the Node.js UI (and the
    siada backend it manages) handle Ctrl+C through their own logic.
    """
    launcher = UILauncher(
        {
            "workspace": workspace,
            "python_path": sys.executable,
            "siada_module": str(Path(__file__).parent.parent.parent),
            "args": args,
        }
    )
    ui_dir = launcher._find_ui_directory()
    cmd = launcher._build_ui_command(ui_dir)
    env = launcher._setup_node_env()

    proc = subprocess.Popen(cmd, cwd=str(ui_dir), env=env)
    try:
        # Wait for the UI process, ignoring KeyboardInterrupt so that
        # Ctrl+C on Windows doesn't cause this parent to kill the child.
        while True:
            try:
                proc.wait()
                break
            except KeyboardInterrupt:
                pass
    except Exception:
        # For any unexpected error, ensure we don't leave zombies.
        proc.kill()
        proc.wait()
        raise
    return proc.returncode


def main():
    """Main entry point for siada-cli command."""
    if "--acp" in sys.argv:
        from siada.acp_server.main import main as acp_server_main
        acp_server_main()
        return 0

    remove_console_handler()
    _t0 = _time.perf_counter()
    logger.debug(f"[PERF][launcher] main() start | +{(_t0 - _LAUNCH_START)*1000:.0f}ms since module load")

    try:
        from siada.foundation.logging import redirect_agents_logger
        redirect_agents_logger()
    except Exception:
        pass

    _run_first_time_setup_if_needed()
    logger.debug(f"[PERF][launcher] first_time_setup done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    if _BACKEND_ONLY_ARGS.intersection(sys.argv):
        return _run_backend()

    workspace, git_root = _resolve_workspace()
    logger.debug(f"[PERF][launcher] resolve_workspace done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    args = _parse_args(git_root)
    logger.debug(f"[PERF][launcher] parse_args done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    if rc := _check_resume_workspace(workspace, args):
        return rc

    if hasattr(args, "ui") and not args.ui:
        from siada.entrypoint.siadahub import main as siadahub_main

        return siadahub_main()

    logger.debug(f"[PERF][launcher] about to _launch_ui | +{(_time.perf_counter() - _t0)*1000:.0f}ms")
    return _launch_ui(workspace, args)


if __name__ == "__main__":
    main()
