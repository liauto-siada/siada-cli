"""Offline fixtures for the pre-refactor session characterization suite."""

from __future__ import annotations

import copy
import importlib
import json
import os
import socket
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import Agent, RunConfig, Runner
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

from siada.agent_hub.context_filter import api_message_transfer_filter as transfer
from siada.agent_hub.hooks.agent_processors.context_track_processor import (
    ContextTrackProcessor,
)
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_base_config import ModelBaseConfig
from siada.models.model_run_config import ModelRunConfig
from siada.services.file_session import FileSession
from siada.session.session_models import RunningSession
from siada.utils import DirectoryUtils

capture = importlib.import_module("siada.agent_hub.context_filter.context_capture_filter")
estimator = importlib.import_module("siada.agent_hub.context_filter.request_token_estimator")

# litellm is imported lazily by the context filters and would otherwise fetch
# its model-cost map over the network on first use. Keep the suite offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


def text_message(text: str, message_id: str = "message-final") -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=message_id,
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


def tool_call(call_id: str, name: str, arguments: dict) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=f"item-{call_id}",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
        type="function_call",
    )


def detailed_usage(input_tokens: int = 120, output_tokens: int = 30) -> Usage:
    return Usage(
        requests=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=20, cache_write_tokens=10),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=7),
    )


class ScriptedModel(Model):
    """Replay bounded responses and observe real model input and on-disk state."""

    def __init__(self, session: FileSession, steps: list, usages: list[Usage] | None = None):
        self.session = session
        self.steps = deque(steps)
        self.usages = deque(usages or [detailed_usage() for _ in steps])
        self.requests: list[dict] = []

    async def _next(self, instructions, input) -> tuple[list, Usage]:
        snapshot, last_index = await self.session.get_api_messages()
        self.requests.append({
            "instructions": instructions,
            "input": copy.deepcopy(input),
            "history": copy.deepcopy(await self.session.get_history_items(include_injected=True)),
            "snapshot": copy.deepcopy(snapshot),
            "last_index": last_index,
        })
        if not self.steps:
            raise AssertionError("Runner made an unexpected extra model request")
        step = self.steps.popleft()
        usage = self.usages.popleft()
        if isinstance(step, BaseException):
            raise step
        return step, usage

    async def get_response(self, system_instructions, input, *args, **kwargs):
        output, usage = await self._next(system_instructions, input)
        return ModelResponse(
            output=output,
            usage=usage,
            response_id=f"response-{len(self.requests)}",
        )

    async def stream_response(self, system_instructions, input, *args, **kwargs):
        output, usage = await self._next(system_instructions, input)
        for item in output:
            if isinstance(item, ResponseOutputMessage):
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    sequence_number=0,
                    item_id=item.id,
                    output_index=0,
                    content_index=0,
                    delta=item.content[0].text,
                    logprobs=[],
                )
        yield ResponseCompletedEvent(
            type="response.completed",
            sequence_number=1,
            response=Response(
                id=f"response-{len(self.requests)}",
                created_at=0,
                model="baseline-model",
                object="response",
                output=output,
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
                usage=ResponseUsage(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    input_tokens_details=usage.input_tokens_details,
                    output_tokens_details=usage.output_tokens_details,
                ),
            ),
        )


class BaselineHarness:
    def __init__(self, root: Path):
        self.root = root
        self.compactions: list[list] = []
        self.compact_at: int | None = None

    def workspace(self, name: str = "workspace") -> Path:
        workspace = self.root / name
        workspace.mkdir(exist_ok=True)
        return workspace

    def session(self, session_id: str = "session-main", workspace: Path | None = None):
        workspace = workspace or self.workspace()
        config = RunningConfig(
            llm_config=ModelRunConfig("baseline-model"),
            io=MagicMock(),
            workspace=str(workspace),
            agent_name="baseline-agent",
            tracing_disabled=True,
        )
        session = RunningSession(siada_config=config, session_id=session_id)
        session.state.openai_session = FileSession(
            session_id=session_id,
            sessions_dir=DirectoryUtils.get_global_sessions_dir(str(workspace)),
            project_root=str(workspace),
        )
        return session

    def context(self, session: RunningSession) -> CodeAgentContext:
        return CodeAgentContext(session=session, root_dir=session.siada_config.workspace)

    def model(self, session: RunningSession, steps: list, usages: list[Usage] | None = None):
        return ScriptedModel(session.openai_session, steps, usages)

    text = staticmethod(text_message)
    call = staticmethod(tool_call)
    usage = staticmethod(detailed_usage)

    async def compact(self, context, real_api_messages, tokens_count, **kwargs):
        if self.compact_at is None or len(real_api_messages) < self.compact_at:
            return real_api_messages
        self.compactions.append(copy.deepcopy(real_api_messages))
        return [{"role": "user", "content": "[baseline compaction summary]"}]

    async def run(self, session, model, *, stream=False, input="start", tools=None,
                  hooks=None, context=None, input_filter=None):
        context = context or self.context(session)
        agent = Agent(
            name="baseline-agent",
            instructions="# Baseline\nUse the supplied tools.",
            model=model,
            tools=tools or [],
            hooks=ContextTrackProcessor(),
        )
        run_config = RunConfig(
            tracing_disabled=True,
            call_model_input_filter=input_filter or capture.context_capture_filter,
        )
        if stream:
            result = Runner.run_streamed(
                agent, input=input, context=context, session=session.openai_session,
                run_config=run_config, hooks=hooks, max_turns=8,
            )
            events = [event async for event in result.stream_events()]
            return result, context, events
        result = await Runner.run(
            agent, input=input, context=context, session=session.openai_session,
            run_config=run_config, hooks=hooks, max_turns=8,
        )
        return result, context, []


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    """Isolate all session paths and reject accidental outgoing connections."""
    network_attempts = []

    def deny_network(*args, **kwargs):
        network_attempts.append(True)
        raise RuntimeError("Session baseline must not access the network")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(
        "siada.models.model_run_config.get_model_config",
        lambda _: ModelBaseConfig(model_name="baseline-model", context_window=1_000_000),
    )
    monkeypatch.setattr(
        DirectoryUtils, "get_global_sessions_dir",
        lambda workspace: str(tmp_path / Path(workspace).name / "sessions"),
    )
    monkeypatch.setattr(DirectoryUtils, "get_project_temp_dir", lambda _: str(tmp_path / "temp"))
    monkeypatch.setattr(
        DirectoryUtils, "get_project_checkpoint_dir", lambda _: str(tmp_path / "checkpoints"),
    )
    monkeypatch.setattr(capture, "_CONTEXT_FILTERS", None)
    monkeypatch.setattr(transfer, "calculate_tokens", lambda _, value, **kwargs: len(value) * 10)
    # The request estimator binds the tokenizer at import time.
    monkeypatch.setattr(estimator, "calculate_tokens", lambda _, value, **kwargs: len(value) * 10)
    # The per-request dynamic window resolver is private-only; skip it here.
    monkeypatch.setattr(
        transfer.ApiMessageTransferFilter, "_resolve_effective_context_window",
        lambda _: None, raising=False,
    )
    from siada.services.memory import combined_memory, memory_update

    monkeypatch.setattr(memory_update, "get_memory_scheduler", lambda _: None)
    monkeypatch.setattr(combined_memory, "build_combined_memory", lambda *args: "baseline memory")
    harness = BaselineHarness(tmp_path)

    async def compact(_filter, **kwargs):
        return await harness.compact(**kwargs)

    monkeypatch.setattr(transfer.ApiMessageTransferFilter, "_try_compact_real_api_messages", compact)
    from siada.io import stdin_interrupt_monitor
    from siada.tools.todo import todo_write_tool
    from siada.tools.agent import sub_agent_notifier
    from siada.services.siada_runner import SiadaRunner

    monkeypatch.setattr(stdin_interrupt_monitor, "drain_pending_injections", lambda: [])
    monkeypatch.setattr(todo_write_tool, "_push_todo_state_via_acp", lambda _: None)
    monkeypatch.setattr(sub_agent_notifier, "_send_notification", lambda *args: None)
    monkeypatch.setattr(SiadaRunner, "_context_cache", {})
    monkeypatch.setattr(SiadaRunner, "_prepare_checkpoint_with_timeout", AsyncMock())
    from siada.tools.agent import subagent_async, subagent_persistence

    monkeypatch.setattr(subagent_async, "_SESSION_TASKS", {})
    monkeypatch.setattr(subagent_async, "_SESSION_WAKEUP", {})
    monkeypatch.setattr(subagent_persistence, "_INDEX_LOCKS", {})
    yield harness
    # Known-gap markers accept AssertionError, so use a different failure type.
    if network_attempts:
        raise RuntimeError("Session baseline attempted a network connection")