import os
import importlib
from pathlib import Path
from .version_checker import VersionChecker

def _load_handler():
    """Plugin pattern: automatically detect and load available handlers"""
    # Try to load internal handler plugin first (for developers and internal users)
    internal_handler_path = Path(__file__).parent.parent / "internal" / "handles" / "internal_handler.py"
    if internal_handler_path.exists():
        try:
            module = importlib.import_module("siada.services.internal.handles.internal_handler")
            return module.VersionHandler()
        except Exception:
            pass
    
    # Try to load external handler plugin (for external users)
    handlers_dir = Path(__file__).parent / "handlers"
    if (handlers_dir / "external_handler.py").exists():
        try:
            module = importlib.import_module(".handlers.external_handler", __name__)
            return module.VersionHandler()
        except Exception:
            pass
    
    return None

# Automatically load handler plugin
_handler = _load_handler()

# Create global interface instance
version_checker = VersionChecker(_handler)

# Export main functions for backward compatibility
def get_latest_version():
    """Get latest version using the global version checker"""
    return version_checker.get_latest_version()

def install_upgrade(io, latest_version=None, version_source=None):
    """Install upgrade using the global version checker"""
    return version_checker.install_upgrade(io, latest_version, version_source)

def check_version(io, just_check=False, verbose=False):
    """Check version using the global version checker"""
    return version_checker.check_version(io, just_check, verbose)

__all__ = [
    'VersionChecker',
    'version_checker',
    'get_latest_version',
    'install_upgrade',
    'check_version'
]
