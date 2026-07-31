"""Siada daemon process - Main entry point for background task discovery."""

import asyncio
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional
from typing import List, Optional

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import (
    configure_third_party_loggers,
    get_model_error_handler,
    redirect_file_handler,
    redirect_openhands_aci_logger,
)

# Registry of known IM controller classes.
# Each entry is (module_path, class_name). The daemon attempts to load
# each one and calls create_if_configured(); all that return a valid
# controller are started concurrently.
# To add a new IM platform (e.g. WeCom, DingTalk), simply append an entry here.
_IM_CONTROLLER_REGISTRY: List[tuple] = [
    ("siada.entrypoint.interaction.lark_controller", "LarkController"),
    # ("siada.entrypoint.interaction.wecom_controller", "WeComController"),
    # ("siada.entrypoint.interaction.dingtalk_controller", "DingTalkController"),
]
class SiadaDaemon:
    """Main daemon process for proactive task discovery."""

    def __init__(
        self,
        pid_file: Optional[Path] = None,
        workspace: Optional[str] = None,
    ):
        """
        Initialize daemon.

        Args:
            pid_file: Unused, kept for API compatibility
            workspace: Working directory passed to ProactiveScheduler / SiadaRunner
        """
        self.workspace = workspace or str(SIADA_HOME / "workspace" / "tmp")

        self.logger: Optional[logging.Logger] = None
        self.running = False
        self.scheduler = None
        self.auto_updater = None
        self.im_controllers: List = []  # List of active ImController instances
        self._im_loops: List = []  # Corresponding asyncio event loops
        self._im_threads: List[threading.Thread] = []  # Corresponding threads
        self._ipc_server = None  # DaemonIPCServer instance
        # In-memory headroom proxy status, queried by the CLI over IPC
        # (headroom.status). Avoids any status file on disk.
        self._headroom_status: dict = {"status": "unknown"}
        self._stop_event = threading.Event()

    def _find_existing_daemon(self) -> Optional[int]:
        """
        通过进程命令行查找已存在的守护进程。

        使用 psutil 扫描所有进程，匹配命令行包含 'siada.agent_hub.proactive' 的进程。
        对僵尸/死掉的残留进程会主动杀死并清理。

        Returns:
            已存在的守护进程PID，如果不存在则返回None
        """
        import psutil
        import datetime

        current_pid = os.getpid()
        parent_pid = os.getppid()

        try:
            for proc in psutil.process_iter(['pid', 'cmdline', 'status']):
                try:
                    cmdline = proc.info.get('cmdline')
                    if cmdline and 'siada.agent_hub.proactive' in ' '.join(cmdline):
                        pid = proc.info['pid']
                        if pid == current_pid:
                            continue
                        if pid == parent_pid:
                            continue

                        # Gather diagnostic info
                        status = proc.info.get('status', '')
                        is_alive = proc.is_running()
                        try:
                            create_time = datetime.datetime.fromtimestamp(
                                proc.create_time()
                            ).strftime('%H:%M:%S')
                        except Exception:
                            create_time = '?'

                        if not is_alive or status in (
                            psutil.STATUS_ZOMBIE,
                            psutil.STATUS_DEAD,
                            psutil.STATUS_STOPPED,
                        ):
                            print(
                                f"[daemon] Cleaning stale process PID={pid} "
                                f"(status={status}, created={create_time})",
                                file=sys.stderr,
                            )
                            try:
                                proc.kill()
                                proc.wait(timeout=3)
                            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                                pass
                            continue

                        # Healthy running daemon found
                        print(
                            f"[daemon] Found running daemon: PID={pid}, "
                            f"started={create_time}, status={status}",
                            file=sys.stderr,
                        )
                        return pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None

        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to check existing daemon: {e}")
            return None

    def setup_logging(self) -> None:
        """Setup daemon logging - writes to siada_daemon.log.

        Redirects the shared file handler singleton from siada_cli.log
        to siada_daemon.log so the daemon process writes to its own log
        file, avoiding cross-process rotation conflicts with TUI.

        Two-level setup:
        1. siada.daemon  – daemon's own logger, propagate=False (no double-write)
        2. siada         – top-level namespace logger; captures all siada.*
                           sub-loggers that have no handler of their own, e.g.
                           siada.agent_hub.proactive.scheduler.
                           siada.api / siada.daemon both have propagate=False so
                           they are NOT affected by this handler.
        """
        # Suppress noisy third-party DEBUG logs (httpx/httpcore/LiteLLM/git/...)
        # and LiteLLM's own verbose stream handler. The daemon is spawned via
        # ``python -m siada.agent_hub.proactive`` which does NOT go through
        # ``siadahub.py``'s ``_configure_litellm_logging`` path, so we must
        # invoke these ourselves – otherwise e.g. ``LiteLLM:DEBUG ...`` and
        # ``DEBUG:httpcore.connection:connect_tcp.started ...`` leak to stderr
        # once any module (skill marketplace fetch, litellm import, GitPython)
        # lands in the daemon process.
        try:
            configure_third_party_loggers()
        except Exception:  # noqa: BLE001 – logging setup must never crash daemon
            pass
        try:
            redirect_openhands_aci_logger()
        except Exception:  # noqa: BLE001
            pass
        try:
            from siada.entrypoint import _configure_litellm
            _configure_litellm()
        except Exception:  # noqa: BLE001
            pass

        # Force root logger to INFO in the daemon so an inherited ``DEBUG=1``
        # environment variable (read by ``siada.foundation.logging``) cannot
        # cause the root ``lastResort`` handler to dump DEBUG records from
        # third-party libraries to stderr.
        logging.getLogger().setLevel(logging.INFO)

        # Redirect the singleton file handler to daemon-specific log file.
        # This replaces the handler in ALL loggers that already reference
        # the old siada_cli.log handler (e.g. siada.api, siada namespace).
        file_handler = redirect_file_handler('siada_daemon.log')
        error_file_handler = get_model_error_handler()

        # 1. Daemon-specific logger
        self.logger = logging.getLogger("siada.daemon")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_file_handler)
        self.logger.propagate = False  # avoid double-write via siada logger

        # 2. siada namespace logger – catches scheduler, etc.
        siada_logger = logging.getLogger("siada")
        siada_logger.setLevel(logging.INFO)
        if not siada_logger.handlers:
            siada_logger.addHandler(file_handler)
            siada_logger.addHandler(error_file_handler)
        # propagate=True (default) is fine; root logger has no handlers

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown.

        NOTE: In ACP mode the StdinInterruptMonitor installs a custom
        debounced SIGINT handler that raises KeyboardInterrupt.  We must
        NOT overwrite it here, otherwise Ctrl+C will trigger daemon
        shutdown instead of interrupting the running agent.
        """

        def handle_sigterm(signum, frame):
            """Handle SIGTERM signal."""
            if self.logger:
                self.logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.shutdown()

        # Register signal handlers
        signal.signal(signal.SIGTERM, handle_sigterm)

        # Only register SIGINT handler when NOT in ACP mode.
        # In ACP mode, stdin_interrupt_monitor has already installed a
        # debounced SIGINT handler; overwriting it would break Ctrl+C
        # interrupt-then-exit flow.
        from siada.io.stdin_interrupt_monitor import is_monitor_active
        if is_monitor_active():
            if self.logger:
                self.logger.info(
                    "Signal handlers registered (SIGINT skipped – "
                    "StdinInterruptMonitor is active)"
                )
        else:
            signal.signal(signal.SIGINT, handle_sigterm)
            if self.logger:
                self.logger.info("Signal handlers registered (including SIGINT)")

    def initialize_components(self) -> None:
        """Initialize ProactiveScheduler with config loaded from conf.yaml."""
        if self.logger:
            self.logger.info("Initializing daemon components...")

        from siada.config.config_loader import load_conf
        from siada.agent_hub.proactive.scheduler import ProactiveScheduler
        from siada.services.auto_update import DaemonAutoUpdater

        config = load_conf()
        self.scheduler = ProactiveScheduler(
            config=config.proactive_config,
            workspace=self.workspace,
        )
        self.auto_updater = DaemonAutoUpdater(
            config=config.auto_update_config,
            stop_event=self._stop_event,
        )

        # Initialize all configured IM controllers (Lark, WeCom, DingTalk, etc.)
        self._initialize_im_controllers()

        # Initialize IPC server for siadahub <-> daemon communication
        self._initialize_ipc_server()

        if self.logger:
            self.logger.info("Components initialized")

    def _check_venv_health(self) -> None:
        """Warn loudly when the running venv path is unhealthy.

        Specifically detects the broken-symlink case: ``sys.executable`` lives
        under a path that walks through a symlink whose target no longer
        exists.  This is non-fatal for already-loaded modules but guarantees
        future failures (auto-update clone, lazy imports, subprocess spawning).
        """
        try:
            exe_path = Path(sys.executable)
            # `Path.resolve(strict=True)` raises if any component along the way
            # cannot be resolved (incl. broken symlinks anywhere in the chain).
            exe_path.resolve(strict=True)
            # Also verify the venv root walks cleanly.
            venv_root = exe_path.parent.parent
            venv_root.resolve(strict=True)
        except FileNotFoundError as exc:
            msg = (
                f"Daemon venv appears broken: {exc}. "
                f"This usually means a symlink (e.g. siada_cli_venv_*) points "
                f"to a versioned directory that no longer exists. "
                f"Auto-update will be skipped and lazy imports will fail. "
                f"Please re-run the install script to repair the venv:\n"
                f"  curl -s https://bj.bcebos.com/prod-cnhb01-siada/cli-install/prod/remote_install.sh | sh"
            )
            if self.logger:
                self.logger.error(msg)
            else:
                print(msg, file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — health check must never abort startup
            if self.logger:
                self.logger.warning(
                    "Daemon venv health check raised unexpectedly (non-fatal): %s",
                    exc,
                )

    def _initialize_im_controllers(self) -> None:
        """Try to initialize IM controllers from the registry.

        Iterates through _IM_CONTROLLER_REGISTRY, attempting to load each
        controller class and call its create_if_configured() factory method.
        All controllers that return a non-None instance are collected.
        """
        import importlib

        for module_path, class_name in _IM_CONTROLLER_REGISTRY:
            try:
                module = importlib.import_module(module_path)
                controller_cls = getattr(module, class_name)
                controller = controller_cls.create_if_configured()
                if controller is not None:
                    self.im_controllers.append(controller)
                    if self.logger:
                        self.logger.info(f"IM controller initialized: {class_name}")
            except ImportError as e:
                if self.logger:
                    self.logger.debug(f"IM controller {class_name} not available: {e}")
            except RuntimeError as e:
                # Config validation errors are non-fatal for individual controllers
                if self.logger:
                    self.logger.warning(f"IM controller {class_name} config error: {e}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to initialize IM controller {class_name}: {e}")
                # Non-fatal: try next controller

        if not self.im_controllers and self.logger:
            self.logger.debug("No IM controllers configured, skipping")

    def _initialize_ipc_server(self) -> None:
        """Initialize the IPC server for siadahub communication."""
        if self._ipc_server is not None:
            # Idempotent: may be brought up early (before _start_headroom) so
            # the CLI can query authoritative headroom status without blocking.
            return
        try:
            from siada.agent_hub.proactive.ipc_server import DaemonIPCServer

            self._ipc_server = DaemonIPCServer(self)
            if self.logger:
                self.logger.info("IPC server initialized")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to initialize IPC server: {e}")

    def start(self) -> bool:
        """
        Start daemon process.

        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Setup logging first
            self.setup_logging()

            if self.logger:
                self.logger.info("Starting Siada daemon...")

            # Defensive venv health check.  If the running venv is reachable
            # only via a broken symlink (e.g. the underlying versioned dir was
            # deleted), every later subprocess / lazy import will mysteriously
            # fail with `cp: stat`, `uv: No virtual environment` or
            # `ModuleNotFoundError`.  Detect it once at startup and emit a
            # single actionable error instead of a death-by-a-thousand-cuts.
            self._check_venv_health()

            # Check if already running by scanning process list
            existing_pid = self._find_existing_daemon()
            if existing_pid is not None:
                if self.logger:
                    self.logger.warning(f"Daemon already running (PID: {existing_pid})")
                return False

            # Setup signal handlers
            self.setup_signal_handlers()

            # Bring the IPC server up EARLY (before the rest of init) so the CLI
            # can query the authoritative headroom status as soon as the daemon
            # process is alive, instead of blocking on a cold daemon boot.
            self._set_headroom_status("starting")
            self._initialize_ipc_server()
            if self._ipc_server:
                self._ipc_server.start()

            # Start headroom proxy early (daemon owns its lifecycle) so the CLI's
            # status query resolves quickly to running / unavailable.
            self._start_headroom()

            # Initialize components
            self.initialize_components()

            # Start scheduler
            if self.scheduler:
                self.scheduler.start()
                if self.logger:
                    self.logger.info("Scheduler started")

            if self.auto_updater:
                self.auto_updater.start()
                if self.logger:
                    self.logger.info("Auto-updater started")

            # Start IPC server for siadahub communication
            if self._ipc_server:
                self._ipc_server.start()
                if self.logger:
                    self.logger.info("IPC server started")

            # Start all IM controllers (each in its own async event loop thread)
            for controller in self.im_controllers:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=self._run_im_loop, args=(loop, controller), daemon=True
                )
                self._im_loops.append(loop)
                self._im_threads.append(thread)
                thread.start()
                if self.logger:
                    self.logger.info(
                        f"IM controller {controller.__class__.__name__} started in background thread"
                    )

            # Enter main loop
            self.running = True
            if self.logger:
                self.logger.info("Daemon started, entering main loop")

            self.run_loop()

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to start daemon: {e}", exc_info=True)
            self.cleanup()
            return False

    def _start_headroom(self) -> None:
        """Start the headroom proxy if enabled in conf.yaml.

        The daemon is the SOLE owner of the proxy lifecycle: it spawns the
        proxy here and terminates it in shutdown(). CLI processes only connect
        to it (env injection) — they never spawn or kill it.

        If host:port is already occupied, ``HeadroomProxyManager.start()``
        itself decides whether to adopt it: it probes ``/health`` and compares
        the occupant's upstream URLs (anthropic/openai/gemini) against our
        hard-coded li-mate gateway config. A match (most commonly a proxy
        siada itself started in a previous run, e.g. after a daemon crash that
        skipped cleanup) is adopted without spawning or killing anything; a
        mismatch is refused and reported as ``"port_conflict"``.
        """
        self._headroom_manager = None
        try:
            import os
            import shutil
            from siada.config.config_loader import load_conf
            from siada.internal.services.headroom_proxy_manager import (
                HeadroomProxyManager, HeadroomProxyConfig, LoggerIO,
            )
            hc = getattr(load_conf(), "headroom_config", None)
            env_on = os.environ.get("SIADA_HEADROOM_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
            if hc is None or (not getattr(hc, "enabled", False) and not env_on):
                # Headroom not desired.
                self._set_headroom_status("disabled")
                return
            host = getattr(hc, "host", "127.0.0.1")
            port = getattr(hc, "port", 8787)
            if shutil.which("headroom") is None:
                self._set_headroom_status("not_installed", host=host, port=port)
                if self.logger:
                    self.logger.warning("[headroom] `headroom` not found on PATH; skipping proxy startup")
                return
            cfg = HeadroomProxyConfig(
                enabled=True, host=hc.host, port=hc.port, budget=hc.budget,
                budget_period=hc.budget_period, telemetry=hc.telemetry,
                startup_timeout=hc.startup_timeout,
            )
            mgr = HeadroomProxyManager(cfg)
            # start() handles the "port already in use" case itself: it will
            # adopt a pre-existing proxy whose /health upstream config matches
            # ours (pid recorded as external_pid, never spawned/killed by us),
            # or refuse and set last_failure_reason="port_conflict" otherwise.
            if mgr.start(LoggerIO()):
                self._headroom_manager = mgr
                pid = mgr.owned_pid or mgr.external_pid
                self._set_headroom_status("running", host=cfg.host, port=cfg.port, pid=pid)
            else:
                reason = mgr.last_failure_reason or "error"
                self._set_headroom_status(reason, host=cfg.host, port=cfg.port)
                if self.logger:
                    self.logger.warning(
                        f"[headroom] failed to start/adopt proxy at {cfg.host}:{cfg.port} "
                        f"(reason={reason})"
                    )
        except Exception as e:
            self._set_headroom_status("error")
            if self.logger:
                self.logger.error(f"[headroom] failed to start proxy: {e}", exc_info=True)


    def _set_headroom_status(self, status, host=None, port=None, pid=None):
        """Record the headroom proxy status in memory (queried over IPC).

        status is one of: running | not_installed | port_conflict | error |
        disabled | stopped | unknown. The CLI reads this via IPC
        (headroom.status) so it can fast-fail on unavailable states instead of
        blocking, and connect to the exact host/port the daemon chose.
        """
        import time
        self._headroom_status = {
            "status": status,
            "host": host,
            "port": port,
            "pid": pid,
            "updated_at": time.time(),
        }

    def get_headroom_status(self) -> dict:
        """Return a copy of the current in-memory headroom status (for IPC)."""
        return dict(getattr(self, "_headroom_status", None) or {"status": "unknown"})

    def _run_im_loop(self, loop, controller) -> None:
        """Run an IM controller's async event loop in a background thread.

        The loop must keep running after start() so that background tasks
        (message_loop, agent execution, etc.) can continue to process.
        """
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(controller.start())
            loop.run_forever()
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"IM controller {controller.__class__.__name__} loop error: {e}",
                    exc_info=True,
                )
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def run_loop(self) -> None:
        """Block the main thread until shutdown() signals the stop event."""
        try:
            self._stop_event.wait()
        except KeyboardInterrupt:
            if self.logger:
                self.logger.info("Received keyboard interrupt")
            self.shutdown()

    def shutdown(self) -> None:
        """Shutdown daemon gracefully."""
        if self.logger:
            self.logger.info("Shutting down daemon...")

        # Unblock run_loop and mark as stopped
        self._stop_event.set()
        self.running = False

        # Stop all IM controllers
        for controller, loop in zip(self.im_controllers, self._im_loops):
            if not controller.is_running:
                continue
            try:
                if not loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        controller.stop(), loop
                    ).result(timeout=5)
                    loop.call_soon_threadsafe(loop.stop)
                if self.logger:
                    self.logger.info(f"IM controller {controller.__class__.__name__} stopped")
            except Exception as e:
                if self.logger:
                    self.logger.warning(
                        f"Error stopping IM controller {controller.__class__.__name__}: {e}"
                    )

        # Stop IPC server
        if self._ipc_server:
            self._ipc_server.stop()
            if self.logger:
                self.logger.info("IPC server stopped")

        if self.auto_updater:
            self.auto_updater.stop()
            if self.logger:
                self.logger.info("Auto-updater stopped")

        # Stop scheduler
        if self.scheduler:
            self.scheduler.stop()
            if self.logger:
                self.logger.info("Scheduler stopped")

        # Release all IM session ownership to prevent stale locks
        self._release_im_ownership()

        # Stop headroom proxy (daemon owns its lifecycle)
        _hm = getattr(self, "_headroom_manager", None)
        if _hm is not None:
            try:
                _hm.stop()
                if self.logger:
                    self.logger.info("[headroom] proxy stopped successfully")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[headroom] error stopping proxy: {e}")

        # Mark the proxy as stopped so a querying CLI does not try to connect
        # to a proxy that is going away.
        try:
            self._set_headroom_status("stopped")
        except Exception:
            pass

        # Cleanup
        self.cleanup()

        if self.logger:
            self.logger.info("Daemon shutdown complete")

    def _release_im_ownership(self) -> None:
        """Release all IM-owned session locks on shutdown."""
        if not self.im_controllers:
            return

        try:
            from siada.utils import DirectoryUtils
            from siada.session.ownership import SessionOwnershipManager

            for controller in self.im_controllers:
                try:
                    workspace = controller.workspace or self.workspace
                    sessions_base = Path(DirectoryUtils.get_global_sessions_dir(workspace))
                    released = SessionOwnershipManager.release_all_by_owner(
                        sessions_base, controller.owner_type
                    )
                    if released and self.logger:
                        self.logger.info(
                            f"Released {released} session ownership(s) on shutdown "
                            f"(owner={controller.owner_type.value})"
                        )
                except Exception as e:
                    if self.logger:
                        self.logger.warning(
                            f"Error releasing ownership for "
                            f"{controller.__class__.__name__}: {e}"
                        )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Error releasing IM ownership on shutdown: {e}")

    def cleanup(self) -> None:
        """Cleanup resources."""
        # Close log handlers
        if self.logger:
            for handler in self.logger.handlers:
                handler.close()


def main():
    """Entry point for daemon process."""
    daemon = SiadaDaemon()
    success = daemon.start()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
