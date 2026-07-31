"""Tests for ReminderPersistenceProcessor.on_llm_end.

This processor is the durable-persistence half of the reminder pipeline:
TodoReminderFilter injects a reminder into a single LLM call's
model_data.input copy (ephemeral, immediate effect) AND stages a copy in
context.pending_reminder_items; this processor drains that queue into the
real Session right after the LLM call succeeds, mirroring how the SDK
itself persists real conversation turns via session.add_items().
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.hooks.processors.reminder_persistence_processor import (
    ReminderPersistenceProcessor,
)


def _make_wrapper(context: CodeAgentContext):
    """Mimic RunContextWrapper[CodeAgentContext]'s `.context` attribute."""
    return SimpleNamespace(context=context)


def _make_context_with_session():
    context = CodeAgentContext()
    openai_session = SimpleNamespace(add_items=AsyncMock())
    context.session = SimpleNamespace(state=SimpleNamespace(openai_session=openai_session))
    return context, openai_session


@pytest.mark.asyncio
async def test_no_pending_items_is_a_noop():
    processor = ReminderPersistenceProcessor()
    context, openai_session = _make_context_with_session()
    await processor.on_llm_end(_make_wrapper(context), agent=None, response=None)
    openai_session.add_items.assert_not_called()


@pytest.mark.asyncio
async def test_persists_pending_items_to_session_and_clears_queue():
    processor = ReminderPersistenceProcessor()
    context, openai_session = _make_context_with_session()
    reminder_item = {"role": "user", "content": "hidden reminder text"}
    context.pending_reminder_items.append(reminder_item)

    await processor.on_llm_end(_make_wrapper(context), agent=None, response=None)

    openai_session.add_items.assert_awaited_once_with([reminder_item])
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
async def test_multiple_pending_items_persisted_together():
    processor = ReminderPersistenceProcessor()
    context, openai_session = _make_context_with_session()
    item_a = {"role": "user", "content": "reminder a"}
    item_b = {"role": "user", "content": "reminder b"}
    context.pending_reminder_items.extend([item_a, item_b])

    await processor.on_llm_end(_make_wrapper(context), agent=None, response=None)

    openai_session.add_items.assert_awaited_once_with([item_a, item_b])
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
async def test_no_session_available_clears_queue_without_error():
    processor = ReminderPersistenceProcessor()
    context = CodeAgentContext()
    context.session = None
    context.pending_reminder_items.append({"role": "user", "content": "reminder"})

    # Must not raise even though there's nowhere durable to persist.
    await processor.on_llm_end(_make_wrapper(context), agent=None, response=None)

    assert context.pending_reminder_items == []


@pytest.mark.asyncio
async def test_add_items_exception_does_not_propagate_and_still_clears_queue():
    processor = ReminderPersistenceProcessor()
    context, openai_session = _make_context_with_session()
    openai_session.add_items.side_effect = RuntimeError("disk full")
    context.pending_reminder_items.append({"role": "user", "content": "reminder"})

    # Must fail safe -- a persistence error must never break the turn.
    await processor.on_llm_end(_make_wrapper(context), agent=None, response=None)

    assert context.pending_reminder_items == []
