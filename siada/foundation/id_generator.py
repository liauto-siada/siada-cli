"""Centralized session ID generator.

Generates session IDs in the format: {timestamp_ms}-{uuid4_short}
e.g. "1713180000000-a1b2c3d4"

This ensures:
- Temporal ordering via millisecond timestamp prefix
- Uniqueness via UUID4 short hash suffix
- Human readability for debugging
"""

import time
import uuid


def generate_session_id() -> str:
    """Generate a unique session ID combining timestamp and UUID4.

    Format: {timestamp_ms}-{uuid4_hex[:8]}
    Example: "1713180000000-a1b2c3d4"
    """
    timestamp_ms = str(int(time.time() * 1000))
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp_ms}-{short_uuid}"
