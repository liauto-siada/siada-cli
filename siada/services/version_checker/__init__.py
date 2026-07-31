"""
Public API for version checking.
Delegates to siada.internal.services.version_checker when available.
"""
try:
    from siada.internal.services.version_checker import (
        VersionChecker,
        version_checker,
        get_latest_version,
        install_upgrade,
        check_version,
    )
except ImportError:
    # Internal module not available (external distribution).
    # Fall back to the local implementation.
    import importlib
    from pathlib import Path
    from .version_checker import VersionChecker  # type: ignore[no-redef]
    from siada.services.auto_update import detect_install_mode

    def _load_handler():
        if detect_install_mode() == "internal":
            internal_handler_path = (
                Path(__file__).parent.parent.parent
                / "internal"
                / "services"
                / "version_checker"
                / "handlers"
                / "internal_handler.py"
            )
            if internal_handler_path.exists():
                try:
                    module = importlib.import_module(
                        "siada.internal.services.version_checker.handlers.internal_handler"
                    )
                    return module.VersionHandler()
                except Exception:
                    pass

        handlers_dir = Path(__file__).parent / "handlers"
        if (handlers_dir / "external_handler.py").exists():
            try:
                module = importlib.import_module(".handlers.external_handler", __name__)
                return module.VersionHandler()
            except Exception:
                pass
        return None

    _handler = _load_handler()
    version_checker = VersionChecker(_handler)  # type: ignore[assignment]

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
