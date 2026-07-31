"""Shared reasoning-content replay hook for all Chat Completions providers.

The SDK default (``default_should_replay_reasoning_content``) only replays
reasoning content for DeepSeek models.  This module provides a project-wide
hook that extends the replay to GLM models (e.g. glm-5.1, glm-5.2) as well,
so that reasoning/thinking content is preserved across multi-turn tool-call
conversations regardless of which provider is used.

Usage:
    # In providers that call Converter.items_to_messages directly:
    from siada.provider.reasoning_replay import should_replay_reasoning_content
    Converter.items_to_messages(..., should_replay_reasoning_content=should_replay_reasoning_content)

    # In providers that instantiate LitellmModel:
    from siada.provider.reasoning_replay import should_replay_reasoning_content
    LitellmModel(..., should_replay_reasoning_content=should_replay_reasoning_content)
"""

from __future__ import annotations

from agents.models.reasoning_content_replay import (
    ReasoningContentReplayContext,
    default_should_replay_reasoning_content,
)

# Model-family keywords that require reasoning-content replay in addition to
# the SDK default (DeepSeek).
_REASONING_REPLAY_MODEL_KEYWORDS: tuple[str, ...] = ("glm", "kimi")


def should_replay_reasoning_content(context: ReasoningContentReplayContext) -> bool:
    """Decide whether to replay reasoning content into the next assistant message.

    Extends the SDK default (which only replays for DeepSeek) to also replay
    for GLM (e.g. glm-5.1, glm-5.2) and Kimi (e.g. kimi-k3) models so that
    reasoning/thinking content is preserved across multi-turn tool-call
    conversations.

    The origin-model check prevents cross-model contamination: reasoning from
    a DeepSeek model will not be replayed into a GLM request, and vice versa.
    """
    model_lower = context.model.lower()
    for keyword in _REASONING_REPLAY_MODEL_KEYWORDS:
        if keyword in model_lower:
            origin_model = context.reasoning.origin_model
            return (
                origin_model is not None and keyword in origin_model.lower()
            ) or context.reasoning.provider_data == {}
    return default_should_replay_reasoning_content(context)
