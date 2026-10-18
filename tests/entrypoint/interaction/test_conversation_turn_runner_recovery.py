"""Real offline Runner continuation over durable effective-context storage."""

import asyncio
import copy
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from agents import Agent, RunConfig, Runner, function_tool
from agents.models.interface import Model
from openai.types.responses import (
    Response, ResponseCompletedEvent, ResponseCreatedEvent,
    ResponseFunctionToolCall, ResponseFunctionCallArgumentsDeltaEvent,
    ResponseOutputItemAddedEvent, ResponseOutputMessage, ResponseOutputText,
    ResponseTextDeltaEvent,
)

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.services.effective_context_session import configure_effective_run
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper
from siada.services.siada_runner import SiadaRunner


class InterruptedModel(Model):
    model = "synthetic"

    def __init__(self, failure):
        self.failure = failure
        self.inputs = []
        self.closed = []

    async def get_response(self, *args, **kwargs):
        raise AssertionError("Streaming required")

    async def stream_response(self, system_instructions, input, *args, **kwargs):
        self.inputs.append(copy.deepcopy(input))
        index = len(self.inputs)
        response = Response(
            id=f"response-{index}", created_at=0, model=self.model,
            object="response", output=[], parallel_tool_calls=False,
            tool_choice="auto", tools=[],
        )
        try:
            yield ResponseCreatedEvent(type="response.created", sequence_number=0, response=response)
            if index == 1:
                response.output = [ResponseFunctionToolCall(
                    id="completed-item", call_id="completed-call", type="function_call",
                    name="record_action", arguments="{}",
                )]
            elif index == 2:
                if self.failure == "tool":
                    yield ResponseOutputItemAddedEvent(
                        type="response.output_item.added", sequence_number=1, output_index=0,
                        item=ResponseFunctionToolCall(
                            id="unfinished-item", call_id="unfinished-call", type="function_call",
                            name="record_action", arguments="",
                        ),
                    )
                    yield ResponseFunctionCallArgumentsDeltaEvent(
                        type="response.function_call_arguments.delta", sequence_number=2,
                        item_id="unfinished-item", output_index=0, delta='{"unfinished":',
                    )
                else:
                    yield ResponseTextDeltaEvent(
                        type="response.output_text.delta", sequence_number=1,
                        item_id="partial-message", output_index=0, content_index=0,
                        delta="partial answer", logprobs=[],
                    )
                if self.failure == "timeout":
                    raise httpx.ReadTimeout("synthetic interruption")
                return
            else:
                response.output = [ResponseOutputMessage(
                    id="final-message", type="message", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text="Recovered.", annotations=[])],
                )]
            yield ResponseCompletedEvent(
                type="response.completed", sequence_number=3, response=response,
            )
        finally:
            self.closed.append(index)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["text", "tool", "timeout"])
async def test_real_runner_preserves_completed_tools_and_drops_unfinished_calls(
    failure, tmp_path, monkeypatch,
):
    actions = []

    @function_tool
    def record_action() -> str:
        """Record one synthetic operation."""
        actions.append("done")
        return "action completed"

    store = FileSession("recovery", tmp_path)
    await store.migrate_legacy_context(allow_history_only=True)
    model = InterruptedModel(failure)
    agent = Agent(name="recovery", model=ModelWrapper(model), tools=[record_action])
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        agent_name="recovery", workspace=str(tmp_path),
        llm_config=SimpleNamespace(model_name="synthetic"),
        io=SimpleNamespace(acp_enabled=True, pretty=False, print_warning=Mock()),
    )
    turn.session = SimpleNamespace(openai_session=store)
    turn._result_ready = threading.Event()
    turn._message_counter = 0
    turn._current_message_id = None
    turn._stream_start_id = None
    turn.mdstream = None
    turn._stop_waiting_spinner = Mock()
    turn._send_lifecycle_event = Mock()
    turn._live_incremental_response = Mock()
    turn._print_context_usage = Mock()
    turn.config.io.advance_tool_call_stage = Mock()
    turn.config.io.print_tool_call_all_stages = Mock()
    monkeypatch.setattr(
        "siada.entrypoint.interaction.turn.conversation_turn.render_tool_call_output", Mock(),
    )

    async def run(**kwargs):
        async def identity_filter(data):
            return data.model_data

        bridge, config = await configure_effective_run(
            store, RunConfig(tracing_disabled=True, call_model_input_filter=identity_filter),
            agent=agent,
        )
        return Runner.run_streamed(
            agent, input=kwargs["user_input"], session=bridge, run_config=config,
        )

    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    result = await turn._run_stream_with_recovery("original task")
    assert result.final_output == "Recovered."
    assert actions == ["done"]
    assert model.closed == [1, 2, 3]
    resumed = model.inputs[-1]
    assert sum(item.get("content") == "original task" for item in resumed) == 1
    outputs = [item for item in resumed if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert outputs[0]["call_id"] == "completed-call"
    assert outputs[0]["output"] == "action completed"
    assert any(item.get("content") == turn._STREAM_RECOVERY_INPUT for item in resumed)
    history = await store.get_history_items()
    assert sum(item.get("call_id") == "completed-call" for item in history) == 2
    assert not any(item.get("call_id") == "unfinished-call" for item in history)
    assert not any(item.get("call_id") == "unfinished-call" for item in resumed)
    starts = [call.args[0] for call in turn._send_lifecycle_event.call_args_list
              if call.args[0]["type"] == "message_start"]
    assert len({event["message_id"] for event in starts}) == len(starts)
    turn.config.io.print_warning.assert_called_once()