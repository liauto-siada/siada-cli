"""Daemon process manager."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from siada.foundation.logging import logger


class DaemonManager:
    """Manages daemon process lifecycle."""

    def __init__(self, pid_file: Path, daemon_script: Path):
        """
        Initialize daemon manager.

        Args:
            pid_file: Path to PID file (unused, kept for compatibility)
            daemon_script: Path to daemon entry script
        """
        self.daemon_script = daemon_script

    def _find_daemon_process(self) -> Optional[int]:
        """
        通过进程命令行查找守护进程。

        Returns:
            守护进程PID，如果不存在则返回None
        """
        import psutil

        try:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline')
                    if cmdline and 'siada.agent_hub.proactive' in ' '.join(cmdline):
                        return proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None
        except Exception:
            return None

    def is_running(self) -> bool:
        """
        Check if daemon is running.

        Returns:
            True if daemon is running, False otherwise
        """
        return self._find_daemon_process() is not None

    def get_pid(self) -> Optional[int]:
        """
        Get daemon PID if running.

        Returns:
            Process ID if running, None otherwise
        """
        return self._find_daemon_process()

    def start_daemon(self) -> bool:
        """
        Start daemon process in background.

        Returns:
            True if started successfully, False if already running or failed

        Raises:
            RuntimeError: If daemon script doesn't exist
        """
        # Check if already running
        if self.is_running():
            return False

        # Verify daemon script exists
        if not self.daemon_script.exists():
            raise RuntimeError(f"Daemon script not found: {self.daemon_script}")

        try:
            # Start daemon as background process using python -m to support package imports
            # Uses __main__.py in the proactive package
            # - stdout/stderr redirected to avoid blocking
            # - detached from parent process
            _popen_kwargs: dict = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                # start_new_session is a POSIX-only flag and is silently ignored on
                # Windows. Use creation flags instead to suppress the console
                # window that would otherwise pop up.
                #
                # NOTE: do NOT add DETACHED_PROCESS here. Per Microsoft's
                # CreateProcess docs, CREATE_NO_WINDOW is ignored when combined
                # with DETACHED_PROCESS, and when the parent has no console
                # (e.g. launched from an Electron/GUI host) DETACHED_PROCESS
                # actually causes Windows to allocate a fresh conhost window
                # for the child python.exe — exactly the empty black popup we
                # want to avoid. CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP +
                # DEVNULL stdio + close_fds is sufficient for the daemon to
                # outlive the parent and stay headless.
                _popen_kwargs["creationflags"] = (
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                )
                _popen_kwargs["close_fds"] = True
            else:
                _popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(
                [sys.executable, "-m", "siada.agent_hub.proactive"],
                **_popen_kwargs,
            )

            # Wait a bit to ensure process starts
            time.sleep(0.5)

            # Verify process is still running
            if process.poll() is None:
                # Process started successfully
                return True
            else:
                return False

        except Exception as e:
            raise RuntimeError(f"Failed to start daemon: {e}") from e

    def stop_daemon(self, timeout: int = 10) -> bool:
        """
        Stop daemon process gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown before forcing

        Returns:
            True if stopped successfully, False if not running
        """
        pid = self.get_pid()
        if pid is None:
            return False

        try:
            # Send SIGTERM for graceful shutdown
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                return False

            # Wait for process to terminate
            for _ in range(timeout * 10):  # Check every 0.1s
                try:
                    os.kill(pid, 0)  # Check if process still exists
                    time.sleep(0.1)
                except ProcessLookupError:
                    # Process terminated
                    return True

            # Process didn't terminate - force kill
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            time.sleep(0.5)
            return True

        except Exception:
            return False

    def ensure_daemon(self) -> tuple[bool, Optional[int]]:
        """
        Ensure daemon is running, start if necessary.

        Returns:
            Tuple of (was_started, pid)
            - was_started: True if daemon was triggered to start, False if already running
            - pid: Current daemon PID if already running, None if just started (PID pending)
        """
        pid = self.get_pid()
        if pid is not None:
            return False, pid

        # Start daemon
        success = self.start_daemon()
        if not success:
            return False, None

        # Wait for process to appear in process list
        for _ in range(50):  # Wait up to 5 seconds
            pid = self.get_pid()
            if pid is not None:
                return True, pid
            time.sleep(0.1)

        logger.warning("Proactive daemon started but not found in process list within 5 seconds")
        return True, None
