"""Lark typing indicator via Message Reaction API (lark-oapi SDK).

Adds a "Typing" emoji reaction to the user's message when the bot starts
processing, and removes it when done. This gives visual feedback similar
to a "typing..." indicator in chat apps.

Uses lark-oapi SDK Client (passed in externally) for API calls.
The SDK handles tenant_access_token refresh internally.

API reference:
- Add: POST /im/v1/messages/{message_id}/reactions
- Delete: DELETE /im/v1/messages/{message_id}/reactions/{reaction_id}

Inspired by openclaw's typing.ts implementation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("siada.im.typing_indicator")

# Lark emoji type for typing indicator
# See: https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce
TYPING_EMOJI = "Typing"

# Max age for a message to receive typing indicator (2 min)
# Older messages are likely replays and should not trigger notifications.
TYPING_MAX_AGE_MS = 2 * 60_000

# Lark API error codes that indicate rate-limit / quota exceeded
BACKOFF_CODES = {99991400, 99991403, 429}


@dataclass
class TypingState:
    """Tracks the current typing indicator state for a message."""

    message_id: str
    reaction_id: Optional[str] = None


class LarkTypingIndicator:
    """Manages typing indicator (emoji reaction) on Lark messages.

    Accepts an existing lark-oapi Client instance (shared with LarkCardSender)
    to avoid duplicating client/token management.

    Usage:
        indicator = LarkTypingIndicator(lark_client)
        state = await indicator.add(message_id)
        # ... bot processes message ...
        await indicator.remove(state)
    """

    def __init__(self, client):
        """Initialize with an existing lark-oapi Client instance.

        Args:
            client: A lark_oapi.Client with auto token management.
        """
        self._client = client

    async def add(
        self,
        message_id: str,
        message_create_time_ms: Optional[float] = None,
    ) -> TypingState:
        """Add typing indicator (Typing emoji reaction) to a message.

        Args:
            message_id: The Lark message ID to react to.
            message_create_time_ms: Optional epoch ms of the message creation.
                If provided and the message is older than TYPING_MAX_AGE_MS,
                the indicator is skipped (avoids stale notifications on replays).

        Returns:
            TypingState with reaction_id if successful, None reaction_id otherwise.
        """
        if not message_id:
            return TypingState(message_id="", reaction_id=None)

        # Skip old messages to avoid stale notifications
        if message_create_time_ms is not None:
            age_ms = time.time() * 1000 - message_create_time_ms
            if age_ms > TYPING_MAX_AGE_MS:
                logger.debug(
                    f"Skipping typing indicator for old message "
                    f"(age={age_ms:.0f}ms > {TYPING_MAX_AGE_MS}ms)"
                )
                return TypingState(message_id=message_id, reaction_id=None)

        try:
            from lark_oapi.api.im.v1 import (
                CreateMessageReactionRequest,
                CreateMessageReactionRequestBody,
                Emoji,
            )

            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(
                        Emoji.builder()
                        .emoji_type(TYPING_EMOJI)
                        .build()
                    )
                    .build()
                ) \
                .build()

            response = await asyncio.to_thread(
                self._client.im.v1.message_reaction.create, request
            )

            if not response.success():
                code = response.code
                if code in BACKOFF_CODES:
                    logger.warning(
                        f"Typing indicator hit rate-limit: code={code}"
                    )
                else:
                    logger.debug(
                        f"Failed to add typing indicator: "
                        f"code={code} msg={response.msg}"
                    )
                return TypingState(message_id=message_id, reaction_id=None)

            reaction_id = response.data.reaction_id if response.data else None
            logger.debug(
                f"Typing indicator added: message_id={message_id}, "
                f"reaction_id={reaction_id}"
            )
            return TypingState(
                message_id=message_id, reaction_id=reaction_id
            )

        except Exception as e:
            logger.debug(f"Failed to add typing indicator: {e}")
            return TypingState(message_id=message_id, reaction_id=None)

    async def remove(self, state: TypingState) -> None:
        """Remove typing indicator (delete the emoji reaction).

        Args:
            state: TypingState returned by add(). If reaction_id is None, this is a no-op.
        """
        if not state or not state.reaction_id:
            return

        try:
            from lark_oapi.api.im.v1 import DeleteMessageReactionRequest

            request = DeleteMessageReactionRequest.builder() \
                .message_id(state.message_id) \
                .reaction_id(state.reaction_id) \
                .build()

            response = await asyncio.to_thread(
                self._client.im.v1.message_reaction.delete, request
            )

            if not response.success():
                code = response.code
                if code in BACKOFF_CODES:
                    logger.warning(
                        f"Typing indicator removal hit rate-limit: code={code}"
                    )
                else:
                    logger.debug(
                        f"Failed to remove typing indicator: "
                        f"code={code} msg={response.msg}"
                    )
                return

            logger.debug(
                f"Typing indicator removed: message_id={state.message_id}"
            )

        except Exception as e:
            logger.debug(f"Failed to remove typing indicator: {e}")
