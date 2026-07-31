"""Unified IM message models across all platforms."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeishuMediaKey:
    """Raw media key extracted from a Feishu message (before download).

    Populated by the Feishu adapter during parse_event() and consumed by
    LarkAgentExecutor to download the resource before passing it to the agent.
    """

    key: str            # image_key or file_key from the Feishu message content
    resource_type: str  # Feishu API "type" param: "image" | "file"
    msg_type: str       # original message type: "image" | "file" | "sticker" | "post"


@dataclass
class MentionTarget:
    """A user mentioned in the message (excluding the bot itself)."""

    open_id: str  # Feishu open_id (ou_xxx)
    name: str  # Display name
    key: str  # Placeholder in original message, e.g. "@_user_1"


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
    parent_id: Optional[str] = None  # Feishu reply message parent_id
    # Resolved quoted message content (populated by QuotedMessageResolver)
    quoted_content: Optional[str] = None  # Plain text of the replied-to message
    quoted_sender: Optional[str] = None  # Display name or open_id of quoted msg sender
    mentioned_bot: bool = False
    sender_en_name: Optional[str] = None
    sender_open_id: Optional[str] = None  # Lark open_id (ou_xxx), separate from user_id
    # Mention-related fields for group chat @ support
    mentions: list[MentionTarget] = field(default_factory=list)  # Non-bot mention targets
    has_any_mention: bool = False  # Whether message has any @ (including bot)
    # Feishu media keys to download before agent execution (populated by Feishu adapter)
    feishu_media_keys: "list[FeishuMediaKey]" = field(default_factory=list)

    def with_content(self, new_content: str) -> "IMMessage":
        """Return a shallow copy with replaced content."""
        from dataclasses import replace
        return replace(self, content=new_content)


@dataclass
class IMResponse:
    """Unified response model for sending messages back."""

    request_id: str
    content_type: str  # text / markdown / interactive
    content: str
    chat_id: Optional[str] = None
    is_streaming: bool = False
    header_title: Optional[str] = None
    header_template: Optional[str] = None
