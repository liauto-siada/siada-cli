"""Offline accounting regression tests, including real SDK streamed runs."""

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from agents import RunConfig
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    Response, ResponseCompletedEvent,
    ResponseOutputMessage, ResponseOutputText, ResponseReasoningItem,
)

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models import model_pricing
from siada.tools.agent import subagent_persistence
from siada.tools.agent.sub_agent_usage import SubAgentUsageHooks
from siada.utils import DirectoryUtils


subtask = importlib.import_module("siada.tools.agent.run_subtask")


@pytest.fixture(autouse=True)
def isolated_pricing(monkeypatch):
    monkeypatch.setattr(model_pricing, "_get_user_defined_pricing", lambda _: None)


@pytest.mark.asyncio
async def test_request_cost_cache_counts_and_monotonic_duration(monkeypatch):
    entries = []
    clock = iter([100.0, 101.0, 103.5, 110.0])
    monkeypatch.setattr("siada.tools.agent.sub_agent_usage.time.perf_counter", lambda: next(clock))
    hook = SubAgentUsageHooks("gpt-5.2", lambda kind, text: entries.append((kind, text)))
    await hook.on_llm_start(None, None, None, [])
    await hook.on_llm_end(None, None, SimpleNamespace(usage=Usage(
        input_tokens=1000, output_tokens=100, total_tokens=1650,
        input_tokens_details={"cached_tokens": 500, "cache_write_tokens": 0},
    )))
    hook.finish("completed")
    assert "Duration: 2.500s" in entries[0][1]
    assert "CacheRead=500, CacheWrite=50, Total=1650" in entries[0][1]
    assert "Cost: CNY 0.0227" in entries[0][1]
    assert "Duration: 10.000s" in entries[1][1]
    assert "Model Request Duration: 2.500s" in entries[1][1]
    assert "Known Cost: CNY 0.0227" in entries[1][1]


@pytest.mark.asyncio
async def test_explicit_cache_writes_and_sdk_retry_count():
    entries = []
    hook = SubAgentUsageHooks("claude-sonnet-4-6", lambda kind, text: entries.append(text))
    await hook.on_llm_start(None, None, None, [])
    # Some providers omit cache writes from total_tokens, and SDK retries
    # can aggregate multiple requests into a single completed response.
    usage = SimpleNamespace(
        requests=3, input_tokens=1000, output_tokens=100, total_tokens=1600,
        input_tokens_details=SimpleNamespace(cached_tokens=500, cache_write_tokens=200),
    )
    await hook.on_llm_end(None, None, SimpleNamespace(usage=usage))
    hook.finish("completed")
    assert "CacheWrite=200" in entries[0]
    assert "Cost: CNY 0.0379" in entries[0]
    assert "SDK Reported Requests: 3" in entries[0]
    assert "Requests: 1\nSDK Reported Requests: 3" in entries[1]
    assert "Known Cost: CNY 0.0379" in entries[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("usage", [None, Usage(input_tokens=123, total_tokens=123)])
async def test_unknown_cost_is_not_reported_as_free(usage):
    entries = []
    hook = SubAgentUsageHooks("synthetic-unknown", lambda kind, text: entries.append(text))
    await hook.on_llm_start(None, None, None, [])
    await hook.on_llm_end(None, None, SimpleNamespace(usage=usage))
    hook.finish("completed")
    assert "Cost: unavailable" in entries[0]
    assert "Requests with unknown cost: 1" in entries[1]


def test_interrupted_request_has_duration_without_invented_tokens():
    entries = []
    hook = SubAgentUsageHooks("gpt-5.2", lambda kind, text: entries.append(text))
    hook.request_count = 1
    hook.pending_start = hook.started_at
    hook.finish("failed")
    assert "Status: failed" in entries[0]
    assert "Duration:" in entries[0]
    assert "Tokens: unavailable" in entries[0]
    assert "Requests with unknown cost: 1" in entries[1]


@pytest.mark.asyncio
async def test_log_write_failure_does_not_break_completion():
    def fail_append(kind, text):
        raise OSError("synthetic disk full")
    hook = SubAgentUsageHooks("gpt-5.2", fail_append)
    await hook.on_llm_start(None, None, None, [])
    await hook.on_llm_end(None, None, SimpleNamespace(usage=Usage(input_tokens=100, total_tokens=100)))
    hook.finish("completed")
    assert hook.pending_start is None
    assert hook.tokens["input"] == 100


class SyntheticModel(Model):
    model = "gpt-5.2"

    def __init__(self, *, fail=False, reasoning=False):
        self.calls = 0
        self.fail = fail
        self.reasoning = reasoning

    async def get_response(self, *args, **kwargs):
        raise AssertionError("Streamed path required")

    async def stream_response(self, *args, **kwargs):
        await asyncio.sleep(0)
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic failure")
        output = (
            [ResponseReasoningItem(id="reasoning", type="reasoning", summary=[])]
            if self.reasoning and self.calls == 1 else
            [ResponseOutputMessage(
                id=f"message-{self.calls}", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="usage verified", annotations=[])],
            )]
        )
        yield ResponseCompletedEvent(
            type="response.completed", sequence_number=0,
            response=Response(
                id=f"response-{self.calls}", created_at=0, model=self.model,
                object="response", output=output, parallel_tool_calls=False,
                tool_choice="auto", tools=[],
                usage={
                    "input_tokens": 1000, "output_tokens": 100, "total_tokens": 1600,
                    "input_tokens_details": {"cached_tokens": 500, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["parallel", "reasoning_retry", "failure", "cancel"])
async def test_subtask_sdk_writes_individual_logs_without_tracing_or_recursion(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(DirectoryUtils, "get_global_sessions_dir", lambda _: str(tmp_path / "sessions"))
    monkeypatch.setattr(
        "siada.agent_hub.coder.sub_task_agent._build_default_tools", lambda **kwargs: [],
    )
    contexts = []

    async def run(model):
        context = CodeAgentContext(root_dir=str(tmp_path), root_session_id="synthetic-session")
        contexts.append(context)
        return await subtask.run_subtask_impl(
            "synthetic accounting", context,
            RunConfig(model=model, tracing_disabled=True),
        )

    if mode == "failure":
        with pytest.raises(RuntimeError, match="synthetic failure"):
            await run(SyntheticModel(fail=True))
    elif mode == "cancel":
        ready = asyncio.Event()
        class CancelModel(SyntheticModel):
            async def stream_response(self, *args, **kwargs):
                ready.set()
                await asyncio.Event().wait()
                yield
        task = asyncio.create_task(run(CancelModel()))
        await asyncio.wait_for(ready.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif mode == "parallel":
        assert await asyncio.gather(run(SyntheticModel()), run(SyntheticModel())) == [
            "usage verified", "usage verified",
        ]
    else:
        assert await run(SyntheticModel(reasoning=True)) == "usage verified"

    logs = list((tmp_path / "sessions" / "synthetic-session" / "subagents").glob("*.log"))
    assert len(logs) == len(contexts)
    expected_requests = 2 if mode == "reasoning_retry" else 1
    for path in logs:
        text = path.read_text()
        assert text.count("MODEL REQUEST USAGE") == expected_requests
        assert "SUB-AGENT USAGE SUMMARY" in text
        assert f"Requests: {expected_requests}" in text
        assert "Duration:" in text
        assert "Model: gpt-5.2" in text
        if mode in ("failure", "cancel"):
            assert "Status: failed" in text
            assert "Cost: unavailable" in text
        else:
            assert "Cost: CNY 0.0227" in text
            assert f"Input={1000 * expected_requests}" in text
    unfinished = subagent_persistence.scan_unfinished(str(tmp_path), "synthetic-session")
    assert unfinished == []