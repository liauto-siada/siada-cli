#!/usr/bin/env python
"""Launch UI as a Node.js subprocess and block until it exits."""

import os
import subprocess
import sys
import time as _time
from pathlib import Path
from typing import Any, Dict, List

_LAUNCH_START = _time.perf_counter()

# Prevent the current working directory from shadowing the installed siada package.
# When CWD contains a source `siada/` directory, Python resolves it before site-packages.
# We remove CWD from sys.path and redirect siada.__path__ to the installed version,
# while keeping the current module loading chain intact in sys.modules.
_cwd = os.getcwd()
if "" in sys.path or _cwd in sys.path:
    sys.path = [p for p in sys.path if p not in ("", ".", _cwd)]
    _siada_mod = sys.modules.get("siada")
    if _siada_mod:
        _local_siada = os.path.join(_cwd, "siada")
        if any(os.path.normpath(p) == _local_siada for p in getattr(_siada_mod, "__path__", [])):
            for _sp in sys.path:
                _candidate = os.path.join(_sp, "siada")
                if os.path.isdir(_candidate) and os.path.normpath(_candidate) != _local_siada:
                    _siada_mod.__path__ = [_candidate]
                    break
    _keep = {"siada", "siada.entrypoint", "siada.entrypoint.launch_ui_with_acp"}
    _stale = [k for k in sys.modules if (k == "siada" or k.startswith("siada.")) and k not in _keep]
    for _k in _stale:
        del sys.modules[_k]

from siada.foundation.logging import logger


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
    node = _expected_node_path()
    raise RuntimeError(
        f"Node.js {_NODE_VERSION} not found at {node}.\n"
        "Please re-run the siada install script:\n"
        "  curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh"
    )


# ---------------------------------------------------------------------------
# First-run initialization
# ---------------------------------------------------------------------------


def _kill_proactive_processes() -> None:
    """Kill any running siada.agent_hub.proactive processes."""
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
        print(f"[siada] Terminated {len(killed)} stale proactive process(es): {killed}", flush=True)


def _check_ui_bundle() -> None:
    """Warn if the UI bundle is missing from the installed package."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("siada_cli_ui")
        if spec is None or spec.origin is None:
            print("[siada] Warning: siada_cli_ui package not found — UI may not work.", flush=True)
            return
        bundle = Path(spec.origin).parent / "bundle" / "siada-ui.js"
        if not bundle.exists():
            print(
                f"[siada] Warning: UI bundle not found at {bundle}.\n"
                "[siada] The package may not be properly built.",
                flush=True,
            )
    except Exception:
        pass


def _expected_node_path() -> Path:
    """Return the expected Node.js binary path inside the siada venv."""
    venv_dir = Path(sys.executable).parent.parent
    if sys.platform == "win32":
        return venv_dir / "node" / "node.exe"
    return venv_dir / "nvm" / "versions" / "node" / f"v{_NODE_VERSION}" / "bin" / "node"


def _install_node_unix() -> bool:
    """Download nvm and use it to install Node.js on Unix/macOS."""
    venv_dir = Path(sys.executable).parent.parent
    nvm_dir = venv_dir / "nvm"
    nvm_install_script = venv_dir / "nvm_install.sh"

    print(f"[siada] Downloading nvm from {_NVM_INSTALL_URL} ...", flush=True)
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
        print("[siada] Neither curl nor wget found. Cannot install nvm.", flush=True)
        return False

    if dl.returncode != 0:
        print(f"[siada] Failed to download nvm: {dl.stderr.decode().strip()}", flush=True)
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
    print(f"[siada] Installing Node.js v{_NODE_VERSION} via nvm ...", flush=True)
    result = subprocess.run(["bash", "-c", bash_script])
    nvm_install_script.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"[siada] nvm/Node.js installation failed (exit {result.returncode}).", flush=True)
        return False

    if not _expected_node_path().exists():
        print("[siada] Node.js binary not found after installation.", flush=True)
        return False

    print(f"[siada] Node.js v{_NODE_VERSION} installed successfully.", flush=True)
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

    print(f"[siada] Downloading Node.js v{_NODE_VERSION} for Windows ...", flush=True)
    try:
        urllib.request.urlretrieve(node_url, temp_zip)
    except Exception as e:
        print(f"[siada] Failed to download Node.js: {e}", flush=True)
        return False

    print("[siada] Extracting Node.js ...", flush=True)
    try:
        with zipfile.ZipFile(temp_zip) as zf:
            zf.extractall(venv_dir)
        extracted = venv_dir / f"node-v{_NODE_VERSION}-win-x64"
        if node_dir.exists():
            shutil.rmtree(node_dir)
        extracted.rename(node_dir)
    except Exception as e:
        print(f"[siada] Failed to extract Node.js: {e}", flush=True)
        return False
    finally:
        temp_zip.unlink(missing_ok=True)

    if not _expected_node_path().exists():
        print("[siada] Node.js binary not found after extraction.", flush=True)
        return False

    print(f"[siada] Node.js v{_NODE_VERSION} installed successfully.", flush=True)
    return True


def _ensure_nodejs() -> bool:
    """Install Node.js into the siada venv if not already present."""
    if _expected_node_path().exists():
        return True

    print(f"[siada] Node.js v{_NODE_VERSION} not found, installing ...", flush=True)
    try:
        if sys.platform == "win32":
            return _install_node_windows()
        return _install_node_unix()
    except Exception as e:
        print(f"[siada] Node.js installation error: {e}", flush=True)
        return False


def _run_first_time_setup_if_needed() -> None:
    """Run one-time setup tasks when the installed version changes."""
    import importlib.metadata

    try:
        current_version = importlib.metadata.version("siada-cli")
    except importlib.metadata.PackageNotFoundError:
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
        marker_file.write_text(current_version)
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
    "--api_server",
    "--stop_api_server",
    "--stop-daemon",
    "--daemon-status",
    "--resume-list",
    "--user-id",
    "--access-token",
}


def _run_backend() -> int:
    """Delegate to the Python backend (siadahub) as a subprocess."""
    result = subprocess.run([sys.executable, "-m", "siada.entrypoint.siadahub", *sys.argv[1:]])
    return result.returncode


def _resolve_workspace() -> tuple:
    """Return (workspace, git_root) derived from --workspace or the cwd."""
    import argparse
    from siada.support.repo import get_git_root

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", default=None)
    temp_args, _ = parser.parse_known_args()

    git_root = get_git_root(temp_args.workspace)
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
            print(f"Error: Session not found: {resume_id}", file=sys.stderr)
            return 1

        origin_root = session_info.project_root or ""
        if (
            origin_root
            and origin_root != "Unknown"
            and os.path.normpath(origin_root) != os.path.normpath(workspace)
        ):
            print(f"Session belongs to workspace: {origin_root}", file=sys.stderr)
            print(
                f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}",
                file=sys.stderr,
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
    _t0 = _time.perf_counter()
    logger.debug(f"[PERF][launcher] main() start | +{(_t0 - _LAUNCH_START)*1000:.0f}ms since module load")

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
