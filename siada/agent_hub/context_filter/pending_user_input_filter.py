from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext

logger = logging.getLogger(__name__)


def _print_image_not_supported_error() -> None:
    """Print an image-not-supported error to the frontend via the IO singleton."""
    try:
        from siada.io.io import InputOutput

        io = InputOutput.get_instance()
        if io is not None:
            io.print_error(
                "⚠️ The current model does not support image input. "
                "Please provide a text message or switch to a model "
                "that supports image understanding."
            )
    except Exception:
        logger.error("Failed to print image-not-supported error", exc_info=True)


class PendingUserInputInjector:
    """
    Filter that injects queued user messages before each LLM call.

    When the agent is mid-turn (processing tool loops), messages arriving
    from the frontend are diverted to a module-level deque in
    stdin_interrupt_monitor rather than being queued for a new turn.

    This filter drains that deque and:
      1. Appends each message as a user-role item to model_data.input so
         the current LLM call sees the new context.
      2. Persists the items to FileSession via add_items() so they survive
         session reload and appear in the audit trail.

    MessageHistoryCaptureFilter (which runs next) will reset task_message_state
    from the updated model_data.input, so ApiMessageTransferFilter will
    naturally include the injected messages when building real_api_messages.
    """

    async def filter(
        self, model_data: ModelInputData, agent: Any, context: CodeAgentContext
    ) -> None:
        from siada.io.stdin_interrupt_monitor import drain_pending_injections, _send_queue_notification

        pending = drain_pending_injections()  # list of (id, content, image_paths)
        if not pending:
            return

        new_items = []
        # Track (id, content) pairs so the consume notification can carry the
        # original prompt text. The frontend uses this as a fallback to render
        # the user bubble even if its local preview queue was already cleared
        # (e.g. by the busy->idle drain), eliminating the "consumed but not
        # shown" race at the turn boundary.
        consumed_items: list = []

        # Reuse the exact same multimodal builder as the normal (non-queued)
        # turn flow so injected messages share an identical image-encoding
        # format (base64 data URL), avoiding any inconsistency.
        from siada.entrypoint.interaction.turn.conversation_turn import _build_multimodal_input

        for item_id, content, image_paths in pending:   # unpack 3-tuple
            # Defensive normalization: image_paths must be a list. A malformed
            # frontend payload could deliver a bare string (e.g. "a/b.png"),
            # which _build_multimodal_input would iterate character-by-character,
            # silently dropping the image and spamming per-char warnings. Coerce
            # any non-list value to None so we fall back to a plain text message.
            if image_paths is not None and not isinstance(image_paths, list):
                logger.warning(
                    "[PendingUserInputInjector] image_paths is not a list (%s), discarding",
                    type(image_paths).__name__,
                )
                image_paths = None

            # Guard: when the bound model cannot process images, image-only
            # messages (no text) are not actionable — print an error to the
            # frontend and skip. When there IS text, strip the images so the
            # agent still receives the text content.
            if image_paths:
                supports_images = True
                try:
                    siada_config = getattr(
                        getattr(context, "session", None), "siada_config", None
                    )
                    if siada_config is not None:
                        supports_images = bool(
                            getattr(siada_config.llm_config, "supports_images", True)
                        )
                except Exception:
                    pass
                if not supports_images:
                    # The frontend sends placeholder text like "[Image #1]"
                    # when the user pastes only images. Strip these and check
                    # if any real text remains.
                    import re
                    stripped_text = re.sub(
                        r"\[Image\s*#\d+\]", "", content or ""
                    ).strip()
                    if not stripped_text:
                        logger.info(
                            "[PendingUserInputInjector] model does not support "
                            "images and mid-turn message has no text; rejecting"
                        )
                        _print_image_not_supported_error()
                        if item_id:
                            consumed_items.append((item_id, content))
                        continue
                    # Has text — strip images, keep text only
                    logger.info(
                        "[PendingUserInputInjector] model does not support "
                        "images; stripped %d image(s) from mid-turn message",
                        len(image_paths),
                    )
                    image_paths = None

            if not content and not image_paths:
                continue
            if image_paths:
                new_items.extend(_build_multimodal_input(content, image_paths))
            else:
                new_items.append({"role": "user", "content": content})


            if item_id:
                consumed_items.append((item_id, content))


        if not new_items:
            return

        # Append to model input (will be seen by subsequent filters and LLM call).
        model_data.input = list(model_data.input) + new_items

        # Persist to FileSession so messages are durable.
        try:
            file_session = (
                context.session.openai_session
                if context and hasattr(context, "session") and context.session
                else None
            )
            if file_session is not None:
                await file_session.add_items(new_items)
                logger.info(
                    "[PendingUserInputInjector] Injected %d pending message(s) into session",
                    len(new_items),
                )
        except Exception as exc:
            logger.warning("[PendingUserInputInjector] Failed to persist injected items: %s", exc)

        # Notify frontend for each consumed item so the preview overlay can be
        # removed. Carry the original content so the frontend can render the
        # user bubble even when its local preview queue entry is already gone.
        for item_id, content in consumed_items:
            _send_queue_notification(
                "queue_item_consumed", {"id": item_id, "content": content}
            )
