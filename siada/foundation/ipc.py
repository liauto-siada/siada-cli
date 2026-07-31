"""Cross-platform IPC utilities for daemon <-> siadahub communication.

Uses multiprocessing.connection which auto-adapts:
- macOS/Linux: Unix Domain Socket (AF_UNIX)
- Windows: Named Pipe
"""

import sys
from pathlib import Path

from siada.foundation.constants import SIADA_HOME

# Shared authkey for connection authentication
IPC_AUTHKEY = b"siada-daemon-ipc-v1"


def get_ipc_address() -> str:
    """Return the platform-adaptive IPC address.

    - Windows: Named Pipe path
    - macOS/Linux: Unix Domain Socket path
    """
    if sys.platform == "win32":
        return r"\\.\pipe\siada-daemon"
    else:
        return str(SIADA_HOME / "daemon.sock")


def cleanup_ipc_address() -> None:
    """Remove stale socket file (Unix only). No-op on Windows."""
    if sys.platform == "win32":
        return
    sock_path = Path(get_ipc_address())
    if sock_path.exists():
        try:
            sock_path.unlink()
        except OSError:
            pass