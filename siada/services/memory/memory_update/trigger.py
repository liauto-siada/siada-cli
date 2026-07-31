"""Trigger strategies — decide whether a memory update should run."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext


class MemoryUpdateTrigger(ABC):
    """Abstract policy: "should we run a memory update right now?".

    Implementations are queried on the synchronous fast-path of
    ``ApiMessageTransferFilter.filter`` so they must be:

    * cheap — no I/O, no LLM calls, just predicate logic;
    * exception-tolerant — any raised exception is interpreted as
      "do not trigger" by the scheduler, never propagated.
    """

    @abstractmethod
    def should_trigger(
        self,
        *,
        context: "CodeAgentContext",
        tokens_count: int,
        item_count: int,
    ) -> bool:
        """Return ``True`` to request a memory update for this turn."""
        ...


class PreCompactionTrigger(MemoryUpdateTrigger):
    """Default trigger: align with the existing compaction strategy.

    Reuses ``CompactionStrategy.should_compact`` so we capture memory at
    exactly the moment the message stream is about to lose information
    to summarization. Benefits:

    * sparse by construction — short sessions never trigger;
    * synchronized with information loss — captured snapshot is the
      richest possible view before mutation;
    * no extra threshold to maintain.
    """

    def should_trigger(
        self,
        *,
        context: "CodeAgentContext",
        tokens_count: int,
        item_count: int,
    ) -> bool:
        try:
            # Local import to avoid pulling compaction strategy types
            # into the module's load-time graph (they pull in tokenizer
            # heavy deps).
            from siada.agent_hub.context_filter.compaction_strategy import (
                get_compaction_strategy,
            )

            strategy = get_compaction_strategy(context)
            return bool(
                strategy.should_compact(tokens_count, context.model_run_config)
            )
        except Exception as e:
            # Trigger predicates never raise — defensive log + treat as
            # "do not trigger" so we never block / break the LLM call.
            logger.warning(f"[memory-update] PreCompactionTrigger failed: {e}")
            return False
