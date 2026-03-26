"""
ACP (Agent Client Protocol) Implementation

This package provides ACP-compliant message communication for siada-agenthub.

Core components:
- message_builder: Build standard ACP messages
- stream_manager: Manage streaming output
- transport: Communication layer (stdio, http, etc.)
"""

from .message_builder import (
    ACPMessage,
    ACPMessageBuilder,
    ACPMessageType,
    SessionUpdateReason,
)
from .stream_manager import (
    ACPStreamManager,
    StreamManagerSync,
)
from .transport import (
    ACPTransport,
    StdioTransport,
)
from .legacy_adapter import (
    LegacyACPAdapter,
    ACPModeDetector,
    create_io_adapter,
)

__all__ = [
    # Message building
    'ACPMessage',
    'ACPMessageBuilder',
    'ACPMessageType',
    'SessionUpdateReason',
    # Stream management
    'ACPStreamManager',
    'StreamManagerSync',
    # Transport
    'ACPTransport',
    'StdioTransport',
    # Legacy compatibility
    'LegacyACPAdapter',
    'ACPModeDetector',
    'create_io_adapter',
]
