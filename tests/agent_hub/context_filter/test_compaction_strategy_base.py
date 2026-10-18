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

from types import SimpleNamespace

import pytest

from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionResult,
    CompactionStrategy,
)


class _InPlaceMutatingNoopStrategy(CompactionStrategy):
    """Simulates a (buggy) strategy that mutates its input in place,
    returns the very same object, but correctly reports `compacted=False`."""

    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        real_api_messages.append({"role": "user", "content": "injected"})
        return CompactionResult(messages=real_api_messages, compacted=False)


class _NoopStrategy(CompactionStrategy):
    """Simulates a strategy that decides there's nothing to compact and
    returns the exact object it was handed, with `compacted=False`."""

    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        return CompactionResult(messages=real_api_messages, compacted=False)


class _RealChangeStrategy(CompactionStrategy):
    """Simulates a well-behaved strategy that returns a brand-new list
    with `compacted=True`."""

    preserve_ratio = 0.6
    summary_budget_ratio = 0.3

    async def _compact_impl(self, model_run_config, real_api_messages, *, fixed_overhead_tokens=0):
        return CompactionResult(
            messages=[{"role": "user", "content": "summary"}],
            summary="summary",
            compacted=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["glm-5.1", "kimi-k3", "kivy-qwen-3.8-max", "deepseek-v4-pro"])
async def test_summary_request_counts_native_reasoning_with_selected_model(monkeypatch, model):
    from unittest.mock import AsyncMock, Mock
    from agents import ModelResponse
    from agents.usage import Usage
    from siada.agent_hub.context_filter import compaction_strategy as shared

    config = SimpleNamespace(model_name="gpt-4o", provider="synthetic")
    monkeypatch.setenv("SIADA_COMPACT_MODEL", model)
    items = [
        {"role": "user", "content": "synthetic task"},
        {"type": "reasoning", "id": "reasoning-synthetic", "summary": [
            {"type": "summary_text", "text": "synthetic thought"},
        ], "provider_data": {"model": model}},
        {"type": "message", "id": "msg-synthetic", "role": "assistant",
         "content": [{"type": "output_text", "text": "synthetic answer"}]},
    ]
    counter = Mock(return_value=100)
    completion = AsyncMock(return_value=ModelResponse(output=[], usage=Usage(), response_id="synthetic-summary"))
    monkeypatch.setattr(shared, "calculate_tokens", counter)
    monkeypatch.setattr(shared, "one_shot_completion", completion)
    strategy = _NoopStrategy()
    system_prompt = Mock(return_value="# Synthetic system")
    user_prompt = Mock(return_value="Synthetic summary request")
    monkeypatch.setattr(strategy, "_get_compaction_system_prompt", system_prompt)
    monkeypatch.setattr(strategy, "_get_compaction_user_prompt", user_prompt)
    assert await strategy.call_llm_to_compact(config, items) is None
    system_prompt.assert_called_once_with()
    user_prompt.assert_called_once_with()
    count_model, counted_items = counter.call_args.args
    assert count_model == model
    assert counted_items[1:-1] == items
    assert completion.call_args.args[0][:-1] == items
    assert completion.call_args.kwargs["model"] == model
    assert completion.call_args.kwargs["system_instructions"] == counted_items[0]["content"]
    assert completion.call_args.args[0] == counted_items[1:]


@pytest.mark.parametrize("context_window", [64_000, 128_000, 200_000, 1_000_000])
@pytest.mark.parametrize("remaining_tokens", [60_001, 60_000, 59_999, 0, -1])
@pytest.mark.parametrize("strategy_name", ["header_summary", "turn_prune_summary"])
def test_compaction_triggers_at_60k_remaining(context_window, remaining_tokens, strategy_name):
    from siada.agent_hub.context_filter.compaction_strategy import _resolve_strategy_by_name

    strategy = _resolve_strategy_by_name(strategy_name)
    config = SimpleNamespace(context_window=context_window)
    assert strategy.should_compact(
        context_window - remaining_tokens, config,
    ) is (remaining_tokens <= 60_000)


@pytest.mark.parametrize("context_window", [32_000, 60_000])
def test_small_context_windows_already_meet_headroom_trigger(context_window):
    assert _NoopStrategy().should_compact(0, SimpleNamespace(context_window=context_window))


def test_compaction_uses_updated_effective_context_window():
    strategy = _NoopStrategy()
    config = SimpleNamespace(context_window=200_000)
    assert strategy.should_compact(140_000, config)
    config.context_window = 1_000_000
    assert not strategy.should_compact(140_000, config)


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
