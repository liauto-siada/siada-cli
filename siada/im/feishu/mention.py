"""Feishu @ mention parsing and formatting utilities.

Reference: OpenClaw extensions/feishu/src/mention.ts
           OpenClaw extensions/feishu/src/bot-content.ts
"""

from __future__ import annotations

from siada.im.models import MentionTarget


def _extract_open_id(mention: dict) -> str:
    """Extract open_id from a mention dict, handling both dict and str id formats."""
    mention_id = mention.get("id", {})
    if isinstance(mention_id, dict):
        return mention_id.get("open_id", "")
    return str(mention_id)


# ──────────────── Inbound Parsing ────────────────


def check_bot_mentioned(
    mentions: list[dict],
    bot_open_id: str,
) -> bool:
    """Check if bot is mentioned in the event.

    Returns True if:
    - mentions array contains bot's open_id
    - mentions array contains @_all key

    Reference: OpenClaw bot-content.ts -> checkBotMentioned()
    """
    for mention in mentions:
        # @_all counts as mentioning everyone including the bot
        if mention.get("key") == "@_all":
            return True
        if _extract_open_id(mention) == bot_open_id:
            return True
    return False


def extract_mention_targets(
    mentions: list[dict],
    bot_open_id: str,
) -> list[MentionTarget]:
    """Extract non-bot mention targets from feishu event mentions array.

    Filters out:
    - Bot's own mention (by open_id match)
    - @_all (everyone) mentions

    Reference: OpenClaw mention.ts -> extractMentionTargets()
    """
    targets: list[MentionTarget] = []
    for mention in mentions:
        key = mention.get("key", "")
        # Skip @_all
        if key == "@_all":
            continue
        open_id = _extract_open_id(mention)
        # Skip bot itself
        if open_id == bot_open_id:
            continue
        name = mention.get("name", "")
        targets.append(MentionTarget(open_id=open_id, name=name, key=key))
    return targets


def normalize_mentions(
    text: str,
    mentions: list[dict],
    bot_open_id: str,
) -> str:
    """Replace @_user_N placeholders with readable <at> tags.

    - Bot's placeholder is stripped entirely (avoid interfering with command parsing)
    - Other users' placeholders -> <at user_id="ou_xxx">name</at>
    - @_all -> @所有人

    Reference: OpenClaw bot-content.ts -> normalizeMentions()
    """
    for mention in mentions:
        key = mention.get("key", "")
        if not key:
            continue

        open_id = _extract_open_id(mention)
        name = mention.get("name", "")

        if key == "@_all":
            text = text.replace(key, "@所有人")
        elif open_id == bot_open_id:
            # Strip bot placeholder entirely
            text = text.replace(key, "")
        else:
            # Replace with readable <at> tag
            at_tag = f'<at user_id="{open_id}">{name}</at>'
            text = text.replace(key, at_tag)

    return text.strip()


# ──────────────── Outbound Formatting ────────────────


def format_mention_for_text(target: MentionTarget) -> str:
    """Format a mention target for text/post messages.

    Returns: <at user_id="ou_xxx">name</at>
    """
    return f'<at user_id="{target.open_id}">{target.name}</at>'


def format_mention_for_card(target: MentionTarget) -> str:
    """Format a mention target for card (interactive/lark_md) messages.

    Returns: <at id=ou_xxx></at>
    """
    return f"<at id={target.open_id}></at>"


def build_mentioned_message(
    targets: list[MentionTarget],
    message: str,
) -> str:
    """Prepend @ tags to message content for outbound text/post messages.

    Returns: "<at ...>name</at> <at ...>name</at> message"
    """
    if not targets:
        return message
    prefix = " ".join(format_mention_for_text(t) for t in targets)
    return f"{prefix} {message}"


def build_mentioned_card_content(
    targets: list[MentionTarget],
    message: str,
) -> str:
    """Prepend @ tags to message content for outbound card messages.

    Returns: "<at id=xxx></at> <at id=xxx></at> message"
    """
    if not targets:
        return message
    prefix = " ".join(format_mention_for_card(t) for t in targets)
    return f"{prefix} {message}"


def build_sender_mention_target(msg) -> MentionTarget | None:
    """Build a MentionTarget for the message sender (for outbound @back).

    In group chat, when a user @bot, the bot reply should @mention the sender
    so they get a notification. Returns None for p2p chats or if sender info
    is unavailable.
    """
    if msg.chat_type != "group":
        return None
    open_id = msg.sender_open_id or ""
    if not open_id:
        return None
    name = msg.sender_name or msg.user_id or ""
    return MentionTarget(open_id=open_id, name=name, key="")


def build_mention_system_hint(msg) -> str | None:
    """Build mention-related system hint for agent context injection.

    Two types of hints:
    1. If message has any @ tags -> tell agent that <at> tags are valid Feishu entities
    2. If group chat -> tell agent that system will auto @mention the sender back
    """
    hints: list[str] = []

    # Hint 1: <at> tag awareness — help the agent understand mention markup
    if msg.has_any_mention:
        hints.append(
            "[System: This message includes Feishu @-mention tags "
            '(formatted as <at user_id="...">name</at>). '
            "Treat each one as a reference to an actual user or bot.]"
        )

    # Hint 2: Outbound auto-@ notice
    # Gather everyone the system will @-notify when delivering the reply:
    #   • explicitly mentioned users (non-bot targets parsed from inbound)
    #   • the original sender (group-chat @back for notification)
    auto_mention_names: list[str] = []
    if msg.mentions:
        auto_mention_names.extend(t.name for t in msg.mentions)
    if msg.chat_type == "group" and msg.sender_open_id:
        sender_name = msg.sender_name or msg.user_id or "sender"
        auto_mention_names.append(sender_name)
    if auto_mention_names:
        names_str = ", ".join(auto_mention_names)
        hints.append(
            f"[System: The following users will be auto-notified via @ when "
            f"your reply is delivered: {names_str}. "
            "Do not include any @-mentions in your response text. "
            "The platform injects them automatically.]"
        )

    return "\n".join(hints) if hints else None
