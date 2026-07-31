"""Tests for the `CompactionStrategy.compact()` template method.

`compact()` hands `_compact_impl()` a private shallow copy of the input
list and normalizes the result into a `CompactionResult`, whose
`compacted` flag is the single source of truth for "did anything change?"
(not a list-identity comparison):
  - `compacted=False` -> `result.messages` is the caller's original
    `real_api_messages` object, untouched, regardless of what the
    subclass's `_compact_impl()` returned.
  - `compacted=True`  -> `result.messages` is whatever new list the
    subclass produced.

This guarantee is enforced once, in the base class, so every concrete
strategy (and every caller) gets it for free -- even a strategy that
mutates its input in place instead of returning a new list can't corrupt
the caller's original reference or be mistaken for "no-op" incorrectly.
"""
from __future__ import annotations

import pytest

from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionResult,
    CompactionStrategy,
)


class _InPlaceMutatingNoopStrategy(CompactionStrategy):
    """Simulates a (buggy) strategy that mutates its input in place,
    returns the very same object, but correctly reports `compacted=False`."""

    token_threshold_ratio = 0.8
    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        real_api_messages.append({"role": "user", "content": "injected"})
        return CompactionResult(messages=real_api_messages, compacted=False)


class _NoopStrategy(CompactionStrategy):
    """Simulates a strategy that decides there's nothing to compact and
    returns the exact object it was handed, with `compacted=False`."""

    token_threshold_ratio = 0.8
    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        return CompactionResult(messages=real_api_messages, compacted=False)


class _RealChangeStrategy(CompactionStrategy):
    """Simulates a well-behaved strategy that returns a brand-new list
    with `compacted=True`."""

    token_threshold_ratio = 0.8
    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        return CompactionResult(
            messages=[{"role": "user", "content": "summary"}],
            summary="summary",
            compacted=True,
        )


@pytest.mark.asyncio
async def test_inplace_mutating_noop_does_not_corrupt_callers_original_list():
    real_api_messages = [{"role": "user", "content": "old turn"}]

    strategy = _InPlaceMutatingNoopStrategy()
    result = await strategy.compact(model_run_config=object(), real_api_messages=real_api_messages)

    # The caller's original list must remain untouched, no matter what the
    # (misbehaving) strategy did to the private copy it was handed.
    assert real_api_messages == [{"role": "user", "content": "old turn"}]
    assert result.compacted is False
    assert result.messages is real_api_messages


@pytest.mark.asyncio
async def test_noop_strategy_reports_compacted_false_and_original_object():
    real_api_messages = [{"role": "user", "content": "old turn"}]

    strategy = _NoopStrategy()
    result = await strategy.compact(model_run_config=object(), real_api_messages=real_api_messages)

    assert result.compacted is False
    # Even though the strategy returned the private copy it was handed
    # (not the true `real_api_messages` object), the caller must see the
    # true original reference on the no-op path.
    assert result.messages is real_api_messages


@pytest.mark.asyncio
async def test_real_change_strategy_reports_compacted_true_and_new_list():
    real_api_messages = [{"role": "user", "content": "old turn"}]

    strategy = _RealChangeStrategy()
    result = await strategy.compact(model_run_config=object(), real_api_messages=real_api_messages)

    assert result.compacted is True
    assert result.messages == [{"role": "user", "content": "summary"}]
    assert result.messages is not real_api_messages
    # Original untouched.
    assert real_api_messages == [{"role": "user", "content": "old turn"}]
