"""Pure request processing for the default effective-context run.

The SDK bridge selects and commits the versioned input. This filter never
captures TaskMessageState or writes a legacy snapshot.

Only repair helpers that exist in this distribution run here: orphan
tool-output removal plus compaction (``_repair_tool_pairs`` inside the
compaction strategy). Provider-specific history repair filters are not part
of this distribution and are deliberately absent from the chain.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from siada.foundation.logging import logger
from .api_message_transfer_filter import ApiMessageTransferFilter
from .compaction_strategy import CompactionError
from .utils import calculate_tokens

if TYPE_CHECKING:
    from agents.run import CallModelData, ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


async def effective_context_filter(data: CallModelData[CodeAgentContext]) -> ModelInputData:
    """Repair and compact authoritative input without falling back to SDK history."""
    model_data = data.model_data
    context = data.context
    transfer = ApiMessageTransferFilter()
    # The dynamic per-request window resolver is not part of this distribution;
    # its absence changes nothing else about the filter chain.
    resolve_window = getattr(transfer, "_resolve_effective_context_window", None)
    if resolve_window is not None:
        try:
            resolve_window(context)
        except Exception as error:
            logger.debug("Effective context window resolution failed: %s", error)
    model_data.input, _ = transfer._drop_orphan_function_call_outputs(model_data.input)
    if not context.auto_compact:
        return model_data

    tools = getattr(data.agent, "tools", None)
    model_name = context.model_run_config.model_name
    tokens_count = calculate_tokens(model_name, model_data.input, tools=tools)
    tokens_count += calculate_tokens(model_name, model_data.instructions or "")
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
        logger.warning("Compaction failed, retaining authoritative context: %s", error)
        return model_data
    model_data.input = compacted
    if compacted != original:
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
