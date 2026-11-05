"""Pure request processing for the default effective-context run.

The SDK bridge selects and commits the versioned input. This filter never
captures TaskMessageState or writes a legacy snapshot.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from siada.foundation.logging import logger
from .api_message_transfer_filter import ApiMessageTransferFilter
from .compaction_strategy import CompactionError
from .malformed_tool_call_filter import MalformedToolCallFilter
from .tool_output_offload import ToolOutputOffloadFilter
from .request_token_estimator import estimate_request_tokens
from .compaction_threshold import get_compaction_token_threshold, get_compaction_threshold_rule

if TYPE_CHECKING:
    from agents.run import CallModelData, ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


async def effective_context_filter(data: CallModelData[CodeAgentContext]) -> ModelInputData:
    """Repair and compact authoritative input without falling back to SDK history."""
    model_data = data.model_data
    context = data.context
    transfer = ApiMessageTransferFilter()
    try:
        transfer._resolve_effective_context_window(context)
    except Exception as error:
        logger.warning(
            "[CTX-COMPACT][window] session=%s status=resolve_failed error_type=%s context_window=%s",
            context.session_id, type(error).__name__, context.model_run_config.context_window,
        )
    for processor in (ToolOutputOffloadFilter(), MalformedToolCallFilter()):
        await processor.filter(model_data, data.agent, context)
    model_data.input, _ = transfer._drop_orphan_function_call_outputs(model_data.input)
    if not context.auto_compact:
        logger.info(
            "[CTX-COMPACT][decision] session=%s action=skip reason=auto_compact_disabled "
            "request=%s model=%s context_window=%s threshold_rule=%s threshold=%d remaining=unavailable",
            context.session_id, getattr(getattr(context, "runtime_session", None), "request_identity", None),
            context.model_run_config.model_name, context.model_run_config.context_window,
            get_compaction_threshold_rule(context.model_run_config.context_window),
            get_compaction_token_threshold(context.model_run_config.context_window),
        )
        return model_data

    tools = getattr(data.agent, "tools", None)
    budget_diagnostics = {}
    tokens_count = estimate_request_tokens(
        context, data.agent, model_data.input, model_data.instructions, diagnostics=budget_diagnostics,
    )
    record_budget = getattr(getattr(context, "runtime_session", None), "record_request_budget", None)
    if callable(record_budget):
        record_budget(
            tokens_count, budget_diagnostics["token_mode"], budget_diagnostics["protocol"],
            model_data.input, model_data.instructions,
        )
    # Background memory work owns a detached pre-compaction snapshot, never a
    # handle that could later read the compacted current session file.
    try:
        from siada.services.memory.memory_update import get_memory_scheduler

        scheduler = get_memory_scheduler(context.session_id)
        if scheduler is not None:
            await scheduler.run(
                context=context, tokens_count=tokens_count,
                real_api_messages=copy.deepcopy(model_data.input),
            )
    except Exception as error:
        logger.warning("Pre-compaction memory update failed: %s", error)

    original = model_data.input
    try:
        compacted = await transfer._try_compact_real_api_messages(
            context=context, real_api_messages=copy.deepcopy(original),
            tokens_count=tokens_count, model_config=context.model_run_config,
            instructions=model_data.instructions, tools=tools,
        )
    except CompactionError as error:
        logger.warning(
            "[CTX-COMPACT][filter] session=%s action=retain_authoritative_context error_type=%s",
            context.session_id, type(error).__name__,
        )
        return model_data
    model_data.input = compacted
    if compacted != original:
        logger.info(
            "[CTX-COMPACT][filter] session=%s stage=prepared before_items=%d after_items=%d",
            context.session_id, len(original), len(compacted),
        )
        if context.memory_store is not None:
            try:
                context.memory_store.load_from_disk()
            except Exception as error:
                logger.warning("Memory snapshot refresh failed: %s", error)
        try:
            from siada.services.memory.combined_memory import build_combined_memory

            context.combined_memory = build_combined_memory(
                context.root_dir, context.memory_store, context.holographic_provider,
            )
        except Exception as error:
            logger.warning("Combined memory refresh failed: %s", error)
    return model_data
