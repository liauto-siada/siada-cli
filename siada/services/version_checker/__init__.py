"""Public version checker and optional public release handler."""

import importlib
from pathlib import Path

from .version_checker import VersionChecker


def _load_handler():
    """Load the public handler without requiring another distribution."""
    if (Path(__file__).parent / "handlers" / "external_handler.py").exists():
        try:
            return importlib.import_module(".handlers.external_handler", __name__).VersionHandler()
        except Exception:
            pass
    return None


version_checker = VersionChecker(_load_handler())


def get_latest_version():
    return version_checker.get_latest_version()


def install_upgrade(io, latest_version=None, version_source=None):
    return version_checker.install_upgrade(io, latest_version, version_source)


def check_version(io, just_check=False, verbose=False):
    return version_checker.check_version(io, just_check, verbose)


__all__ = ["VersionChecker", "version_checker", "get_latest_version", "install_upgrade", "check_version"]