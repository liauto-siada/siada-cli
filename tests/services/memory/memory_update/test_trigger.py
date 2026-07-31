"""Tests for ``PreCompactionTrigger``.

The trigger must:

* delegate to ``CompactionStrategy.should_compact`` (via the unified
  ``get_compaction_strategy`` factory);
* never raise — any underlying error is swallowed and treated as
  "do not trigger";
* be cheap (no I/O, no LLM); we don't assert this explicitly but the
  tests deliberately use synchronous mocks so any accidental I/O
  would surface.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from siada.services.memory.memory_update import trigger as trigger_module
from siada.services.memory.memory_update.trigger import (
    PreCompactionTrigger,
)


def _fake_context(*, model_run_config=None) -> SimpleNamespace:
    """Build a minimal CodeAgentContext-like stand-in for the trigger.

    We only need ``model_run_config`` because that's the single
    attribute the strategy interaction goes through.
    """
    return SimpleNamespace(
        model_run_config=model_run_config or SimpleNamespace(model_name="gpt-4"),
    )


def _patch_strategy(monkeypatch, *, should_compact, raises_on_lookup=False):
    """Replace ``get_compaction_strategy`` with a configurable stub.

    Returns the (mock_strategy, mock_factory) tuple so individual tests
    can inspect call arguments.
    """
    mock_strategy = MagicMock()
    mock_strategy.should_compact = MagicMock(return_value=should_compact)

    def _factory(_context):
        if raises_on_lookup:
            raise RuntimeError("strategy lookup failed")
        return mock_strategy

    # Patch the import *target* — the trigger does
    # ``from siada.agent_hub.context_filter.compaction_strategy import
    # get_compaction_strategy`` inside the method, so we need to swap
    # it on the strategy module itself.
    import siada.agent_hub.context_filter.compaction_strategy as cs_mod
    monkeypatch.setattr(cs_mod, "get_compaction_strategy", _factory)
    return mock_strategy


def test_should_trigger_true(monkeypatch):
    strategy = _patch_strategy(monkeypatch, should_compact=True)
    trig = PreCompactionTrigger()
    ctx = _fake_context()

    assert trig.should_trigger(
        context=ctx, tokens_count=100_000, item_count=42
    ) is True
    # The strategy was consulted with the provided tokens_count.
    strategy.should_compact.assert_called_once_with(
        100_000, ctx.model_run_config
    )


def test_should_trigger_false(monkeypatch):
    _patch_strategy(monkeypatch, should_compact=False)
    trig = PreCompactionTrigger()
    ctx = _fake_context()
    assert trig.should_trigger(
        context=ctx, tokens_count=10, item_count=1
    ) is False


def test_strategy_lookup_failure_swallowed(monkeypatch):
    """``get_compaction_strategy`` raising must not propagate."""
    _patch_strategy(monkeypatch, should_compact=True, raises_on_lookup=True)
    trig = PreCompactionTrigger()

    # Trigger never raises — it logs and returns False.
    assert trig.should_trigger(
        context=_fake_context(), tokens_count=999, item_count=1
    ) is False


def test_should_compact_failure_swallowed(monkeypatch):
    """``strategy.should_compact`` raising is also swallowed."""
    strategy = _patch_strategy(monkeypatch, should_compact=True)
    strategy.should_compact.side_effect = RuntimeError("boom")
    trig = PreCompactionTrigger()
    assert trig.should_trigger(
        context=_fake_context(), tokens_count=5, item_count=1
    ) is False


def test_trigger_module_logger_is_present():
    """Smoke check: the module exports the contract expected by tests."""
    # Failing this would mean future refactors split out the import,
    # which breaks the monkeypatch path in other tests.
    assert hasattr(trigger_module, "PreCompactionTrigger")
    assert hasattr(trigger_module, "MemoryUpdateTrigger")
