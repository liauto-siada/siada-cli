"""Proactive task discovery module."""

# Lazy imports to avoid triggering heavy dependency chains (e.g. file_operator → openhands_aci)
# when only DaemonManager or PIDManager is needed (e.g. daemon_commands.py).
# Callers that need ProactiveAgent or SiadaDaemon should import them directly from their modules.


def __getattr__(name: str):
    if name == "ProactiveAgent":
        from .proactive_agent import ProactiveAgent
        return ProactiveAgent
    if name == "SiadaDaemon":
        from .daemon import SiadaDaemon
        return SiadaDaemon
    if name == "DaemonManager":
        from .daemon_manager import DaemonManager
        return DaemonManager
    if name == "PIDManager":
        from .utils.pid_manager import PIDManager
        return PIDManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ProactiveAgent", "SiadaDaemon", "DaemonManager", "PIDManager"]
