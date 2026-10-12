"""Verify that compaction notices bracket the work and finish before model input."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.agent_hub.context_filter.api_message_transfer_filter import (
    ApiMessageTransferFilter,
)
from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionError,
    CompactionResult,
)


@pytest.fixture
def compaction_setup(monkeypatch):
    notices = []
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "continue"},
    ]
    context = SimpleNamespace(
        session=SimpleNamespace(siada_config=SimpleNamespace(
            io=Mock(print_info=Mock(side_effect=notices.append)),
        )),
        model_run_config=object(),
        auto_compact=True,
        session_id="test-session",
        task_message_state=Mock(),
        goal=None,
        is_subagent=True,
        memory_store=None,
    )
    strategy = Mock()
    strategy.should_compact.return_value = True
    monkeypatch.setattr(
        "siada.agent_hub.context_filter.api_message_transfer_filter.get_compaction_strategy",
        lambda _: strategy,
    )
    monkeypatch.setattr(
        "siada.agent_hub.context_filter.api_message_transfer_filter.CompactionStrategy.calculate_fixed_overhead",
        lambda *args, **kwargs: 0,
    )
    return context, strategy, messages, notices


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [True, False])
async def test_notifications_surround_compaction_and_precede_model_input(
    compaction_setup, monkeypatch, changed,
):
    context, strategy, messages, notices = compaction_setup
    compacted = [{"role": "user", "content": "summary"}] if changed else messages

    async def compact(**kwargs):
        assert notices == ["Compacting context..."]
        return CompactionResult(messages=compacted, compacted=changed)

    strategy.compact = AsyncMock(side_effect=compact)
    filter_ = ApiMessageTransferFilter()
    monkeypatch.setattr(
        filter_, "_build_real_message_state",
        AsyncMock(return_value=(messages, 100, 2, "signature")),
    )
    monkeypatch.setattr(filter_, "_sync_api_message_to_file", Mock())
    monkeypatch.setattr(
        "siada.services.memory.memory_update.get_memory_scheduler", lambda _: None,
    )
    monkeypatch.setattr(
        "siada.services.memory.combined_memory.build_combined_memory",
        lambda *args: "",
    )
    model_data = SimpleNamespace(input=messages, instructions="test instructions")

    await filter_.filter(model_data, SimpleNamespace(tools=None), context)

    assert model_data.input is compacted
    assert notices == [
        "Compacting context...",
        "Compacted: 3 → 1 messages (2 removed)" if changed
        else "Nothing to compact (conversation too short or already compact).",
    ]


@pytest.mark.asyncio
async def test_skipped_compaction_sends_no_notices(compaction_setup):
    context, strategy, messages, notices = compaction_setup
    strategy.should_compact.return_value = False

    result = await ApiMessageTransferFilter()._try_compact_real_api_messages(
        context, messages, 10, context.model_run_config,
    )

    assert result is messages
    assert notices == []
    strategy.compact.assert_not_called()


@pytest.mark.asyncio
async def test_completion_counts_include_restored_reminders(compaction_setup, monkeypatch):
    context, strategy, messages, notices = compaction_setup
    compacted = [{"role": "user", "content": "summary"}]
    restored = [*compacted, {"role": "user", "content": "goal reminder"}]
    strategy.compact = AsyncMock(
        return_value=CompactionResult(messages=compacted, compacted=True),
    )
    filter_ = ApiMessageTransferFilter()
    monkeypatch.setattr(filter_, "_maybe_reinject_goal_reminder", lambda *args: restored)

    result = await filter_._try_compact_real_api_messages(
        context, messages, 100, context.model_run_config,
    )

    assert result is restored
    assert notices == ["Compacting context...", "Compacted: 3 → 2 messages (1 removed)"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_error", "end_notice"),
    [
        (RuntimeError("synthetic failure"), CompactionError, "Compaction failed: synthetic failure"),
        (asyncio.CancelledError(), asyncio.CancelledError, "Compaction interrupted."),
    ],
)
async def test_failed_or_cancelled_compaction_ends_its_notice(
    compaction_setup, error, expected_error, end_notice,
):
    context, strategy, messages, notices = compaction_setup
    strategy.compact = AsyncMock(side_effect=error)

    with pytest.raises(expected_error):
        await ApiMessageTransferFilter()._try_compact_real_api_messages(
            context, messages, 100, context.model_run_config,
        )

    assert notices == ["Compacting context...", end_notice]
    assert len(messages) == 3


@pytest.mark.asyncio
async def test_unavailable_notice_output_does_not_fail_compaction(compaction_setup):
    context, strategy, messages, _ = compaction_setup
    context.session.siada_config.io.print_info.side_effect = RuntimeError("output unavailable")
    compacted = [{"role": "user", "content": "summary"}]
    strategy.compact = AsyncMock(
        return_value=CompactionResult(messages=compacted, compacted=True),
    )

    result = await ApiMessageTransferFilter()._try_compact_real_api_messages(
        context, messages, 100, context.model_run_config,
    )

    assert result is compacted