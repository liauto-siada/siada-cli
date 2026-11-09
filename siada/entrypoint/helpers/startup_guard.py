"""Guards for user-facing startup failures detected before IO is ready.

These checks run at the beginning of the CLI entry points, so they report
directly to stderr instead of going through the logging or IO layers that are
not initialised yet.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

MISSING_LAUNCH_DIRECTORY_MESSAGE = (
    "Error: the current working directory no longer exists.\n"
    "Please change to an existing directory (for example, cd ~) or pass "
    "--workspace <dir>, then run siada-cli again."
)


def workspace_argument(argv: Optional[Sequence[str]] = None) -> Optional[str]:
    """Return the raw ``--workspace``/``-w`` value without resolving it.

    Resolution is deferred to the callers because it may depend on the launch
    directory (relative paths) or on ``SIADA_WORKSPACE``. Text after a literal
    ``--`` is user content and is never treated as an option.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--workspace", "-w", nargs="?", const=".", default=os.environ.get("SIADA_WORKSPACE")
    )

    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--" in arguments:
        arguments = arguments[: arguments.index("--")]

    temp_args, _ = parser.parse_known_args(arguments)
    return temp_args.workspace


def missing_launch_directory_error(workspace: Optional[str] = None) -> Optional[str]:
    """Return a diagnostic when the process has no usable working directory.

    ``os.getcwd()`` raises ``FileNotFoundError`` once the directory the process
    was started in has been deleted (for example, a shell left open in a
    removed worktree). Every later workspace lookup would then fail with a raw
    traceback, so callers report this message and exit instead. An existing
    absolute ``--workspace`` keeps the CLI usable without the launch directory.
    """
    if workspace:
        candidate = Path(workspace)
        if candidate.is_absolute() and candidate.is_dir():
            return None

    try:
        os.getcwd()
    except OSError:
        return MISSING_LAUNCH_DIRECTORY_MESSAGE
    return None
