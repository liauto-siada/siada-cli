"""siada package root.

`__version__` is resolved lazily: importlib.metadata pulls in email/zipfile
and costs ~38ms at import time, which is paid on every `import siada.*`
(launcher, backend, tests) even when the version is never read.
"""


def _resolve_version() -> str:
    """Resolve the version of this checkout or installed distribution."""
    from pathlib import Path
    import tomllib

    # A checkout may share an environment with an older installed distribution.
    # Resolve relative to this module, never the user's working directory.
    manifest = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if manifest.is_file():
        with manifest.open("rb") as source:
            config = tomllib.load(source)
        project = config.get("project", {})
        poetry = config.get("tool", {}).get("poetry", {})
        for metadata in (project, poetry):
            if metadata.get("name") == "siada-cli":
                value = metadata.get("version")
                if isinstance(value, str) and value.strip() and value != "dev":
                    return value.strip()

    from importlib.metadata import PackageNotFoundError, version

    try:
        value = version("siada-cli")
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "Siada version metadata is missing. Reinstall siada-cli or run from "
            "a checkout containing pyproject.toml."
        ) from exc
    if not isinstance(value, str) or not value.strip() or value.strip() == "dev":
        raise RuntimeError("Siada version metadata is invalid. Reinstall siada-cli.")
    return value.strip()


def __getattr__(name):
    if name == "__version__":
        version_value = _resolve_version()
        globals()["__version__"] = version_value  # cache for subsequent accesses
        return version_value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | {"__version__"})


__all__ = ["__version__"]
