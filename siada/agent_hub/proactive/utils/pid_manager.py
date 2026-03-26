"""PID file management for daemon process."""

import os
import signal
from pathlib import Path
from typing import Optional


class PIDManager:
    """Manages PID file for daemon process tracking."""

    def __init__(self, pid_file: Path):
        """
        Initialize PID manager.

        Args:
            pid_file: Path to PID file
        """
        self.pid_file = pid_file

    def write_pid(self, pid: int) -> None:
        """
        Write PID to file atomically.

        Args:
            pid: Process ID to write

        Raises:
            IOError: If file write fails
        """
        # Create parent directory if not exists
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write using temp file + rename
        temp_file = self.pid_file.with_suffix(".tmp")
        try:
            temp_file.write_text(str(pid))
            temp_file.rename(self.pid_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise IOError(f"Failed to write PID file: {e}") from e

    def read_pid(self) -> Optional[int]:
        """
        Read PID from file.

        Returns:
            Process ID if file exists and valid, None otherwise
        """
        if not self.pid_file.exists():
            return None

        try:
            content = self.pid_file.read_text().strip()
            return int(content)
        except (ValueError, IOError):
            return None

    def remove_pid(self) -> None:
        """Remove PID file if exists."""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                pass  # Ignore errors during cleanup

    def is_process_running(self, pid: int) -> bool:
        """
        Check if process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        if pid <= 0:
            return False

        try:
            # Send signal 0 to check if process exists
            # This doesn't actually send a signal, just checks permissions
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # Process does not exist
            return False
        except PermissionError:
            # Process exists but we don't have permission (still running)
            return True
        except Exception:
            return False

    def get_running_pid(self) -> Optional[int]:
        """
        Get PID if daemon is running.

        Returns:
            Process ID if daemon is running, None otherwise
        """
        pid = self.read_pid()
        if pid is None:
            return None

        if self.is_process_running(pid):
            return pid

        # PID file exists but process is not running - clean up
        self.remove_pid()
        return None

    def send_signal(self, pid: int, sig: signal.Signals) -> bool:
        """
        Send signal to process.

        Args:
            pid: Process ID
            sig: Signal to send

        Returns:
            True if signal sent successfully, False otherwise
        """
        try:
            os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
