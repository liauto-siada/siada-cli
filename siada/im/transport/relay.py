"""Backward-compatible re-export stub.

The relay transport implementation has moved to siada.internal.transport.relay.
This module re-exports for any legacy imports.
"""

try:
    from siada.internal.transport.relay import (  # noqa: F401
        LarkCredentials,
        RelayTransport,
    )
except ImportError:
    LarkCredentials = None
    RelayTransport = None
