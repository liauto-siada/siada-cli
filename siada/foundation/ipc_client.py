"""IPC client for siadahub processes to communicate with the daemon.

Provides a simple request/response API over multiprocessing.connection.Client.
Gracefully degrades when the daemon is not running.

Usage::

    from siada.foundation.ipc_client import DaemonIPCClient

    client = DaemonIPCClient()
    if client.connect():
        status = client.lark_status()
        client.disconnect()
"""

import logging
import math
import socket
import sys
import time
import uuid
from multiprocessing.connection import Client, Connection, answer_challenge, deliver_challenge
from typing import Any, Optional

from siada.foundation.ipc import IPC_AUTHKEY, get_ipc_address

logger = logging.getLogger("siada.ipc.client")


class _SocketConnection(Connection):
    """Use socket deadlines for complete multiprocessing frames, including auth.

    Polling alone bounds only the arrival of the first byte. The socket remains
    owned by this Connection, so timeout/error paths close it synchronously.
    """

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        super().__init__(sock.fileno())
        self._socket = sock
        self._deadline = deadline

    def set_deadline(self, deadline: float) -> None:
        self._deadline = deadline

    def _set_socket_timeout(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("daemon IPC deadline expired")
        self._socket.settimeout(remaining)

    def _read_with_timeout(self, _handle: int, size: int) -> bytes:
        self._set_socket_timeout()
        return self._socket.recv(size)

    def _write_with_timeout(self, _handle: int, data: bytes) -> int:
        self._set_socket_timeout()
        return self._socket.send(data)

    def _recv(self, size: int):
        return super()._recv(size, read=self._read_with_timeout)

    def _send(self, buf) -> None:
        super()._send(buf, write=self._write_with_timeout)

    def _close(self) -> None:
        self._socket.close()


def _connect_unix(address: str, timeout: float) -> Connection:
    """Bound connect and mutual authentication by one shared deadline."""
    deadline = time.monotonic() + timeout
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn = None
    try:
        sock.settimeout(timeout)
        sock.connect(address)
        conn = _SocketConnection(sock, deadline)
        answer_challenge(conn, IPC_AUTHKEY)
        deliver_challenge(conn, IPC_AUTHKEY)
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        else:
            sock.close()
        raise


class DaemonIPCClient:
    """Client for communicating with the daemon IPC server.

    Thread-safe for single-connection usage. Each siadahub instance
    should create its own client.
    """

    def __init__(self, timeout: float = 5.0) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self._conn: Optional[Any] = None
        self._timeout = timeout

    # ── Connection management ────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to the daemon IPC server.

        Returns:
            True if connected successfully, False if daemon is not available.
        """
        if self._conn is not None:
            return True

        try:
            address = get_ipc_address()
            if sys.platform == "win32":
                self._conn = Client(address, authkey=IPC_AUTHKEY)
            else:
                self._conn = _connect_unix(address, self._timeout)
            logger.debug("Connected to daemon IPC at %s", address)
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            logger.debug("Daemon IPC not available: %s", e)
            self._conn = None
            return False
        except Exception as e:
            logger.warning("Unexpected error connecting to daemon IPC: %s", e)
            self._conn = None
            return False

    def disconnect(self) -> None:
        """Close the connection to the daemon."""
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._conn is not None

    # ── Raw RPC call ─────────────────────────────────────────────────

    def call(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a request and wait for a response.

        Args:
            method: RPC method name (e.g. "lark.status")
            params: Optional parameters dict

        Returns:
            Response dict with "result" or "error" key.

        Raises:
            ConnectionError: If not connected or connection lost.
        """
        if self._conn is None:
            raise ConnectionError("Not connected to daemon IPC")

        request = {
            "method": method,
            "params": params or {},
            "id": str(uuid.uuid4())[:8],
        }

        try:
            deadline = time.monotonic() + self._timeout
            if isinstance(self._conn, _SocketConnection):
                self._conn.set_deadline(deadline)
            self._conn.send(request)
            if self._conn.poll(timeout=max(0.0, deadline - time.monotonic())):
                return self._conn.recv()
            else:
                self.disconnect()
                return {"error": "timeout waiting for response", "id": request["id"]}
        except (EOFError, BrokenPipeError, OSError) as e:
            self.disconnect()
            raise ConnectionError(f"Connection lost: {e}") from e

    # ── High-level API ───────────────────────────────────────────────

    def lark_status(self) -> Optional[dict]:
        """Query the LarkController status from daemon.

        Returns:
            Status dict with "active", "controllers" keys, or None if unavailable.
        """
        try:
            resp = self.call("lark.status")
            if "error" in resp:
                logger.warning("lark.status error: %s", resp["error"])
                return None
            return resp.get("result")
        except ConnectionError as e:
            logger.debug("lark_status failed: %s", e)
            return None

    def headroom_status(self) -> Optional[dict]:
        """Query the daemon's in-memory headroom proxy status.

        Returns:
            Status dict (status/host/port/pid), or None if the daemon is
            unreachable or reports an error.
        """
        try:
            resp = self.call("headroom.status")
            if "error" in resp:
                logger.debug("headroom.status error: %s", resp["error"])
                return None
            return resp.get("result")
        except ConnectionError as e:
            logger.debug("headroom_status failed: %s", e)
            return None

    def send_lark_notification(
        self,
        content: str,
        content_type: str = "text",
    ) -> Optional[dict]:
        """Send a notification message to Lark chat (no session history write).

        Use this for fire-and-forget notifications that don't need to appear
        in the agent's conversation context.

        Args:
            content: Message content
            content_type: Message content type (default "text")

        Returns:
            Result dict or None if unavailable.
        """
        return self._send_lark_message(content, content_type=content_type)

    def send_lark_message(
        self,
        content: str,
        session_id: str,
        content_type: str = "text",
    ) -> Optional[dict]:
        """Send a message to Lark chat AND write into the session history.

        Use this when the message should be visible to the agent in the
        next turn's conversation context.

        Args:
            content: Message content
            session_id: Source session ID (written into session history)
            content_type: Message content type (default "text")

        Returns:
            Result dict or None if unavailable.
        """
        return self._send_lark_message(content, session_id=session_id, content_type=content_type)

    def is_session_active(self, session_id: str) -> Optional[dict]:
        """Check if a session is actively controlled by IM via daemon.

        Used for stale ownership detection: when agenthub fails to acquire
        a session owned by lark, it calls this to verify the ownership
        is still valid.

        Returns:
            Dict with "daemon_alive" and "session_active" keys, or None
            if daemon IPC is unreachable (implies daemon is dead).
        """
        try:
            resp = self.call("lark.is_session_active", {"session_id": session_id})
            if "error" in resp:
                logger.warning("lark.is_session_active error: %s", resp["error"])
                return None
            return resp.get("result")
        except ConnectionError as e:
            logger.debug("is_session_active failed: %s", e)
            return None

    def _send_lark_message(
        self,
        content: str,
        session_id: Optional[str] = None,
        content_type: str = "text",
    ) -> Optional[dict]:
        """Internal: dispatch lark.send_message IPC call."""
        try:
            resp = self.call(
                "lark.send_message",
                {
                    "content": content,
                    "session_id": session_id,
                    "content_type": content_type,
                },
            )
            if "error" in resp:
                logger.warning("lark.send_message error: %s", resp["error"])
                return None
            return resp.get("result")
        except ConnectionError as e:
            logger.debug("send_lark_message failed: %s", e)
            return None

    # ── Context manager ──────────────────────────────────────────────

    def __enter__(self) -> "DaemonIPCClient":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()