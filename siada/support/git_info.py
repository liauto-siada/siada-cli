"""
Lightweight git workspace info helper.

Provides get_workspace_git_info(path) which returns a GitInfo dataclass
containing the remote origin URL, current branch name, and HEAD commit hash
for the git repository that contains ``path``.

The function walks up from ``path`` to the filesystem root so it works even
when the workspace itself is a subdirectory of the actual repo root.
Returns a GitInfo with all-empty strings when no git repo can be found or
any git command fails.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GitInfo:
    repo_url: str = ""
    branch: str = ""
    commit: str = ""

    @property
    def repo_id(self) -> str:
        """Return the ``group/repo`` portion of the remote URL.

        Handles the two most common URL shapes:
          - SSH  : ``git@host:group/repo.git``    → ``group/repo``
          - HTTPS: ``https://host/group/repo.git`` → ``group/repo``
        Returns an empty string when ``repo_url`` is empty or unparseable.
        """
        return _parse_repo_id(self.repo_url)


def _parse_repo_id(url: str) -> str:
    """Extract ``group/repo`` from a git remote URL, stripping the ``.git`` suffix."""
    if not url:
        return ""
    # SSH format: git@host:path/to/repo.git
    if ":" in url and not url.startswith(("http://", "https://", "ssh://")):
        path = url.split(":", 1)[1]
    else:
        # HTTPS / SSH-with-scheme: strip scheme and host
        # e.g. https://gitlab.com/group/repo.git  or  ssh://git@gitlab.com/group/repo.git
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path.lstrip("/")
        except Exception:
            return ""
    # Strip trailing .git
    if path.endswith(".git"):
        path = path[:-4]
    return path


def get_workspace_git_info(path: Optional[str]) -> GitInfo:
    """Return git repo URL, branch, and HEAD commit for the git repo that contains *path*.

    Searches upward from *path* (or cwd when *path* is None) until a .git
    directory is found or the filesystem root is reached.  Falls back to empty
    strings on any error so callers are never disrupted by missing git.
    """
    if not path:
        logging.debug("get_workspace_git_info: path is empty, returning empty GitInfo")
        return GitInfo()

    repo_root = _find_git_root(path)
    if not repo_root:
        logging.debug(f"get_workspace_git_info: no git root found under {path!r}")
        return GitInfo()

    logging.debug(f"get_workspace_git_info: found git root {repo_root!r}")
    info = GitInfo(
        repo_url=_run_git(repo_root, ["remote", "get-url", "origin"]),
        branch=_run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        commit=_run_git(repo_root, ["rev-parse", "HEAD"]),
    )
    logging.debug(
        f"get_workspace_git_info: repo_url={info.repo_url!r}, "
        f"branch={info.branch!r}, commit={info.commit!r}"
    )
    return info


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_git_root(start: str) -> Optional[str]:
    """Walk up from *start* and return the first directory that contains .git."""
    from pathlib import Path

    current = Path(start).resolve()
    # Guard against infinite loop on unusual filesystems
    for _ in range(100):
        if (current / ".git").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _run_git(cwd: str, args: list[str]) -> str:
    """Run a git command in *cwd* and return stdout stripped, or "" on failure."""
    try:
        # Suppress any credential prompts so git never blocks waiting for input.
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"

        kwargs: dict = dict(
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            env=env,
        )
        # On Windows, prevent git (or credential helpers) from opening GUI windows.
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(["git"] + args, **kwargs)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
