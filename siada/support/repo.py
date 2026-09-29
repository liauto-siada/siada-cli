import os
from pathlib import Path


def get_git_root(path=None):
    """Find the git repository root by looking for a .git directory.

    Uses plain os operations instead of GitPython (~135ms import) since
    this is called on the startup critical path just to locate .env files.

    Args:
        path: Optional path to start searching from. If None, uses current directory.

    Returns:
        str or None: Path to git repository root, or None if not found
    """
    start = Path(path).resolve() if path else Path.cwd()
    for parent in [start] + list(start.parents):
        if (parent / ".git").exists():
            return str(parent)
    return None