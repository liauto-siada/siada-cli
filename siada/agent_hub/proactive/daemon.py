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
from siada.foundation.logging import get_file_handler, get_model_error_handler

# Registry of known IM controller classes.
# Each entry is (module_path, class_name). The daemon attempts to load
# each one and calls create_if_configured(); all that return a valid
# controller are started concurrently.
# To add a new IM platform (e.g. WeCom, DingTalk), simply append an entry here.
_IM_CONTROLLER_REGISTRY: List[tuple] = [
    ("siada.entrypoint.interaction.feishu_controller", "LarkController"),
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
        self.im_controllers: List = []  # List of active ImController instances
        self._im_loops: List = []  # Corresponding asyncio event loops
        self._im_threads: List[threading.Thread] = []  # Corresponding threads
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
        """Setup daemon logging - writes to shared siada_cli.log.

        Two-level setup:
        1. siada.daemon  – daemon's own logger, propagate=False (no double-write)
        2. siada         – top-level namespace logger; captures all siada.*
                           sub-loggers that have no handler of their own, e.g.
                           siada.agent_hub.proactive.scheduler.
                           siada.api / siada.daemon both have propagate=False so
                           they are NOT affected by this handler.
        """
        # Shared file handler (siada_cli.log)
        file_handler = get_file_handler()
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

        config = load_conf()
        self.scheduler = ProactiveScheduler(
            config=config.proactive_config,
            workspace=self.workspace,
        )

        # Initialize all configured IM controllers (Lark, WeCom, DingTalk, etc.)
        self._initialize_im_controllers()

        if self.logger:
            self.logger.info("Components initialized")

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

            # Check if already running by scanning process list
            existing_pid = self._find_existing_daemon()
            if existing_pid is not None:
                if self.logger:
                    self.logger.warning(f"Daemon already running (PID: {existing_pid})")
                return False

            # Setup signal handlers
            self.setup_signal_handlers()

            # Initialize components
            self.initialize_components()

            # Start scheduler
            if self.scheduler:
                self.scheduler.start()
                if self.logger:
                    self.logger.info("Scheduler started")

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

        # Stop scheduler
        if self.scheduler:
            self.scheduler.stop()
            if self.logger:
                self.logger.info("Scheduler stopped")

        # Release all IM session ownership to prevent stale locks
        self._release_im_ownership()
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
