"""GroupChatHandler - Group chat message processing for Lark IM.

Handles group-specific logic: trigger detection, pause commands,
pending history injection, sender formatting, and task interception.

Extracted from LarkController to isolate the group chat concern.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable, Optional

from siada.im.feishu.pending_history import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_KEYS,
    PendingHistoryBuffer,
    PendingHistoryEntry,
)

if TYPE_CHECKING:
    from siada.im.feishu.card_sender import LarkCardSender
    from siada.im.models import IMMessage

logger = logging.getLogger("siada.im.lark.group_handler")

# Pause keyword constants for group chat
GROUP_PAUSE_KEYWORDS = {"pause", "暂停"}


class GroupChatHandler:
    """Encapsulates group chat message processing logic.

    Responsibilities:
    - Trigger detection (@mention required)
    - Pause command handling
    - Pending history context injection
    - Running task interception (block new triggers while task is active)
    - Message content formatting with sender identification
    """

    def __init__(
        self,
        *,
        card_sender: "LarkCardSender",
        active_entries: dict,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        check_group_access: Optional[Callable[["IMMessage"], bool]] = None,
    ) -> None:
        self._card_sender = card_sender
        self._active_entries = active_entries
        self._check_group_access = check_group_access

        self._pending_history = PendingHistoryBuffer(
            limit=history_limit,
            max_keys=MAX_HISTORY_KEYS,
        )

    # ── Public API ────────────────────────────────────────────────────

    def resolve_task_key(self, msg: "IMMessage") -> str:
        """Resolve the task tracking key based on chat type.

        Both P2P and group use chat_id as task_key.
        Group: one task slot per group (any user's new trigger is blocked while running).
        """
        return msg.chat_id

    def should_handle(self, msg: "IMMessage") -> bool:
        """Check if a group message should trigger the agent.

        Only @mention triggers the bot in group chat.
        """
        return msg.mentioned_bot

    def record_pending_history(self, msg: "IMMessage") -> None:
        """Record a non-triggered group message into pending history."""
        self._pending_history.record(
            peer_id=msg.chat_id,
            entry=PendingHistoryEntry(
                sender=msg.sender_name or msg.user_id or msg.sender_open_id,
                content=msg.content,
                timestamp=time.time(),
                message_id=msg.message_id or "",
            ),
        )

    def inject_pending_context(self, msg: "IMMessage") -> "IMMessage":
        """Inject pending history context into the message when bot is triggered.

        Returns a new IMMessage with context-enriched content, or
        the original message if no pending history exists.
        """
        if msg.chat_type != "group":
            return msg

        enriched_content = self._pending_history.build_context(
            peer_id=msg.chat_id,
            current_message=msg.content,
        )

        if enriched_content == msg.content:
            return msg  # No pending history, no change

        return msg.with_content(enriched_content)

    def format_group_message_content(self, msg: "IMMessage") -> str:
        """Format group message with sender identification.

        Reference: OpenClaw bot.ts line 205 — speaker: messageBody
        """
        sender = msg.sender_name or msg.sender_en_name or msg.user_id or msg.sender_open_id
        return f"{sender}: {msg.content}"

    def enrich_for_agent(self, msg: "IMMessage") -> "IMMessage":
        """Enrich a group message before sending to the agent.

        Applies pending history injection and sender-prefix formatting.
        Should be called AFTER slash command detection (to keep raw content
        intact for command parsing) and BEFORE agent dispatch.
        """
        msg = self.inject_pending_context(msg)
        return msg.with_content(self.format_group_message_content(msg))

    def is_pause_command(self, msg: "IMMessage") -> bool:
        """Check if a group message is a pause command.

        Requires @mention + exact keyword (case-insensitive, stripped).
        e.g. "@bot pause", "@bot 暂停"
        """
        if msg.chat_type != "group":
            return False
        if not msg.mentioned_bot:
            return False
        text = msg.content.strip().lower()
        return text in GROUP_PAUSE_KEYWORDS

    @staticmethod
    def _is_btw_command(msg: "IMMessage") -> bool:
        """Return True if a group @bot message is a ``/btw`` slash command.

        Matches the controller's slash-command detection: the (stripped)
        content must start with ``/`` and its first token (minus the leading
        slash) must be exactly ``btw``.
        """
        content = (msg.content or "").strip()
        if not content.startswith("/"):
            return False
        first = content.split(None, 1)[0].lstrip("/").lower()
        return first == "btw"

    async def handle_pause(
        self, msg: "IMMessage", cancel_task_fn,
    ) -> bool:
        """Handle pause command for group chat.

        Cancels the running task in this group (shared slot by chat_id).
        Returns True if a task was paused, False otherwise.

        Args:
            cancel_task_fn: async callable(task_key) to cancel the active task.
        """
        task_key = self.resolve_task_key(msg)
        entry = self._active_entries.get(task_key)

        if not entry or not entry.is_running:
            return False

        logger.info("Pausing group task via pause command: task_key=%s", task_key)
        await cancel_task_fn(task_key)
        await self._card_sender.send_im(
            msg.request_id,
            msg.chat_id,
            "⏸️ 任务已暂停。你可以重新 @bot 发送新的指令。",
            content_type="text",
        )
        return True

    async def handle_trigger_interception(
        self, msg: "IMMessage", task_key: str,
    ) -> bool:
        """Handle group message trigger with running task interception.

        Returns True if the message was intercepted (caller should return early),
        False if the message should proceed to agent execution.
        """
        if msg.chat_type != "group":
            return False
        if not msg.mentioned_bot:
            return False

        entry = self._active_entries.get(task_key)
        if entry and entry.is_running:
            logger.info(
                "Group task running interception: task_key=%s, blocking new trigger",
                task_key,
            )
            await self._card_sender.send_im(
                msg.request_id,
                msg.chat_id,
                "⏳ 当前任务正在运行中，请等待完成。\n"
                f"💡 @我 并发送 {'/'.join(f'`{k}`' for k in sorted(GROUP_PAUSE_KEYWORDS))} 可以暂停当前任务。",
                content_type="text",
            )
            return True  # Intercepted

        return False  # Not intercepted, proceed normally

    async def gate_group_message(
        self,
        msg: "IMMessage",
        cancel_task_fn,
    ) -> Optional["IMMessage"]:
        """Group message gate: trigger detection + pre-processing.

        Returns the (possibly enriched) message to proceed with,
        or None if the message should be dropped.

        Args:
            cancel_task_fn: async callable(task_key) to cancel the active task.
        """
        logger.info(
            "gate_group_message enter: chat_id=%s, user_id=%s, sender_name=%s, sender_en_name=%s, mentioned_bot=%s, content=%r",
            msg.chat_id, msg.user_id, msg.sender_name, msg.sender_en_name, msg.mentioned_bot, msg.content[:80] if msg.content else "",
        )

        # Group-level access policy check (first gate)
        # Reference: OpenClaw bot.ts -> isFeishuGroupAllowed()
        # For unauthorized groups: silently drop non-@bot messages (no buffer),
        # only send "Access denied" reply when bot is explicitly @mentioned.
        if self._check_group_access is not None and not self._check_group_access(msg):
            if msg.mentioned_bot:
                logger.info(
                    "Group %s blocked by group_policy, sending access denied for @bot message", msg.chat_id,
                )
                await self._card_sender.send_im(
                    msg.request_id,
                    msg.chat_id,
                    f"⚠️ Access denied. This group is not in the allowlist.\n"
                    f"Please contact the admin to configure access.\n\n"
                    f"Group key: {msg.chat_id}",
                    content_type="text",
                )
            else:
                logger.info(
                    "Group %s blocked by group_policy, silently dropping message", msg.chat_id,
                )
            return None

        # Must @bot to trigger; otherwise buffer as pending history
        if not self.should_handle(msg):
            logger.info("Message not mentioning bot, buffering as pending history: chat_id=%s", msg.chat_id)
            self.record_pending_history(msg)
            return None

        # /btw is a read-only side question that runs concurrently in its own
        # thread without touching the main conversation. In groups it must NOT
        # be blocked by the running-task interception (nor treated as a pause),
        # so let it pass straight through to the slash-command handler, which
        # enforces its own per-chat single-flight guard and never interrupts
        # the main agent.
        if self._is_btw_command(msg):
            logger.info("Group /btw side question passes through gate: chat_id=%s", msg.chat_id)
            return msg

        # Check pause command (@bot pause / @bot 暂停)
        if self.is_pause_command(msg):
            logger.info("Pause command detected: chat_id=%s", msg.chat_id)
            if await self.handle_pause(msg, cancel_task_fn):
                logger.info("Task paused successfully: chat_id=%s", msg.chat_id)
                return None  # Task paused
            logger.info("No active task to pause, treating as normal message: chat_id=%s", msg.chat_id)
            # If no task to pause, treat as normal message

        # Running task interception (block if same user has running task)
        task_key = self.resolve_task_key(msg)
        logger.info("Checking trigger interception: task_key=%s", task_key)
        if await self.handle_trigger_interception(msg, task_key):
            logger.info("Message intercepted by running task: task_key=%s", task_key)
            return None

        logger.info("gate_group_message pass-through: task_key=%s, content=%r", task_key, msg.content[:80] if msg.content else "")
        return msg
