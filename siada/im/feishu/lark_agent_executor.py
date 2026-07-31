"""Agent execution and task lifecycle component for LarkController.

Handles:
- Task cancellation and interrupt markers
- Session ownership acquire/release
- User input building (mention hints)
- Agent execution via SiadaRunner
- Task dispatch with lifecycle callbacks
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from agents import RunResultStreaming

from siada.foundation.code_agent_context import RuntimeSource
from siada.im.feishu.mention import build_sender_mention_target
from siada.im.feishu.prompt_injection import (
    build_inbound_user_context_suffix,
    build_quoted_message_block,
)
from siada.im.feishu.quoted_message_resolver import QuotedMessage, QuotedMessageResolver
from siada.im.models import MentionTarget
from siada.im.feishu.utils import format_exception_for_user, get_default_workspace

if TYPE_CHECKING:
    from siada.entrypoint.interaction.lark_controller import LarkController
    from siada.im.models import IMMessage
    from siada.session.session_models import RunningSession

logger = logging.getLogger("siada.im.lark.controller")


@dataclass
class ActiveTaskEntry:
    """Unified per-chat active task state.

    Replaces the three separate dicts (_active_tasks, _active_sessions,
    _active_results) with a single structure keyed by task_key.

    Fields are populated incrementally during the task lifecycle:
    - task: set in dispatch_task() when the asyncio.Task is created
    - session: set in run_agent_for_message() after ownership is acquired
    - result: set in run_agent_for_message() after SiadaRunner returns
    """

    task: asyncio.Task
    session: Optional["RunningSession"] = field(default=None)
    result: Optional[RunResultStreaming] = field(default=None)

    @property
    def is_running(self) -> bool:
        """Whether the underlying asyncio task is still running."""
        return not self.task.done()


class LarkAgentExecutor:
    """Agent execution and task lifecycle for LarkController.

    Encapsulates task cancellation, session ownership management,
    agent invocation via SiadaRunner, and stream consumption.
    """

    def __init__(self, ctrl: "LarkController") -> None:
        self._ctrl = ctrl
        lark_cfg = ctrl._config.get("lark", {})
        self._include_conversation_info: bool = (
            (lark_cfg.get("context") or {}).get("include_conversation_info", False)
        )

    # ── Task cancellation & interrupt ────────────────────────────────

    async def cancel_active_task(self, task_key: str) -> None:
        """Cancel the currently running task for a task_key, if any."""
        ctrl = self._ctrl
        entry = ctrl._active_entries.get(task_key)
        logger.debug(
            "[cancel_active_task] task_key=%s, has_entry=%s",
            task_key, entry is not None,
        )
        await ctrl._card_sender.remove_typing(task_key)

        if entry is None:
            return

        # Remove from registry first to prevent re-entrant access
        ctrl._active_entries.pop(task_key, None)

        # Cancel the streaming result
        if entry.result:
            try:
                entry.result.cancel()
                logger.info("Cancelled streaming result for task_key=%s", task_key)
            except Exception as e:
                logger.debug("Error cancelling streaming result: %s", e)

        # Cancel the asyncio task
        if entry.task and not entry.task.done():
            logger.info("Cancelling active task for task_key=%s", task_key)
            entry.task.cancel()
            try:
                await entry.task
            except (asyncio.CancelledError, Exception):
                pass
            logger.info("Active task cancelled for task_key=%s", task_key)

        # Add interrupt marker to session history
        if entry.session and entry.session.openai_session:
            try:
                await self._add_interrupt_marker(entry.session)
            except Exception as e:
                logger.debug("Error adding interrupt marker: %s", e)

    async def _add_interrupt_marker(self, session: "RunningSession") -> None:
        """Add interrupt note to session history."""
        from agents.models.chatcmpl_converter import Converter

        history = await session.openai_session.get_items()
        if not history:
            return

        last_item = history[-1]
        interrupt_note = {
            "role": "user",
            "content": "Note: This Conversation Was Interrupted By User",
        }

        should_add_note = any(
            [
                Converter.maybe_input_message(last_item),
                Converter.maybe_easy_input_message(last_item),
                Converter.maybe_function_tool_call_output(last_item),
            ]
        )

        if should_add_note:
            await session.openai_session.add_items([interrupt_note])
            logger.info("Added interrupt marker to session %s", session.session_id)

    # ── Session ownership ─────────────────────────────────────────────

    def _acquire_ownership(
        self, session: "RunningSession", workspace: str,
    ) -> Optional[Path]:
        """Acquire Lark ownership for a session directory.

        Returns the session_dir Path on success, or None if ownership
        could not be acquired (e.g. CLI is using the session).
        """
        from siada.session.ownership import (
            SessionOwnershipManager, SessionOwner, OwnershipError,
        )
        session_dir = self._ctrl._get_session_dir(session.session_id, workspace)
        try:
            SessionOwnershipManager.acquire_ownership(session_dir, SessionOwner.LARK)
            logger.debug(
                "Ownership acquired: session_id=%s, session_dir=%s",
                session.session_id, session_dir,
            )
            return session_dir
        except OwnershipError:
            logger.warning(
                "Session %s is currently owned by CLI, cannot acquire for Lark",
                session.session_id,
            )
            return None

    @staticmethod
    def _release_ownership(session_dir: Path) -> None:
        """Release Lark ownership for a session directory."""
        from siada.session.ownership import SessionOwnershipManager, SessionOwner
        SessionOwnershipManager.release_ownership(session_dir, SessionOwner.LARK)
        logger.debug("Ownership released: session_dir=%s", session_dir)

    # ── User input building ───────────────────────────────────────────

    def _build_user_input(self, msg: "IMMessage") -> str:
        """Build final user input with quoted reply context and optional suffix.

        Injection order:
          1. Quoted message block (always-on when resolved, no switch)
          2. User's actual message content
          3. Context suffix (conversation info, mention hints — switch-controlled)

        Both injection blocks are wrapped with IM-context sentinel markers
        (see ``siada.services.memory.holographic.marker``) so downstream
        consumers — frontend renderer, MemoryReviewAgent — can strip them
        out and never confuse them with user-authored text. The LLM still
        sees the full block; the markers are just inert HTML comments.
        """
        from siada.services.memory.holographic.marker import wrap_im_context_block

        parts: list[str] = []

        # Quoted message context — always injected when available (no switch)
        quoted_block = build_quoted_message_block(msg)
        if quoted_block:
            parts.append(wrap_im_context_block(quoted_block).rstrip("\n"))

        parts.append(msg.content)

        # Optional context suffix (switch-controlled)
        suffix = build_inbound_user_context_suffix(
            msg, include_conversation_info=self._include_conversation_info,
        )
        if suffix:
            parts.append(wrap_im_context_block(suffix).rstrip("\n"))

        user_input = "\n\n".join(parts)
        if quoted_block or suffix:
            logger.debug(
                "[_build_user_input] context injected (quoted=%s, suffix=%s), "
                "total input_len=%d",
                bool(quoted_block), bool(suffix), len(user_input),
            )
        return user_input

    # ── Quoted message resolution ─────────────────────────────────────

    async def _resolve_quoted_message(
        self, msg: "IMMessage", session: "RunningSession",
    ) -> "Optional[QuotedMessage]":
        """Resolve quoted/replied message content and populate msg fields.

        Calls Feishu im.v1.message.get API to fetch the parent message content.
        Regular session history items do NOT store Feishu message_id, so local
        lookup is not feasible — always goes to API.

        Populates msg.quoted_content and msg.quoted_sender on success.
        Returns the resolved QuotedMessage object (or None) so callers can
        extract media keys from the quoted message without a second round-trip.
        Gracefully degrades (returns None) on failure — never blocks the main flow.
        """
        if not msg.parent_id:
            return None

        # If quoted_content is already populated (e.g. by thread_router for
        # IPC cross-session reply), skip API fetch to avoid overwriting.
        if msg.quoted_content:
            return None

        try:
            # Get lark client from card_sender (shared credentials)
            lark_client = self._ctrl._card_sender._get_lark_client()
            resolver = QuotedMessageResolver(lark_client=lark_client)

            quoted = await resolver.resolve(msg.parent_id)
            if quoted:
                msg.quoted_content = quoted.content
                msg.quoted_sender = quoted.sender_name or quoted.sender_id
                logger.debug(
                    "[_resolve_quoted_message] resolved: parent_id=%s, "
                    "sender=%s, content_len=%d",
                    msg.parent_id,
                    msg.quoted_sender,
                    len(msg.quoted_content) if msg.quoted_content else 0,
                )
            return quoted
        except Exception as e:
            # Graceful degradation: log and continue without quoted content
            logger.warning(
                "Failed to resolve quoted message: parent_id=%s, error=%s",
                msg.parent_id, e,
            )
            return None

    # ── Media collection ──────────────────────────────────────────────

    async def _collect_media(
        self,
        msg: "IMMessage",
        quoted_msg: "Optional[QuotedMessage]",
        session_dir: Path,
    ) -> list:
        """Download media attachments for this turn and return them as a list.

        Scope rules (group-chat safe):
          1. Trigger message itself   — msg.feishu_media_keys
          2. First-level quoted/reply — quoted_msg.raw_content_json (if any)
          Never processes buffered history messages.

        Files are persisted under <session_dir>/feishu_media/ so the same
        attachment is never downloaded twice within a session.
        """
        from siada.im.feishu.media import (
            download_message_resource,
            extract_media_keys_from_message,
        )

        ctrl = self._ctrl
        media_cache_dir = session_dir / "feishu_media"
        lark_client = None   # lazy: only created when there is actual work to do
        collected: list = []

        # 1. Media from the trigger message (@bot message itself)
        if msg.feishu_media_keys and msg.message_id:
            lark_client = lark_client or ctrl._card_sender._get_lark_client()
            for mk in msg.feishu_media_keys:
                media = await download_message_resource(
                    lark_client, msg.message_id, mk.key, mk.resource_type,
                    cache_dir=media_cache_dir,
                )
                if media:
                    collected.append(media)

        # 2. Media from the first-level quoted/replied parent message only.
        #    No deeper traversal; never touches buffered group-chat history.
        if msg.parent_id and quoted_msg and quoted_msg.raw_content_json:
            parent_pairs = extract_media_keys_from_message(
                quoted_msg.raw_content_json, quoted_msg.msg_type,
            )
            if parent_pairs:
                lark_client = lark_client or ctrl._card_sender._get_lark_client()
                for key, rt in parent_pairs:
                    media = await download_message_resource(
                        lark_client, msg.parent_id, key, rt,
                        cache_dir=media_cache_dir,
                    )
                    if media:
                        collected.append(media)
                logger.info(
                    "[_collect_media] %d media key(s) from quoted parent: parent_id=%s",
                    len(parent_pairs), msg.parent_id,
                )

        return collected

    # ── Image support guard ───────────────────────────────────────────

    @staticmethod
    def _model_supports_images(session: "RunningSession") -> bool:
        """Whether the bound model can accept image input.

        Reads ``supports_images`` from the session's llm_config (a
        ``ModelRunConfig``). Defaults to ``True`` on any access error so
        that a misconfigured model never causes a false rejection.
        """
        try:
            return bool(session.siada_config.llm_config.supports_images)
        except Exception:
            logger.error(
                "Failed to read supports_images from session config; "
                "defaulting to True",
                exc_info=True,
            )
            return True

    @staticmethod
    def _has_meaningful_text(msg: "IMMessage") -> bool:
        """Check whether the message carries text the agent can act on.

        Feishu renders image/file/audio/video/sticker messages as a
        placeholder string like ``'[image: img_xxx]'`` — not real user
        text.  When the bound model cannot process images, such
        placeholders leave the agent with nothing actionable, so they are
        treated as "no text".

        Edge case: ``post`` (rich-text) messages that contain *only*
        image nodes (no text/title/at elements) cause
        ``_extract_post_text`` to fall back to ``str(data)`` — a raw dict
        string starting with ``'{'``.  That is also treated as "no text".
        """
        import re

        content = (msg.content or "").strip()
        if not content:
            return False

        # Media-only message types always produce placeholder content.
        if msg.content_type in ("image", "file", "audio", "video", "sticker"):
            return False

        # For text/post messages, strip inline media placeholders and
        # check whether any real text remains.
        stripped = re.sub(
            r"\[(?:image|file|audio|video|sticker):\s*[^\]]+\]",
            "",
            content,
        ).strip()

        # Post messages with only image nodes fall back to str(data),
        # producing a raw dict string — not meaningful user text.
        if msg.content_type == "post" and stripped.startswith("{"):
            return False

        return bool(stripped)

    async def _filter_media_for_image_support(
        self,
        msg: "IMMessage",
        session: "RunningSession",
        downloaded_media: list,
    ) -> "Optional[list]":
        """Filter media list based on model image-support capability.

        When the bound model cannot process images:
        - Image-only messages (no meaningful text) are rejected early with
          an error sent to the user; returns None to signal abort.
        - Text+image messages have images stripped (documents kept);
          returns the filtered list.

        When the model supports images (or there are no images), returns
        the original list unchanged.
        """
        if not downloaded_media or self._model_supports_images(session):
            return downloaded_media

        has_images = any(m.is_image for m in downloaded_media)
        if not has_images:
            return downloaded_media

        if not self._has_meaningful_text(msg):
            logger.info(
                "[run_agent_for_message] model does not support images "
                "and message has no text content; rejecting image-only input"
            )
            ctrl = self._ctrl
            await ctrl._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ The current model does not support image input. "
                "Please send a text message or switch to a model that "
                "supports image understanding.",
                content_type="text",
            )
            return None

        # Model can't handle images but there is text — strip images
        # and keep documents so the agent still receives file hints.
        image_count = sum(1 for m in downloaded_media if m.is_image)
        filtered = [m for m in downloaded_media if not m.is_image]
        logger.info(
            "[run_agent_for_message] model does not support images; "
            "stripped %d image(s), keeping %d document(s)",
            image_count, len(filtered),
        )
        return filtered

    # ── Agent execution ───────────────────────────────────────────────


    async def run_agent_for_message(
        self, msg: "IMMessage", session: "RunningSession",
    ) -> None:
        """Core agent execution logic, runs inside a cancellable Task."""
        ctrl = self._ctrl
        start_time = time.time()
        logger.info(
            "Processing message: request_id=%s, user=%s, session_id=%s, content=%s...",
            msg.request_id, msg.user_id, session.session_id, msg.content[:50],
        )

        ctrl._lark_io.set_context(msg.request_id, msg.chat_id)
        await ctrl._card_sender.add_typing(msg)

        workspace = session.siada_config.workspace or ctrl._workspace or get_default_workspace()
        session_dir = self._acquire_ownership(session, workspace)

        if not session_dir:
            await ctrl._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ This session is currently being used by CLI. "
                "Please wait for the current turn to finish.",
                content_type="text",
            )
            await ctrl._card_sender.remove_typing(msg.chat_id)
            return

        # Track downloaded media for cleanup in finally block
        downloaded_media = []

        try:
            from siada.services.siada_runner import SiadaRunner

            # Update entry with session for interrupt handling
            task_key = ctrl._resolve_task_key(msg)
            entry = ctrl._active_entries.get(task_key)
            if entry is not None:
                entry.session = session
            ctrl._session_resolver.ensure_in_cache(session)

            # Resolve quoted/replied message content (always-on, no switch).
            # Returns the QuotedMessage object so we can extract media from it below.
            quoted_msg = await self._resolve_quoted_message(msg, session)

            user_input = self._build_user_input(msg)

            # Download all in-scope media attachments for this turn
            downloaded_media = await self._collect_media(msg, quoted_msg, session_dir)

            # Guard: filter media based on model image support.
            filtered = await self._filter_media_for_image_support(
                msg, session, downloaded_media
            )
            if filtered is None:
                return
            downloaded_media = filtered

            if downloaded_media:
                from siada.im.feishu.media import build_multimodal_input_with_media
                user_input = build_multimodal_input_with_media(user_input, downloaded_media)
                logger.info(
                    "[run_agent_for_message] multimodal input: "
                    "%d items (images=%d, docs=%d, cached=%d)",
                    len(downloaded_media),
                    sum(1 for m in downloaded_media if m.is_image),
                    sum(1 for m in downloaded_media if m.is_document),
                    sum(1 for m in downloaded_media if m.cached),
                )

            logger.info(
                "[run_agent_for_message] SiadaRunner.run_agent: agent=%s, "
                "workspace=%s, session_id=%s",
                ctrl._agent_name, workspace, session.session_id,
            )
            result: RunResultStreaming = await SiadaRunner.run_agent(
                agent_name=ctrl._agent_name,
                user_input=user_input,
                workspace=workspace,
                session=session,
                stream=True,
                runtime_source=RuntimeSource.LARK_CONTROLLER,
            )
            # Update entry with streaming result
            if entry is not None:
                entry.result = result

            # Build outbound mention targets:
            # 1. Non-bot mention targets from inbound message (e.g. @周鑫每)
            # 2. Sender @back target (group chat auto @sender notification)
            # Reference: OpenClaw bot.ts -> parseFeishuMessageEvent + reply-dispatcher
            outbound_mentions: list[MentionTarget] = []
            if msg.mentions:
                outbound_mentions.extend(msg.mentions)
            sender_target = build_sender_mention_target(msg)
            if sender_target:
                outbound_mentions.append(sender_target)

            verbose = ctrl._verbose_config.is_verbose(msg.chat_id, msg.chat_type)
            await ctrl._stream_consumer.consume_stream(
                result, msg.request_id, msg.chat_id, workspace,
                mention_targets=outbound_mentions or None,
                verbose=verbose,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Message processed: request_id=%s, session_id=%s, duration=%dms",
                msg.request_id, session.session_id, elapsed_ms,
            )

        finally:
            # Clean up downloaded temp media files regardless of success/failure
            if downloaded_media:
                from siada.im.feishu.media import cleanup_media_files
                cleanup_media_files(downloaded_media)
            self._release_ownership(session_dir)
            await ctrl._card_sender.remove_typing(msg.chat_id)
            if hasattr(ctrl._transport, "send_ack"):
                await ctrl._transport.send_ack(msg.request_id)

    # ── Task dispatch ─────────────────────────────────────────────────

    def dispatch_task(
        self, msg: "IMMessage", session: "RunningSession", task_key: str,
    ) -> None:
        """Create a fire-and-forget agent task with lifecycle callbacks."""
        ctrl = self._ctrl
        logger.debug(
            "[dispatch_task] task_key=%s, session_id=%s, "
            "chat_id=%s, active_entries_count=%d",
            task_key, session.session_id, msg.chat_id, len(ctrl._active_entries),
        )
        task = asyncio.create_task(self.run_agent_for_message(msg, session))
        ctrl._active_entries[task_key] = ActiveTaskEntry(task=task)

        def _on_task_done(t: asyncio.Task, _task_key=task_key, _msg=msg):
            """Callback to handle task completion, cancellation, or error."""
            # Clean up entry only if it still references this task
            entry = ctrl._active_entries.get(_task_key)
            if entry is not None and entry.task is t:
                ctrl._active_entries.pop(_task_key, None)

            if t.cancelled():
                logger.info("Task for task_key=%s was interrupted by user", _task_key)
                asyncio.ensure_future(ctrl._card_sender.send_im(
                    _msg.request_id, _msg.chat_id,
                    "⏹️ Previous task interrupted by user.",
                    content_type="text",
                ))
            elif t.exception():
                exc = t.exception()
                logger.error("Task for task_key=%s failed: %s", _task_key, exc, exc_info=exc)
                asyncio.ensure_future(ctrl._card_sender.send_im(
                    _msg.request_id, _msg.chat_id,
                    f"❌ Agent execution failed: {format_exception_for_user(exc)}",
                    content_type="text",
                ))

            # IPC drain: only for P2P tasks, skip group chat
            if _msg.chat_type == "p2p":
                asyncio.ensure_future(ctrl._drain_pending_ipc_messages())
            else:
                logger.debug("Skipping IPC drain for group task: task_key=%s", _task_key)

        task.add_done_callback(_on_task_done)
