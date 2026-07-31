"""
Model Hallucination Suppression Processor

Some smaller / weaker models tend to loop: they re-issue tool calls or output
turn after turn without adapting to new information. This processor
periodically injects a lightweight reminder into the LLM input nudging the
model to vary its approach instead of repeating itself unchanged.

Currently scoped to `kivy-deepseek-v4-flash` only — this is the sole model
observed to exhibit this behaviour in practice. Other models are left
untouched to avoid polluting their context with an irrelevant reminder.
"""

from typing import Any, Optional

from agents import (
    Agent,
    AgentHooks,
    ModelResponse,
    RunContextWrapper,
    TContext,
    TResponseInputItem,
    Tool,
)

from siada.agent_hub.hooks.processors.reminder_persistence_utils import (
    persist_pending_reminder_items,
)
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger

# Models this processor is scoped to. Keep as a set so more models can be
# added later without changing the trigger logic.
_TARGET_MODELS = {"kivy-deepseek-v4-flash"}

# Remind every N LLM calls, starting from the very first one (call #1, #21,
# #41, ...).
_REMINDER_INTERVAL = 20

_REMINDER_TEXT = (
    "Do not repeat the same action unchanged. Vary the tool arguments or "
    "method, inspect the latest result, or ask the user for the missing "
    "information and avoid repeating the same output."
)
class ModelHallucinationSuppressionProcessor(AgentHooks):
    """Periodically nudge the target model to avoid repeating itself."""

    def _current_model_name(self, context: RunContextWrapper[CodeAgentContext]) -> Optional[str]:
        try:
            session = getattr(context.context, "session", None)
            cfg = getattr(session, "siada_config", None)
            return getattr(cfg.llm_config, "model_name", None) if cfg else None
        except Exception:
            return None

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        try:
            if self._current_model_name(context) not in _TARGET_MODELS:
                return
            if not isinstance(input_items, list):
                return

            # Track the LLM call count per session so the interval survives
            # across turns (mirrors CacheStatusProcessor's session.state usage).
            session = context.context.session
            state = getattr(session.state, "hallucination_suppression_state", None) or {}
            call_count = state.get("llm_call_count", 0) + 1
            state["llm_call_count"] = call_count
            session.state.hallucination_suppression_state = state

            if call_count % _REMINDER_INTERVAL != 1:
                return

            reminder_item = {"role": "user", "content": _REMINDER_TEXT}
            input_items.append(reminder_item)

            # Also stage a copy on our own queue for durable persistence
            # into the real Session (drained in our own on_llm_end below).
            # Without this, the reminder would only affect this single LLM
            # call and vanish the moment it returns, never showing up in
            # api_history.json for future turns / session resume.
            pending = getattr(context.context, "pending_hallucination_reminder_items", None)
            if pending is not None:
                pending.append(dict(reminder_item))

            logger.debug(
                "[ModelHallucinationSuppression] injected reminder at llm_call_count=%d",
                call_count,
            )
        except Exception as e:
            logger.debug(f"[ModelHallucinationSuppression] on_llm_start failed: {e}")

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Drain our own pending queue into the real Session, independent of
        any other processor's hook registration / ordering.
        """
        siada_context = context.context
        pending = getattr(siada_context, "pending_hallucination_reminder_items", None) or []
        try:
            await persist_pending_reminder_items(
                getattr(siada_context, "session", None),
                pending,
                "ModelHallucinationSuppression",
            )
        finally:
            if hasattr(siada_context, "pending_hallucination_reminder_items"):
                siada_context.pending_hallucination_reminder_items = []

    # No-op implementations for the rest of the AgentHooks contract.
    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        pass
