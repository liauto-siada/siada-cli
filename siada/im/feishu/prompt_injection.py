"""Feishu inbound user context prefix injection.

Builds untrusted metadata blocks prepended to the user-role message before
the actual user text. Follows OpenClaw's buildInboundUserContextPrefix()
pattern (src/auto-reply/reply/inbound-meta.ts L178-258).

Two JSON blocks are emitted (when enabled):
  // Conversation info (untrusted metadata): { ... }
  // Sender (untrusted metadata):            { ... }

Followed by any mention system hints from build_mention_system_hint().
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from siada.im.models import IMMessage


def build_inbound_user_context_suffix(
    msg: "IMMessage",
    *,
    include_conversation_info: bool = False,
) -> Optional[str]:
    """Build the context suffix to append after the user-role message content.

    Returns None when there is nothing to inject (disabled and no mention hints).
    """
    from siada.im.feishu.mention import build_mention_system_hint

    parts: list[str] = []

    if include_conversation_info:
        conv_data = _build_conversation_info(msg)
        if conv_data:
            parts.append(_format_untrusted_json_block("Conversation info", conv_data))

    mention_hint = build_mention_system_hint(msg)
    if mention_hint:
        parts.append(mention_hint)

    return "\n\n".join(parts) if parts else None


def _build_conversation_info(msg: "IMMessage") -> dict:
    """Build conversation info dict from IMMessage fields.

    DM vs group field differences per design §3.2:
    - chat_id and is_group_chat are group-only
    - reply_to_id and was_mentioned are emitted only when present/true
    """
    is_group = msg.chat_type == "group"
    data: dict = {}

    if is_group and msg.chat_id:
        data["chat_id"] = msg.chat_id

    if msg.sender_open_id:
        data["sender_open_id"] = msg.sender_open_id
    if msg.user_id:
        data["sender_user_id"] = msg.user_id
    if msg.sender_name:
        data["sender_name"] = msg.sender_name

    if msg.message_id:
        data["message_id"] = msg.message_id

    reply_to = msg.parent_id or msg.root_id
    if reply_to:
        data["reply_to_id"] = reply_to

    if is_group:
        data["is_group_chat"] = True

    if msg.mentioned_bot:
        data["was_mentioned"] = True

    return data


def build_quoted_message_block(msg: "IMMessage") -> Optional[str]:
    """Build the quoted/replied message context block (always-on, no switch).

    Only emitted when msg.quoted_content is populated (by QuotedMessageResolver).
    This is independent of include_conversation_info — reply context is always
    provided to the agent when available.

    Format follows OpenClaw's "Replied message (untrusted, for context)" pattern.
    """
    if not msg.quoted_content:
        return None

    data: dict = {}
    if msg.quoted_sender:
        data["sender"] = msg.quoted_sender
    data["body"] = msg.quoted_content

    return _format_untrusted_json_block("Replied message", data)


def _format_untrusted_json_block(label: str, data: dict) -> str:
    """Format a labelled untrusted JSON block.

    Example:
        // Conversation info (untrusted metadata):
        {
          "chat_id": "oc_xxx"
        }
    """
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    return f"// {label} (untrusted metadata):\n{json_str}"
