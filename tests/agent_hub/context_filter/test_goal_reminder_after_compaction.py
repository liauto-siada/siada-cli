"""Tests for goal-reminder re-injection after compaction.

Covers the gap described in the goal-command design: the once-per-activation
goal reminder (merged into a single turn by
``SiadaRunner._maybe_merge_goal_reminder``) can later be summarized or
pruned away by either compaction strategy, whether compaction was triggered
passively (``ApiMessageTransferFilter``'s per-call threshold check) or
actively (the user-invoked ``/compact`` command). These tests exercise
``ApiMessageTransferFilter._maybe_reinject_goal_reminder`` directly and its
wiring into ``_try_compact_real_api_messages``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from siada.agent_hub.context_filter.api_message_transfer_filter import (
    ApiMessageTransferFilter,
)
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult


def _make_goal(status="active", objective="Ship the feature"):
    goal = MagicMock()
    goal.status = status
    goal.objective = objective
    return goal


def _make_context(goal=None):
    context = MagicMock()
    context.goal = goal
    return context


# ---------------------------------------------------------------------------
# Orphan function-call output repair
# ---------------------------------------------------------------------------

def test_drop_orphan_function_call_output_from_restored_compaction():
    messages = [
        {"role": "user", "content": "continue"},
        {
            "type": "function_call_output",
            "call_id": "summarized_call",
            "output": "stale output",
        },
        {
            "type": "function_call",
            "call_id": "kept_call",
            "name": "run_cmd",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "kept_call",
            "output": "ok",
        },
        {
            "type": "apply_patch_call",
            "call_id": "kept_patch",
            "id": "apc_1",
        },
        {
            "type": "apply_patch_call_output",
            "call_id": "kept_patch",
            "output": "patched",
        },
    ]

    repaired, removed = ApiMessageTransferFilter._drop_orphan_function_call_outputs(
        messages
    )

    assert removed == 1
    assert repaired is not messages
    assert [
        item["call_id"]
        for item in repaired
        if item.get("type") == "function_call_output"
    ] == ["kept_call"]
    assert any(item.get("type") == "apply_patch_call_output" for item in repaired)
    assert messages[1]["call_id"] == "summarized_call"


@pytest.mark.asyncio
async def test_filter_repairs_orphan_output_before_assigning_model_input():
    messages = [
        {"role": "user", "content": "continue"},
        {
            "type": "function_call_output",
            "call_id": "summarized_call",
            "output": "stale output",
        },
        {
            "type": "function_call",
            "call_id": "kept_call",
            "name": "run_cmd",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "kept_call",
            "output": "ok",
        },
    ]
    model_data = MagicMock()
    model_data.input = messages
    model_data.instructions = "instructions"
    context = MagicMock()
    context.auto_compact = True
    context.session_id = "session-test"
    context.task_message_state.set_real_messages = MagicMock()
    filter_ = ApiMessageTransferFilter()

    with patch.object(
        filter_,
        "_build_real_message_state",
        AsyncMock(return_value=(messages, 100, 3, "signature")),
    ), patch(
        "siada.services.memory.memory_update.get_memory_scheduler",
        return_value=None,
    ), patch.object(
        filter_,
        "_try_compact_real_api_messages",
        AsyncMock(side_effect=lambda **kwargs: kwargs["real_api_messages"]),
    ), patch.object(filter_, "_sync_api_message_to_file"):
        await filter_.filter(model_data, MagicMock(tools=None), context)

    assert [
        item["call_id"]
        for item in model_data.input
        if item.get("type") == "function_call_output"
    ] == ["kept_call"]
    context.task_message_state.set_real_messages.assert_called_once()


# ---------------------------------------------------------------------------
# _maybe_reinject_goal_reminder
# ---------------------------------------------------------------------------

def test_no_active_goal_is_a_noop():
    messages = [{"role": "user", "content": "hi"}]
    context = _make_context(goal=None)

    result = ApiMessageTransferFilter._maybe_reinject_goal_reminder(context, messages)

    assert result is messages


def test_inactive_goal_status_is_a_noop():
    messages = [{"role": "user", "content": "hi"}]
    context = _make_context(goal=_make_goal(status="blocked"))

    result = ApiMessageTransferFilter._maybe_reinject_goal_reminder(context, messages)

    assert result is messages


def test_active_goal_appends_reminder_to_trailing_user_message():
    messages = [
        {"role": "user", "content": "<summary>"},
        {"role": "user", "content": "continue please"},
    ]
    context = _make_context(goal=_make_goal())

    result = ApiMessageTransferFilter._maybe_reinject_goal_reminder(context, messages)

    assert result is not messages
    last = result[-1]
    assert last["content"][0] == {"type": "input_text", "text": "continue please"}
    assert "<system-reminder>" in last["content"][1]["text"]
    assert "Ship the feature" in last["content"][1]["text"]


# ---------------------------------------------------------------------------
# _try_compact_real_api_messages wiring (both strategies go through the
# same ApiMessageTransferFilter._try_compact_real_api_messages call site)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_try_compact_reinjects_reminder_when_compaction_occurs():
    real_api_messages = [{"role": "user", "content": "old turn"}]
    compacted = [{"role": "user", "content": "compacted result"}]

    strategy = MagicMock()
    strategy.should_compact.return_value = True
    strategy.compact = AsyncMock(
        return_value=CompactionResult(messages=compacted, compacted=True)
    )

    context = _make_context(goal=_make_goal())
    context.model_run_config = MagicMock()

    filter_ = ApiMessageTransferFilter()
    with patch(
        "siada.agent_hub.context_filter.api_message_transfer_filter.get_compaction_strategy",
        return_value=strategy,
    ), patch(
        "siada.agent_hub.context_filter.api_message_transfer_filter.CompactionStrategy.calculate_fixed_overhead",
        return_value=0,
    ):
        result = await filter_._try_compact_real_api_messages(
            context=context,
            real_api_messages=real_api_messages,
            tokens_count=100,
            model_config=context.model_run_config,
        )

    assert result is not compacted  # reminder-appending returns a new list
    assert "<system-reminder>" in result[-1]["content"][-1]["text"]


@pytest.mark.asyncio
async def test_try_compact_skips_reinjection_when_should_compact_is_false():
    real_api_messages = [{"role": "user", "content": "old turn"}]

    strategy = MagicMock()
    strategy.should_compact.return_value = False

    context = _make_context(goal=_make_goal())
    context.model_run_config = MagicMock()

    filter_ = ApiMessageTransferFilter()
    with patch(
        "siada.agent_hub.context_filter.api_message_transfer_filter.get_compaction_strategy",
        return_value=strategy,
    ):
        result = await filter_._try_compact_real_api_messages(
            context=context,
            real_api_messages=real_api_messages,
            tokens_count=10,
            model_config=context.model_run_config,
        )

    # No compaction happened, so nothing should be reinjected either.
    assert result is real_api_messages
