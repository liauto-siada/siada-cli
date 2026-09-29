"""Lazy exports for siada.config.

external_agent_migration pulls in yaml and other deps that are not needed at
startup; import attributes on demand to keep `import siada.config` cheap.
"""

_LAZY_ATTRS = (
    "ExternalAgentMigrationService",
    "ExternalAgentSource",
    "MigrationItem",
    "MigrationItemType",
)


def __getattr__(name):
    if name in _LAZY_ATTRS:
        from siada.config import external_agent_migration as _m

        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_LAZY_ATTRS)
