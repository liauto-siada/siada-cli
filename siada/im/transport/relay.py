"""Relay transport placeholder (unavailable in this distribution).

The relay transport talks to a privately hosted IM gateway and is not part of
this distribution, so ``RelayTransport`` / ``LarkCredentials`` cannot be
imported from here. ``RELAY_AVAILABLE`` is ``False`` and importing either name
raises ``ImportError`` that explains the fallback, so relay-aware callers can
detect the absence and use direct mode instead
(``siada.im.transport.direct``).
"""

RELAY_AVAILABLE = False

_UNAVAILABLE_MESSAGE = (
    "Relay transport is unavailable: the Siada relay gateway client is a "
    "private implementation that is not part of this distribution. "
    "Use direct mode instead (siada.im.transport.direct.DirectTransport)."
)


def __getattr__(name: str):
    """Report legacy relay names as an actionable ImportError."""
    if name in ("LarkCredentials", "RelayTransport"):
        raise ImportError(_UNAVAILABLE_MESSAGE)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RELAY_AVAILABLE"]
