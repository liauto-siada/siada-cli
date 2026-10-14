"""Background memory review must leave pane state owned by the main agent."""

import asyncio
from types import SimpleNamespace

import pytest
from agents import Model, ModelResponse, RunConfig, Runner, Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from siada.agent_hub.hooks.processors.herdr_state_processor import HerdrStateProcessor
from siada.foundation import herdr_reporter
from siada.services.memory.memory_review_agent import _build_memory_review_agent
from siada.services.memory.memory_update.scheduler import MemoryUpdateScheduler


class _ReviewModel(Model):
    def __init__(self, fail: bool):
        self.fail = fail

    async def get_response(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("Synthetic review failure")
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="synthetic-message",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[
                        ResponseOutputText(
                            type="output_text", text="Nothing to save.", annotations=[]
                        )
                    ],
                )
            ],
            usage=Usage(),
            response_id="synthetic-response",
        )

    async def stream_response(self, *args, **kwargs):
        raise AssertionError("The background reviewer uses non-streamed runs")
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("with_fact_store", [False, True])
@pytest.mark.parametrize("review_fails", [False, True])
async def test_background_review_preserves_main_pane_state(
    monkeypatch, with_fact_store, review_fails
):
    reports = []
    monkeypatch.setattr(
        herdr_reporter,
        "report_state",
        lambda state, **kwargs: reports.append((state, kwargs.get("session_id"))),
    )
    main = HerdrStateProcessor()
    main_context = SimpleNamespace(context=SimpleNamespace(session_id="main-session"))
    await main.on_agent_start(main_context, agent=None)

    reviewer = _build_memory_review_agent(
        "# Synthetic memory review", with_fact_store=with_fact_store
    )
    reviewer.model = _ReviewModel(review_fails)
    review_context = SimpleNamespace(session_id=None, session=None)
    review_finished = asyncio.Event()
    review_errors = []

    class Updater:
        async def sync_stage(self, **kwargs):
            pass

        async def async_stage(self, **kwargs):
            try:
                await Runner.run(
                    reviewer,
                    "Review synthetic history",
                    context=review_context,
                    run_config=RunConfig(tracing_disabled=True),
                )
            except Exception as error:
                review_errors.append(str(error))
                raise
            finally:
                review_finished.set()

    scheduler = MemoryUpdateScheduler(
        SimpleNamespace(should_trigger=lambda **kwargs: True), Updater()
    )
    try:
        await scheduler.run(
            context=SimpleNamespace(session_id="main-session"),
            tokens_count=1,
            real_api_messages=[{"role": "user", "content": "Synthetic history"}],
        )
        # The main task is still awaiting compaction while review completes.
        await asyncio.wait_for(review_finished.wait(), timeout=5)
        await scheduler.shutdown()
        assert review_errors == (
            ["Synthetic review failure"] if review_fails else []
        )
        assert reports == [(herdr_reporter.STATE_WORKING, "main-session")]

        await main.on_agent_end(main_context, agent=None, output=None)
        assert reports == [
            (herdr_reporter.STATE_WORKING, "main-session"),
            (herdr_reporter.STATE_IDLE, "main-session"),
        ]
    finally:
        await scheduler.shutdown()