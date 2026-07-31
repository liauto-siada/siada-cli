import contextlib
import os
import time
from pathlib import Path, PurePosixPath

# Lazy: git (GitPython) is ~95ms to import.  Defer to first get_git_root() call.
_git = None
_ANY_GIT_ERROR = None


def _init_git():
    """Import git lazily and build the exception tuple."""
    global _git, _ANY_GIT_ERROR
    if _ANY_GIT_ERROR is not None:
        return
    try:
        import git

        _git = git
        errs = [
            git.exc.ODBError,
            git.exc.GitError,
            git.exc.InvalidGitRepositoryError,
            git.exc.GitCommandNotFound,
        ]
    except ImportError:
        _git = None
        errs = []
    errs += [
        OSError,
        IndexError,
        BufferError,
        TypeError,
        ValueError,
        AttributeError,
        AssertionError,
        TimeoutError,
    ]
    _ANY_GIT_ERROR = tuple(errs)


def get_git_root(path=None):
    """Try and guess the git repo, since the conf.yml can be at the repo root
    
    Args:
        path: Optional path to start searching from. If None, uses current directory.
        
    Returns:
        str or None: Path to git repository root, or None if not found
    """
    _init_git()
    if _git is None:
        return None
    try:
        # If path is provided, start search from that directory
        if path:
            repo = _git.Repo(path, search_parent_directories=True)
        else:
            # Default behavior: search from current directory
            repo = _git.Repo(search_parent_directories=True)
        return repo.working_tree_dir
    except (_git.InvalidGitRepositoryError, FileNotFoundError):
        return None