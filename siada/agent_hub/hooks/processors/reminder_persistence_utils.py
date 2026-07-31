"""
Shared helper for draining a processor-local "pending reminder items" queue
into the real Session on AgentHooks.on_llm_end.

Several on_llm_start processors (TodoReminderProcessor,
ModelHallucinationSuppressionProcessor, ...) inject a hidden reminder
directly into the real per-call ``input_items`` list -- which only affects
the single LLM call currently in flight, since the SDK's Runner loop only
reads ``session.get_items()`` once at the very start of a run. To survive in
``api_history.json`` for future turns / session resume, each such reminder
must also be staged on its own queue and drained into the Session here,
right after the LLM call succeeds -- mirroring how the SDK itself persists
real conversation turns via ``save_result_to_session() -> session.add_items()``.

Each processor owns its own queue (e.g. a dedicated field on
CodeAgentContext) so that persistence never depends on hook registration
order between processors -- this helper only implements the shared
"drain into session.add_items(), clear queue, never raise" mechanics.
"""

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


async def persist_pending_reminder_items(
    session: Optional[Any],
    pending: List[Any],
    processor_name: str,
) -> None:
    """Persist ``pending`` items into ``session``'s real Session, if any.

    Never raises -- persistence errors must not break the turn, since the
    reminder already had its immediate effect via the ephemeral
    on_llm_start injection; losing the durable copy is a degradation, not
    a failure.
    """
    if not pending:
        return
    try:
        openai_session = getattr(session.state, "openai_session", None) if session is not None else None
        if openai_session is not None:
            await openai_session.add_items(list(pending))
        else:
            # No live Session to persist into (e.g. lightweight/test
            # contexts) -- nothing durable to do, just drop the queue
            # rather than let it grow unbounded across turns.
            logger.debug(
                "[%s] no session available, dropping %d pending reminder item(s)",
                processor_name, len(pending),
            )
    except Exception as e:
        logger.debug(f"[{processor_name}] failed to persist reminders: {e}")
