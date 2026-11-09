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
    from siada.provider.token_counting import token_counting_info_from_model

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
    monkeypatch.setattr(shared, "token_counting_info_from_config", lambda config, **kwargs: token_counting_info_from_model(kwargs["model_name"]))
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


@pytest.mark.parametrize("context_window, threshold", [
    (32_000, 0), (60_000, 0), (64_000, 4_000), (128_000, 68_000),
    (200_000, 140_000), (499_999, 439_999), (500_000, 440_000),
    (500_001, 375_001), (600_000, 450_000), (1_000_000, 750_000),
])
@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("strategy_name", ["header_summary", "turn_prune_summary"])
def test_compaction_triggers_at_tiered_threshold(context_window, threshold, offset, strategy_name):
    from siada.agent_hub.context_filter.compaction_strategy import _resolve_strategy_by_name
    from siada.agent_hub.context_filter.compaction_threshold import get_compaction_token_threshold

    strategy = _resolve_strategy_by_name(strategy_name)
    config = SimpleNamespace(context_window=context_window)
    assert get_compaction_token_threshold(context_window) == threshold
    assert strategy.should_compact(
        threshold + offset, config,
    ) is (offset >= 0)


@pytest.mark.parametrize("context_window", [32_000, 60_000])
def test_small_context_windows_already_meet_headroom_trigger(context_window):
    assert _NoopStrategy().should_compact(0, SimpleNamespace(context_window=context_window))


def test_compaction_uses_updated_effective_context_window():
    strategy = _NoopStrategy()
    config = SimpleNamespace(context_window=200_000)
    assert strategy.should_compact(140_000, config)
    config.context_window = 1_000_000
    assert not strategy.should_compact(140_000, config)


def test_openrouter_gemini_compaction_uses_chat_route_for_history_and_tools(monkeypatch):
    from unittest.mock import Mock
    import litellm
    from agents import function_tool
    from siada.agent_hub.context_filter import utils
    from siada.provider import provider_factory
    from siada.provider.default.default_provider import DefaultProvider
    from siada.provider.gemini import counting

    @function_tool
    def lookup(value: int) -> str:
        return str(value)

    monkeypatch.setenv("BASE_URL", "https://openrouter.ai/api/v1")
    provider = DefaultProvider()
    describe = Mock(wraps=provider.get_token_counting_info)
    monkeypatch.setattr(provider, "get_token_counting_info", describe)
    monkeypatch.setattr(provider_factory, "get_provider", lambda name: provider)
    native_counter = Mock(side_effect=AssertionError("Chat must not use native Gemini counting"))
    counter = Mock(return_value=100)
    tool_counter = Mock(side_effect=[140, 100])
    monkeypatch.setattr(utils, "_calculate_tokens", counter)
    monkeypatch.setattr(counting, "estimate_input_tokens", native_counter)
    monkeypatch.setattr(litellm, "token_counter", tool_counter)
    config = SimpleNamespace(model_name="google/gemini-3.5-flash", provider="default")
    context = SimpleNamespace(model_run_config=config)
    items = [{"role": "user", "content": "synthetic"}]
    assert _NoopStrategy()._count_tokens(items, config) == 110
    assert CompactionStrategy.calculate_fixed_overhead(context, "instructions", [lookup]) == 150
    assert all(call.args[0] == "openrouter/google/gemini-3.5-flash" for call in counter.call_args_list)
    assert all(call.kwargs["model"] == "openrouter/google/gemini-3.5-flash" for call in tool_counter.call_args_list)
    assert describe.call_count == 2
    native_counter.assert_not_called()
    assert provider._gemini_transport is None


@pytest.mark.parametrize("protocol", ["chat", "gemini"])
@pytest.mark.parametrize("current_tokens", [0, 200])
def test_legacy_context_refresh_uses_runtime_protocol(monkeypatch, protocol, current_tokens):
    from unittest.mock import Mock
    from siada.agent_hub.context_filter import utils
    from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter
    from siada.provider.gemini import counting
    from siada.provider.token_counting import TokenCountingInfo

    counter = Mock(return_value=100)
    native_counter = Mock(return_value=200)
    monkeypatch.setattr(utils, "_calculate_tokens", counter)
    monkeypatch.setattr(counting, "estimate_input_tokens", native_counter)
    info = TokenCountingInfo("opaque-wire-alias", protocol)
    context = SimpleNamespace(
        model_run_config=SimpleNamespace(model_name="google/gemini-3.5-flash"),
        runtime_session=SimpleNamespace(token_counting_info=info),
    )
    previous = {"role": "user", "content": "previous"}
    delta = {"role": "user", "content": "delta"}
    items = [previous, delta]
    budget = 220 if protocol == "gemini" else 110
    assert CompactionStrategy.calculate_fixed_overhead(context, "instructions") == budget
    transfer = ApiMessageTransferFilter()
    refreshed, tokens = transfer._do_full_refresh(context, "instructions", items, 0)
    assert refreshed == items and tokens == budget * 2
    updated, tokens = transfer._try_incremental_update(
        context, "instructions", items, [previous], 0,
        utils.compute_message_signature(previous), current_tokens,
    )
    assert updated == items
    assert tokens == (current_tokens + budget if current_tokens else budget * 2)
    if protocol == "gemini":
        counter.assert_not_called()
    else:
        native_counter.assert_not_called()
        assert all(call.args[0] == info.model_name for call in counter.call_args_list)


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
