#!/usr/bin/env python
"""Launch UI as a Node.js subprocess and block until it exits."""

import os
import json
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

# ---------------------------------------------------------------------------
# Agents-SDK bootstrap gate — only needed for in-process agent modes.
#
# ``--acp`` runs the agent in THIS process (see the preload below), so the
# ``agents`` package must be initialized single-threaded before any other
# siada import: openai-agents 0.22.x's ``__init__`` pulls
# ``agents.models._openai_shared`` and, when that package import races with a
# worker thread's submodule import, CPython can raise ``_DeadlockError``
# (module-lock ABBA) or report partially initialized modules.
#
# The plain UI path does NOT import the SDK here — it launches the Node UI and
# delegates to ``siada.entrypoint.siadahub`` / ``siada.acp_server.main``, which
# carry the same gate in their own processes. Gating unconditionally would add
# ~1 s to every ``siada-cli`` launch for nothing.
# ---------------------------------------------------------------------------
if "--acp" in sys.argv:
    from siada.foundation.sdk_patches import (
        ensure_agents_imported as _ensure_sdk,
    )

    _ensure_sdk()

# ACP agents (spawned by the chrome-acp proxy as node -> cmd -> python with
# piped stdio) deadlock when numpy's native extension is first loaded lazily
# from the event-loop thread mid-turn (Windows loader lock). Preload the
# holographic provider — which transitively imports numpy — up front while the
# process is still single-threaded.
if "--acp" in sys.argv:
    try:
        import siada.services.memory.holographic.provider as _holo_preload  # noqa: F401
    except Exception:
        pass


from siada.foundation.logging import logger, remove_console_handler, get_log_directory  # noqa: E402
from siada.entrypoint.env_assignments import parse_env_assignments as _parse_env_assignments  # noqa: E402



from siada.foundation.node_runtime import NODE_VERSION as _NODE_VERSION


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
        workspace = self.config.get("workspace")
        if workspace:
            args.extend(["--workspace", self._quote_arg(str(workspace))])
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

        return args


    def _find_local_node(self) -> str:
        """Resolve an installed runtime without downloading at UI startup."""
        from siada.foundation.node_runtime import find_node

        try:
            return find_node(_expected_node_path())
        except FileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc

    def _setup_node_env(self) -> Dict[str, str]:
        """Setup environment variables for Node.js execution."""
        env = os.environ.copy()
        # Credentials supplied with --set-env travel through the environment,
        # rather than the UI and backend subprocess command lines.
        assignments = _parse_env_assignments(self.config.get("args"))
        env.update(assignments)
        # Send names only so the backend can preserve explicit CLI values
        # while loading .env files, without duplicating credential payloads.
        if assignments:
            env["_SIADA_CLI_ENV_KEYS"] = json.dumps(list(assignments))
        else:
            env.pop("_SIADA_CLI_ENV_KEYS", None)
        venv_dir = Path(sys.executable).parent.parent

        # Snapshot the user's original env *before* any siada-specific
        # injection below, so agent-run shell commands (run_cmd) can restore
        # a clean user environment at the execution boundary
        # (see siada.foundation.shell_env.make_user_shell_env).  JSON null
        # means "was unset", which the restore side turns into "delete the
        # variable".
        env["SIADA_USER_ENV"] = json.dumps(
            {
                "PATH": env.get("PATH"),
                "PYTHONPATH": env.get("PYTHONPATH"),
                "NVM_DIR": env.get("NVM_DIR"),
                "PYTHONIOENCODING": env.get("PYTHONIOENCODING"),
                "PYTHONUNBUFFERED": env.get("PYTHONUNBUFFERED"),
            }
        )

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
        # Share the resolved root, including writable-directory fallbacks.
        env["SIADA_CLI_LOG_DIR"] = get_log_directory()
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
    node = _expected_node_path()
    raise RuntimeError(
        f"Node.js {_NODE_VERSION} not found at {node}.\n"
        "Install a maintained Node.js LTS release from https://nodejs.org/ "
        "and add its bin directory to PATH."
    )


# ---------------------------------------------------------------------------
# First-run initialization
#
# The launcher never manages other processes.  The proactive daemon belongs to
# ``siada.agent_hub.proactive.daemon_manager.DaemonManager`` and its explicit
# backend commands (``--stop-daemon`` / ``--restart-daemon`` /
# ``--daemon-status``); normal startup lets the backend start it, honoring
# ``--no-daemon`` (see ``siadahub.main()``).  The version-upgrade path used to
# kill every matching ``siada.agent_hub.proactive`` process from here and
# respawn one — racing the daemon's own auto-updater and, because the scan
# matches the whole process table, reaching processes the launcher does not
# own.  That must never happen on a plain CLI start.
# ---------------------------------------------------------------------------


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
    """Return the legacy runtime location for existing installations."""
    from siada.foundation.node_runtime import legacy_node

    return legacy_node()


def _run_first_time_setup_if_needed() -> None:
    """Record the initialized version and check the UI bundle once per version.

    Deliberately limited to local bookkeeping: the launcher neither manages
    other processes (see the note above) nor installs toolchains.  Node.js is
    resolved from the venv install layout or from ``PATH`` at UI launch time
    (see ``UILauncher._find_local_node``), and a missing Node fails with the
    launcher's install guidance instead of an implicit download.
    """
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

    if marker_file.exists():
        try:
            if marker_file.read_text().strip() == current_version:
                return
        except OSError:
            pass

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

    # Browser proxy (chrome-acp) management — handled by the backend's
    # handle_special_commands(); must not launch the Node UI.
    "--browser-setup",
    "--browser-start",
    "--browser-stop",
    "--browser-restart",
    "--browser-status",
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
    parser.add_argument(
        "--workspace", "-w", nargs="?", const=".", default=os.environ.get("SIADA_WORKSPACE")
    )
    temp_args, _ = parser.parse_known_args()

    workspace = os.path.abspath(temp_args.workspace or os.getcwd())
    # Git discovery is for environment loading, not workspace selection.
    git_root = _fast_git_root(workspace)
    return workspace, git_root


def _parse_args(git_root):
    """Build the full argument parser and parse sys.argv.

    This deliberately runs *before* ``_run_first_time_setup_if_needed()``:
    ``--version`` is an argparse ``action="version"`` and ``-h``/``--help`` are
    the parser's default help action, so they print and exit here — a plain
    version/help query never reaches the one-time setup (no marker file, no
    bundle check), the backend or the Node UI.  Argparse errors behave the
    same way: an invalid invocation exits before any setup work.
    """
    from siada.entrypoint.args_parser.args import get_parser

    parser = get_parser(default_config_files=[], git_root=git_root)
    args, _ = parser.parse_known_args()
    try:
        _parse_env_assignments(args)
    except ValueError as exc:
        parser.error(str(exc))
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
            message = f"Error: Session not found: {resume_id}"
            logger.error(message)
            # The launcher removes console logging before IO/UI initialization.
            print(message, file=sys.stderr)
            return 1

        origin_root = session_info.project_root or ""
        if (
            origin_root
            and origin_root != "Unknown"
            and os.path.normpath(origin_root) != os.path.normpath(workspace)
        ):
            message = f"Session belongs to workspace: {origin_root}"
            hint = (
                f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}"
            )
            logger.error(message)
            logger.error(hint)
            print(message, file=sys.stderr)
            print(hint, file=sys.stderr)
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
    if "--browser-login" in sys.argv:
        remove_console_handler()
        from siada.entrypoint.browser_login import main as browser_login_main
        return browser_login_main(reconfigure="--reconfigure" in sys.argv)
    if "--browser-check" in sys.argv:
        remove_console_handler()
        from siada.entrypoint.browser_check import main as browser_check_main

        return browser_check_main()
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

    if _BACKEND_ONLY_ARGS.intersection(sys.argv):
        return _run_backend()

    workspace, git_root = _resolve_workspace()
    logger.debug(f"[PERF][launcher] resolve_workspace done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    # Parse before any one-time setup work: argparse answers ``--version`` /
    # ``--help`` / ``-h`` (print and exit) and reports invalid invocations here,
    # so a plain version/help query never writes to ``~/.siada-cli``, checks the
    # bundle or launches the Node UI.  Only then does the version-change setup
    # run, still before the UI backend is started (see ``_parse_args``).
    args = _parse_args(git_root)
    logger.debug(f"[PERF][launcher] parse_args done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    _run_first_time_setup_if_needed()
    logger.debug(f"[PERF][launcher] first_time_setup done | +{(_time.perf_counter() - _t0)*1000:.0f}ms")

    if rc := _check_resume_workspace(workspace, args):
        return rc

    if hasattr(args, "ui") and not args.ui:
        from siada.entrypoint.siadahub import main as siadahub_main

        return siadahub_main()

    logger.debug(f"[PERF][launcher] about to _launch_ui | +{(_time.perf_counter() - _t0)*1000:.0f}ms")
    return _launch_ui(workspace, args)


if __name__ == "__main__":
    main()
