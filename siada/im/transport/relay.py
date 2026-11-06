"""Relay transport is unavailable in the public distribution."""

RELAY_AVAILABLE = False
_UNAVAILABLE_MESSAGE = (
    "Relay transport is unavailable: the gateway client is not part of this "
    "distribution. Use direct mode instead "
    "(siada.im.transport.direct.DirectTransport)."
)


def __getattr__(name: str):
    """Give callers of legacy relay names an actionable import error."""
    if name in ("LarkCredentials", "RelayTransport"):
        raise ImportError(_UNAVAILABLE_MESSAGE)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RELAY_AVAILABLE"]
