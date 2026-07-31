"""Protocol state machine for Siada's standard ACP server."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

JsonObject = dict[str, Any]
TurnRunner = Callable[[str, str], Iterable[JsonObject]]


@dataclass(frozen=True)
class AcpSession:
    """Minimal ACP session state owned by the server."""

    session_id: str
    cwd: str | None


class AcpServer:
    """Handle the standard ACP methods independent of a transport."""

    def __init__(self, turn_runner: TurnRunner):
        self._turn_runner = turn_runner
        self._initialized = False
        self._sessions: dict[str, AcpSession] = {}
        self._cancelled_sessions: set[str] = set()
        self._notifications: list[JsonObject] = []

    def handle(self, request: JsonObject) -> JsonObject:
        """Return the JSON-RPC response for one ACP request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if request.get("jsonrpc") != "2.0" or request_id is None:
            return self._error(request_id, -32600, "Invalid Request")

        if method == "initialize":
            return self._initialize(request_id, params)
        if method == "session/new":
            return self._new_session(request_id, params)
        if method == "session/prompt":
            return self._prompt(request_id, params)
        if method == "session/cancel":
            return self._cancel(request_id, params)
        return self._error(request_id, -32601, f"Method not found: {method}")

    def _initialize(self, request_id: int | str, params: JsonObject) -> JsonObject:
        version = params.get("protocolVersion")
        if version != 1:
            return self._error(request_id, -32602, "Unsupported protocolVersion")
        self._initialized = True
        return self._result(
            request_id,
            {
                "protocolVersion": 1,
                "agentInfo": {"name": "Siada", "version": "1.7.17"},
                "agentCapabilities": {},
            },
        )

    def _new_session(self, request_id: int | str, params: JsonObject) -> JsonObject:
        if not self._initialized:
            return self._error(request_id, -32600, "initialize must be called first")
        session_id = str(uuid4())
        self._sessions[session_id] = AcpSession(session_id=session_id, cwd=params.get("cwd"))
        return self._result(request_id, {"sessionId": session_id})

    def _prompt(self, request_id: int | str, params: JsonObject) -> JsonObject:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            return self._error(request_id, -32602, "Unknown sessionId")
        prompt = "".join(
            item.get("text", "") for item in params.get("prompt", []) if item.get("type") == "text"
        )
        for update in self._turn_runner(session_id, prompt):
            self._notifications.append(
                {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": update}}
            )
        return self._result(request_id, {})

    def _cancel(self, request_id: int | str, params: JsonObject) -> JsonObject:
        session_id = params.get("sessionId")
        if session_id not in self._sessions:
            return self._error(request_id, -32602, "Unknown sessionId")
        self._cancelled_sessions.add(session_id)
        return self._result(request_id, {})

    def is_cancelled(self, session_id: str) -> bool:
        """Return whether a client requested cancellation for this session."""
        return session_id in self._cancelled_sessions

    def drain_notifications(self) -> list[JsonObject]:
        """Return and clear notifications generated while handling requests."""
        notifications, self._notifications = self._notifications, []
        return notifications

    @staticmethod
    def _result(request_id: int | str, result: JsonObject) -> JsonObject:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: int | str | None, code: int, message: str) -> JsonObject:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
