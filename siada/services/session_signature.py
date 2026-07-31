"""
Session Signature Utility

Provides the compute_last_item_signature() function used by FileSession
to generate an MD5 hash of the last native item for change detection
in the deferred rendering (cross-channel sync) flow.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_last_item_signature(native_items: list) -> str:
    """Compute MD5 signature from the last native item.

    Args:
        native_items: Full list of native (OpenAI-format) items from the session.

    Returns:
        MD5 hex digest of the last item, or empty string if the list is empty.
    """
    if not native_items:
        return ""
    last = native_items[-1]
    message_str = json.dumps(last, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(message_str.encode("utf-8")).hexdigest()