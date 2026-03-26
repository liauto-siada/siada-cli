"""Unified IM message models across all platforms."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IMMessage:
    """Unified message model across all IM platforms."""

    request_id: str
    platform: str  # lark / wecom / dingtalk
    user_id: str
    chat_id: str
    chat_type: str  # p2p / group
    content_type: str  # text / image / file / interactive
    content: str
    timestamp: float
    raw: dict = field(default_factory=dict)
    # Optional extended fields
    message_id: Optional[str] = None
    sender_name: Optional[str] = None
    root_id: Optional[str] = None
    thread_id: Optional[str] = None
    mentioned_bot: bool = False
    sender_en_name: Optional[str] = None
    sender_open_id: Optional[str] = None  # Lark open_id (ou_xxx), separate from user_id


@dataclass
class IMResponse:
    """Unified response model for sending messages back."""

    request_id: str
    content_type: str  # text / markdown / interactive
    content: str
    chat_id: Optional[str] = None
    is_streaming: bool = False
