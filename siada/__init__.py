try:
    from importlib.metadata import version
except ImportError:
    # Python < 3.8 compatibility
    from importlib_metadata import version

try:
    __version__ = version("siada-agenthub")
except Exception:
    # Fallback for development environment
    __version__ = "dev"

__all__ = ["__version__"]