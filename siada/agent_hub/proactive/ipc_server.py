"""Daemon-side IPC server for siadahub <-> daemon communication.

Accepts multiple concurrent clients via multiprocessing.connection.Listener.
Each client is served in a dedicated thread.

Protocol:
  Request:  {"method": "lark.status", "params": {...}, "id": "..."}
  Response: {"result": {...}, "id": "..."} or {"error": "...", "id": "..."}
"""

import logging
import threading
import uuid
from multiprocessing.connection import Listener
from typing import TYPE_CHECKING, Any, Callable, Optional

from siada.foundation.ipc import IPC_AUTHKEY, cleanup_ipc_address, get_ipc_address

if TYPE_CHECKING:
    from siada.agent_hub.proactive.daemon import SiadaDaemon

logger = logging.getLogger("siada.daemon.ipc")

# Type alias for handler functions
HandlerFunc = Callable[[dict, "DaemonIPCServer"], dict]

# Module-level daemon reference for in-process direct access
_daemon_instance: Optional["SiadaDaemon"] = None


def _is_lark_controller(controller: Any) -> bool:
    """Return whether a controller instance is a Lark controller (direct or relay)."""
    pname = getattr(controller, "platform_name", None) or ""
    if pname.startswith("lark"):
        return True
    return controller.__class__.__name__ in {"LarkController", "RelayLarkController"}


class DaemonIPCServer:
    """Multi-client IPC server running inside the daemon process.

    Usage::

        server = DaemonIPCServer(daemon)
        server.start()   # non-blocking, spawns acceptor thread
        ...
        server.stop()
    """

    def __init__(self, daemon: "SiadaDaemon") -> None:
        global _daemon_instance
        self._daemon = daemon
        _daemon_instance = daemon
        self._listener: Optional[Listener] = None
        self._acceptor_thread: Optional[threading.Thread] = None
        self._client_threads: list[threading.Thread] = []
        self._running = False
        self._handlers: dict[str, HandlerFunc] = {}

        # Register built-in handlers
        self._register_builtin_handlers()

    # ── Handler registration ─────────────────────────────────────────

    def register_handler(self, method: str, handler: HandlerFunc) -> None:
        """Register a handler for a given RPC method name."""
        self._handlers[method] = handler

    def _register_builtin_handlers(self) -> None:
        """Register the default set of IPC method handlers."""
        self.register_handler("lark.status", _handle_lark_status)
        self.register_handler("lark.send_message", _handle_lark_send_message)
        self.register_handler("lark.is_session_active", _handle_is_session_active)
        self.register_handler("headroom.status", _handle_headroom_status)

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start accepting IPC connections (non-blocking)."""
        if self._running:
            return

        # Clean up stale socket file from previous run
        cleanup_ipc_address()

        address = get_ipc_address()
        self._listener = Listener(address, authkey=IPC_AUTHKEY)
        self._running = True

        self._acceptor_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="ipc-acceptor"
        )
        self._acceptor_thread.start()
        logger.info("IPC server started on %s", address)

    def stop(self) -> None:
        """Stop the server and close all connections."""
        if not self._running:
            return

        self._running = False

        # Close listener to unblock accept()
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass

        # Wait for acceptor thread
        if self._acceptor_thread and self._acceptor_thread.is_alive():
            self._acceptor_thread.join(timeout=3)

        # Wait for client threads
        for t in self._client_threads:
            if t.is_alive():
                t.join(timeout=2)
        self._client_threads.clear()

        # Clean up socket file
        cleanup_ipc_address()
        logger.info("IPC server stopped")

    # ── Accept loop ──────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        """Accept incoming client connections in a loop."""
        while self._running:
            try:
                conn = self._listener.accept()
                client_id = str(uuid.uuid4())[:8]
                logger.debug("IPC client connected: %s", client_id)

                t = threading.Thread(
                    target=self._handle_client,
                    args=(conn, client_id),
                    daemon=True,
                    name=f"ipc-client-{client_id}",
                )
                self._client_threads.append(t)
                t.start()
            except OSError:
                # Listener closed during shutdown
                break
            except Exception as e:
                if self._running:
                    logger.error("IPC accept error: %s", e, exc_info=True)

    # ── Per-client handler ───────────────────────────────────────────

    def _handle_client(self, conn, client_id: str) -> None:
        """Handle messages from a single client connection."""
        try:
            while self._running:
                try:
                    if not conn.poll(timeout=1.0):
                        continue
                    request = conn.recv()
                except EOFError:
                    logger.debug("IPC client disconnected: %s", client_id)
                    break
                except Exception:
                    break

                response = self._dispatch(request)
                try:
                    conn.send(response)
                except (BrokenPipeError, OSError):
                    break
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # ── Dispatch ─────────────────────────────────────────────────────

    def _dispatch(self, request: Any) -> dict:
        """Route a request dict to the registered handler."""
        if not isinstance(request, dict):
            return {"error": "invalid request: expected dict", "id": None}

        method = request.get("method", "")
        req_id = request.get("id")

        handler = self._handlers.get(method)
        if handler is None:
            return {"error": f"unknown method: {method}", "id": req_id}

        try:
            result = handler(request, self)
            return {"result": result, "id": req_id}
        except Exception as e:
            logger.error("IPC handler error for %s: %s", method, e, exc_info=True)
            return {"error": str(e), "id": req_id}

    @property
    def daemon(self) -> "SiadaDaemon":
        """Access the daemon instance (used by handlers)."""
        return self._daemon


# ═══════════════════════════════════════════════════════════════════════
# Built-in RPC handlers
# ═══════════════════════════════════════════════════════════════════════


def _handle_lark_status(request: dict, server: DaemonIPCServer) -> dict:
    """Handle 'lark.status' - query LarkController status.

    Response::

        {
            "active": true,
            "mode": "direct",
            "controllers": [
                {"class": "LarkController", "running": true, "mode": "direct"}
            ]
        }
    """
    daemon = server.daemon
    controllers_info = []

    for ctrl in daemon.im_controllers:
        if not _is_lark_controller(ctrl):
            continue

        info: dict[str, Any] = {
            "class": ctrl.__class__.__name__,
            "running": getattr(ctrl, "is_running", False),
        }
        if hasattr(ctrl, "_mode"):
            info["mode"] = ctrl._mode
        controllers_info.append(info)

    has_active = any(c.get("running") for c in controllers_info)
    return {
        "active": has_active,
        "controllers": controllers_info,
    }


def _handle_headroom_status(request: dict, server: DaemonIPCServer) -> dict:
    """Handle 'headroom.status' - return the daemon's in-memory headroom status.

    Response mirrors SiadaDaemon._headroom_status, e.g.::

        {"status": "running", "host": "127.0.0.1", "port": 8787, "pid": 1234}

    status is one of: running | not_installed | port_conflict | error |
    disabled | stopped | unknown.
    """
    daemon = server.daemon
    getter = getattr(daemon, "get_headroom_status", None)
    if callable(getter):
        try:
            return getter()
        except Exception as e:  # pragma: no cover - defensive
            return {"status": "unknown", "error": str(e)}
    return {"status": "unknown"}


def send_lark_message_direct(
    daemon: "SiadaDaemon",
    content: str,
    content_type: str = "text",
    session_id: Optional[str] = None,
) -> dict:
    """Send a message via Lark directly using the daemon's IM controllers.

    This is the core implementation shared by the IPC handler and in-process
    tools (e.g. send_daily_summary_to_lark). It finds a running LarkController
    from the daemon and schedules the message on its event loop.

    Args:
        daemon: The SiadaDaemon instance.
        content: Message text to send.
        content_type: Content type, defaults to "text".
        session_id: Optional source session id.

    Returns:
        dict with "sent" bool and optional "reason" on failure.
    """
    import asyncio

    if not content:
        return {"sent": False, "reason": "missing required param: content"}

    # Find a running LarkController and its event loop
    controller = None
    loop = None
    for ctrl, ctrl_loop in zip(daemon.im_controllers, daemon._im_loops):
        if (
            _is_lark_controller(ctrl)
            and hasattr(ctrl, "enqueue_ipc_message")
            and getattr(ctrl, "is_running", False)
        ):
            controller = ctrl
            loop = ctrl_loop
            break

    if controller is None or loop is None:
        return {"sent": False, "reason": "no active LarkController available"}

    if loop.is_closed():
        return {"sent": False, "reason": "LarkController event loop is closed"}

    # Schedule the coroutine on the controller's event loop (async return)
    try:
        future = asyncio.run_coroutine_threadsafe(
            controller.enqueue_ipc_message(
                content=content,
                content_type=content_type,
                source_session_id=session_id,
            ),
            loop,
        )
        # Wait briefly for the enqueue result (fast operation)
        result = future.result(timeout=5.0)
        return result
    except TimeoutError:
        return {"sent": False, "reason": "timeout scheduling message on controller loop"}
    except Exception as e:
        logger.error("lark.send_message dispatch error: %s", e, exc_info=True)
        return {"sent": False, "reason": str(e)}


def get_daemon_instance() -> Optional["SiadaDaemon"]:
    """Get the daemon instance stored by DaemonIPCServer.

    Returns:
        The SiadaDaemon instance if available, None otherwise.
    """
    return _daemon_instance


def _handle_lark_send_message(request: dict, server: DaemonIPCServer) -> dict:
    """Handle 'lark.send_message' - send a message via Lark.

    Expected params::

        {
            "session_id": "source-session-id",
            "content": "message text",
            "content_type": "text"
        }

    Delegates to send_lark_message_direct() which contains the core logic.
    """
    params = request.get("params", {})
    return send_lark_message_direct(
        daemon=server.daemon,
        content=params.get("content", ""),
        content_type=params.get("content_type", "text"),
        session_id=params.get("session_id"),
    )


def _handle_is_session_active(request: dict, server: DaemonIPCServer) -> dict:
    """Handle 'lark.is_session_active' - check if IM is actively controlling a session.

    Used by agenthub (CLI) to verify whether lark ownership on a session
    is stale (daemon crashed) or genuinely active. Prevents permanent
    lock-out when the daemon dies without releasing ownership.

    If this handler responds at all, the daemon is alive. The only
    remaining question is whether the session is in _active_sessions.

    Expected params::

        {"session_id": "the-session-id-to-check"}

    Response::

        {
            "daemon_alive": true,
            "session_active": true/false
        }
    """
    params = request.get("params", {})
    session_id = params.get("session_id", "")
    daemon = server.daemon

    session_active = False
    for ctrl in daemon.im_controllers:
        if not _is_lark_controller(ctrl):
            continue
        # _active_entries: task_key -> ActiveTaskEntry (unified task state)
        # Entries are cleaned up in _on_task_done, so presence implies active.
        active_entries = getattr(ctrl, "_active_entries", {})
        for _task_key, entry in active_entries.items():
            if entry.session is not None and entry.session.session_id == session_id:
                session_active = True
                break
        if session_active:
            break

    return {
        "daemon_alive": True,
        "session_active": session_active,
    }
