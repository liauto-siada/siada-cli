"""siada package root.

`__version__` is resolved lazily: importlib.metadata pulls in email/zipfile
and costs ~38ms at import time, which is paid on every `import siada.*`
(launcher, backend, tests) even when the version is never read.
"""


def _resolve_version() -> str:
    try:
        from importlib.metadata import version
    except ImportError:
        # Python < 3.8 compatibility
        from importlib_metadata import version

    try:
        return version("siada-cli")
    except Exception:
        # Fallback for development environment
        return "dev"


def __getattr__(name):
    if name == "__version__":
        version_value = _resolve_version()
        globals()["__version__"] = version_value  # cache for subsequent accesses
        return version_value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | {"__version__"})


__all__ = ["__version__"]
