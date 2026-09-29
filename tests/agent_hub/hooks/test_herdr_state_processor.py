"""Tests for the Herdr turn-state processor.

The processor is what turns an agent run into a `working` / `idle` report for
a hosting Herdr pane. It must read the session id off the run context without
assuming a session exists, and it must be part of the default agent hook chain
so both runtime paths are covered by one registration.
"""

from types import SimpleNamespace

import pytest

from siada.agent_hub.hooks.processors import herdr_state_processor
from siada.agent_hub.hooks.processors.herdr_state_processor import (
    HerdrStateProcessor,
)
from siada.foundation import herdr_reporter


class _RecordingReporter:
    def __init__(self):
        self.reports = []

    def report_state(self, state, message=None, session_id=None):
        self.reports.append((state, message, session_id))


@pytest.fixture
def fake_reporter(monkeypatch):
    """Capture reports without touching the real herdr CLI dispatch."""
    reporter = _RecordingReporter()
    monkeypatch.setattr(
        herdr_state_processor.herdr_reporter, "report_state", reporter.report_state
    )
    return reporter


def _wrapper(session_id):
    context = SimpleNamespace(session_id=session_id) if session_id else None
    return SimpleNamespace(context=context)


@pytest.mark.asyncio
async def test_agent_start_reports_working(fake_reporter):
    processor = HerdrStateProcessor()

    await processor.on_agent_start(_wrapper("sess-1"), agent=None)

    assert fake_reporter.reports == [
        (herdr_reporter.STATE_WORKING, None, "sess-1")
    ]


@pytest.mark.asyncio
async def test_agent_end_reports_idle(fake_reporter):
    processor = HerdrStateProcessor()

    await processor.on_agent_end(_wrapper("sess-1"), agent=None, output=None)

    assert fake_reporter.reports == [(herdr_reporter.STATE_IDLE, None, "sess-1")]


@pytest.mark.asyncio
async def test_missing_session_is_reported_without_an_id(fake_reporter):
    processor = HerdrStateProcessor()

    await processor.on_agent_start(_wrapper(None), agent=None)

    assert fake_reporter.reports == [(herdr_reporter.STATE_WORKING, None, None)]


@pytest.mark.asyncio
async def test_llm_and_tool_hooks_stay_silent(fake_reporter):
    processor = HerdrStateProcessor()

    await processor.on_llm_start(_wrapper("sess-1"), agent=None, system_prompt=None, input_items=[])
    await processor.on_llm_end(_wrapper("sess-1"), agent=None, response=None)
    await processor.on_tool_start(_wrapper("sess-1"), agent=None, tool=None)
    await processor.on_tool_end(_wrapper("sess-1"), agent=None, tool=None, result="")

    assert fake_reporter.reports == []


def test_processor_is_registered_in_default_agent_hooks():
    from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks

    hooks = SiadaAgentHooks()

    assert any(isinstance(p, HerdrStateProcessor) for p in hooks.processors)


def test_basic_hooks_stay_untouched_for_subagents():
    """Sub-agent runs must not flip the pane to idle while the parent works."""
    from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks

    hooks = SiadaBasicAgentHooks()

    assert not any(isinstance(p, HerdrStateProcessor) for p in hooks.processors)
