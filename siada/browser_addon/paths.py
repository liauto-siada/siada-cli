"""Paths and runtime resolution for the chrome-acp browser addon.

Everything lives under ``~/.siada-cli/browser/``:

    proxy/          chrome-acp proxy-server (dist + public + node_modules)
    extension/      unpacked MV3 extension (fixed path — Chrome pins it)
    state.json      {port, token}
    acp-proxy.log   proxy stdout/stderr

Env overrides (mainly for tests): SIADA_BROWSER_HOME, SIADA_BROWSER_NODE,
SIADA_BROWSER_PROXY_CMD.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from siada.foundation.constants import SIADA_HOME

DEFAULT_PORT = 9315


def browser_home() -> Path:
    env = os.environ.get("SIADA_BROWSER_HOME")
    return Path(env).expanduser() if env else SIADA_HOME / "browser"


def proxy_dir() -> Path:
    return browser_home() / "proxy"


def proxy_entry() -> Path | None:
    entry = proxy_dir() / "dist" / "cli" / "bin.js"
    return entry if entry.is_file() else None


def extension_dir() -> Path:
    return browser_home() / "extension"


def state_path() -> Path:
    return browser_home() / "state.json"


def log_path() -> Path:
    return browser_home() / "acp-proxy.log"


def node_binary() -> str:
    """Node.js: env override → the one bundled in the siada venv → PATH."""
    env = os.environ.get("SIADA_BROWSER_NODE")
    if env:
        return env
    exe = "node.exe" if sys.platform.startswith("win") else "node"
    for candidate in (Path(sys.prefix) / "node" / "bin" / exe, Path(sys.prefix) / "node" / exe):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("node")
    if found:
        return found
    raise FileNotFoundError(
        "Node.js not found (no bundled node in the siada venv, none on PATH). "
        "Reinstall siada-cli or set SIADA_BROWSER_NODE."
    )


def npm_argv() -> list[str] | None:
    """Argv that runs npm, preferring ``node npm-cli.js`` (no Windows .cmd mess)."""
    node = node_binary()
    prefix = Path(sys.prefix)
    candidates = [
        prefix / "node" / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        prefix / "node" / "node_modules" / "npm" / "bin" / "npm-cli.js",
    ]
    for cli in candidates:
        if cli.is_file():
            return [node, str(cli)]
    npm = shutil.which("npm")
    return [npm] if npm else None
