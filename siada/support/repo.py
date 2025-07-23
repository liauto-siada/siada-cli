import contextlib
import os
import time
from pathlib import Path, PurePosixPath

try:
    import git

    ANY_GIT_ERROR = [
        git.exc.ODBError,
        git.exc.GitError,
        git.exc.InvalidGitRepositoryError,
        git.exc.GitCommandNotFound,
    ]
except ImportError:
    git = None
    ANY_GIT_ERROR = []

ANY_GIT_ERROR += [
    OSError,
    IndexError,
    BufferError,
    TypeError,
    ValueError,
    AttributeError,
    AssertionError,
    TimeoutError,
]
ANY_GIT_ERROR = tuple(ANY_GIT_ERROR)



def get_git_root():
    """Try and guess the git repo, since the conf.yml can be at the repo root"""
    try:
        repo = git.Repo(search_parent_directories=True)
        return repo.working_tree_dir
    except (git.InvalidGitRepositoryError, FileNotFoundError):
        return None