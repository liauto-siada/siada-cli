"""Resolve an existing Node runtime shared by the UI and browser proxy."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

NODE_VERSION = "24.13.0"


def runtime_node(runtime: Path) -> Path:
    """Return the executable in an official Node distribution."""
    return runtime / ("node.exe" if sys.platform == "win32" else "bin/node")


def legacy_node() -> Path:
    """Support previously installed venv and nvm runtime layouts."""
    prefix = Path(sys.prefix)
    direct = runtime_node(prefix / "node")
    if direct.is_file():
        return direct
    previous = runtime_node(prefix / "nvm" / "versions" / "node" / "v24.21.0")
    if previous.is_file():
        return previous
    return runtime_node(prefix / "nvm" / "versions" / "node" / f"v{NODE_VERSION}")


def find_node(legacy: Path | None = None) -> str:
    """Resolve the override, browser runtime, legacy install, then PATH."""
    override = os.environ.get("SIADA_BROWSER_NODE")
    if override:
        return override
    from siada.browser_addon.paths import browser_home

    for candidate in (runtime_node(browser_home() / "runtime"), legacy or legacy_node()):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("node")
    if found:
        return found
    raise FileNotFoundError(
        "Node.js not found. Run `siada-browser setup` to install the browser "
        "runtime, or install Node.js 24 LTS from https://nodejs.org/ "
        "and add its bin directory to PATH."
    )