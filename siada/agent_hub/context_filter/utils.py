from __future__ import annotations
from typing import Any
import hashlib
import json


def compute_message_signature(message: Any) -> str:
    """
    Compute MD5 signature for a message.
    
    Args:
        message: The message to compute signature for
        
    Returns:
        MD5 hash string of the message
    """
    # Convert message to string for MD5 calculation
    message_str = json.dumps(message, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(message_str.encode('utf-8')).hexdigest()