"""Paths and runtime resolution for the chrome-acp browser addon.

Addon files live under ``~/.siada-cli/browser/``:

    proxy/          chrome-acp proxy-server (dist + public + node_modules)
    extension/      unpacked MV3 extension (fixed path — Chrome pins it)
    state.json      {port, token}

Logs are stored under the CLI log root in ``logs/proxy/``.

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


def log_directory() -> Path:
    override = os.environ.get("SIADA_PROXY_LOG_DIR")
    if override:
        return Path(override).expanduser()
    from siada.foundation.logging import get_log_directory

    return Path(get_log_directory()) / "proxy"


def log_path() -> Path:
    """Bootstrap diagnostics emitted before the Node logger is initialized."""
    return log_directory() / "acp-proxy-launch.log"


def node_binary() -> str:
    """Resolve the same runtime used by the terminal UI."""
    from siada.foundation.node_runtime import find_node

    return find_node()


def npm_argv() -> list[str] | None:
    """Argv that runs npm, preferring ``node npm-cli.js`` (no Windows .cmd mess)."""
    node = node_binary()
    prefix = Path(sys.prefix)
    candidates = [
        browser_home() / "runtime" / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        browser_home() / "runtime" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        prefix / "node" / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        prefix / "node" / "node_modules" / "npm" / "bin" / "npm-cli.js",
    ]
    for cli in candidates:
        if cli.is_file():
            return [node, str(cli)]
    npm = shutil.which("npm")
    return [npm] if npm else None
