"""Filesystem locations for the Browser Skill Graph.

All state lives under ``~/.siada-cli/workspace/`` (siada's own user data
directory), independent of chrome-acp's ``~/.chrome-acp`` directory.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

from siada.foundation.constants import SIADA_HOME


def get_trajectories_dir() -> Path:
    """Raw trajectory jsonl files, written by chrome-acp's proxy-server.

    One file per day: ``YYYY-MM-DD.jsonl``. (Recording location only — the
    learning pipeline no longer ingests these files.)
    """
    path = SIADA_HOME / "workspace" / "browser_trajectories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_skills_root() -> Path:
    """Root directory for browser skills: ``<domain>/<capacity>/...``."""
    path = SIADA_HOME / "workspace" / "browser_skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_registry_path() -> Path:
    """Global registry.json indexing every published skill."""
    return get_skills_root() / "registry.json"


def skill_dir_for(domain: str, capacity: str) -> Path:
    """Directory holding one skill's artifacts."""
    from .event_utils import slugify

    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
        raise ValueError("Invalid browser skill domain")
    return get_skills_root() / domain.lower() / slugify(capacity)


def atomic_write_text(path: Path, text: str) -> None:
    """Publish a complete artifact without exposing partial writes to readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
