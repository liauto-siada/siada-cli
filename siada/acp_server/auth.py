"""ACP authentication methods advertised by the Siada agent.

Siada uses Terminal Auth: the client re-launches the binary with
``--login``, which drops the user into Siada's interactive sign-in flow
(LiId device code or provider API key). Once credentials are stored in
``~/.siada-cli/``, the ACP server picks them up on its next start.
"""

from __future__ import annotations

import sys
from typing import Any

SIADA_TERMINAL_AUTH_METHOD_ID = "siada_terminal_login"

_LOGIN_ARG = "--login"


def _terminal_auth_launch_spec() -> dict[str, Any]:
    """Best-effort command+args for Zed's terminal-auth banner.

    Zed expects a fully resolved command rather than the RFD's
    args-only shape, so mirror however this process was started.
    """
    argv1 = sys.argv[0] if sys.argv else ""
    if argv1.endswith(".py"):
        return {"command": sys.executable, "args": [argv1, _LOGIN_ARG]}
    if argv1:
        return {"command": argv1, "args": [_LOGIN_ARG]}
    return {"command": "siada-cli", "args": [_LOGIN_ARG]}


def get_auth_methods(supports_terminal_auth_meta: bool = True) -> list[dict[str, Any]]:
    """Build the ``authMethods`` payload for ``initialize``.

    Both shapes are emitted for maximum compatibility:
      - ``type``/``args``/``env``: the shape required by the ACP registry.
      - ``_meta["terminal-auth"]``: what Zed reads to render its
        "Authenticate" banner.
    """
    method: dict[str, Any] = {
        "id": SIADA_TERMINAL_AUTH_METHOD_ID,
        "name": "Sign in with Siada in the terminal",
        "description": "Launch Siada in an interactive terminal to sign in or configure an API key",
        "type": "terminal",
        "args": [_LOGIN_ARG],
        "env": {},
    }

    if supports_terminal_auth_meta:
        method["_meta"] = {
            "terminal-auth": {**_terminal_auth_launch_spec(), "label": "Launch Siada"},
        }

    return [method]
