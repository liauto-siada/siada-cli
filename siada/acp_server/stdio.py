"""NDJSON stdio transport for the standard ACP server."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from siada.acp_server.server import AcpServer


def _default_turn_runner(_session_id: str, _prompt: str):
    """Temporary runner until the Siada conversation adapter is wired in."""
    yield {"sessionUpdate": "end_turn"}


def serve(stdin: TextIO, stdout: TextIO, server: AcpServer | None = None) -> None:
    """Process newline-delimited JSON-RPC messages until stdin reaches EOF."""
    server = server or AcpServer(turn_runner=_default_turn_runner)
    for line in stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write(stdout, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        _write(stdout, server.handle(request))
        for notification in server.drain_notifications():
            _write(stdout, notification)


def _write(stdout: TextIO, message: dict) -> None:
    stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def main() -> None:
    serve(sys.stdin, sys.stdout)
