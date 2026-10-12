"""Public API for version checking.

Exposes the shared ``VersionChecker`` contract plus the module-level
``version_checker`` singleton. The handler is optional: when no public handler
is importable the checker still works, using the published release metadata
only.
"""

import importlib
from pathlib import Path

from .version_checker import VersionChecker


def _load_handler():
    """Return the public version handler, or None when none is importable.

    Handlers are optional fallbacks; ``VersionChecker`` degrades to the public
    release metadata when this returns None.
    """
    handlers_dir = Path(__file__).parent / "handlers"
    if (handlers_dir / "external_handler.py").exists():
        try:
            module = importlib.import_module(".handlers.external_handler", __name__)
            return module.VersionHandler()
        except Exception:
            pass
    return None


_handler = _load_handler()
version_checker = VersionChecker(_handler)


def get_latest_version():
    return version_checker.get_latest_version()


def install_upgrade(io, latest_version=None, version_source=None):
    return version_checker.install_upgrade(io, latest_version, version_source)


def check_version(io, just_check=False, verbose=False):
    return version_checker.check_version(io, just_check, verbose)


__all__ = [
    "VersionChecker",
    "version_checker",
    "get_latest_version",
    "install_upgrade",
    "check_version",
]
