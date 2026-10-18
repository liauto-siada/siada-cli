"""Cache-free route descriptions must match actual SDK request semantics."""

import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import Agent, RunConfig, RunHooks, function_tool

from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.provider.token_counting import TokenCountingInfo, token_counting_info_from_model
from siada.services.effective_context_session import EffectiveContextSession
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelWrapper
from siada.services.session_runtime_state import load_state
from siada.services.session_storage import SessionStorageError
from tests.session.baseline.test_default_context_cutover import run_default


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_same_run_tool_loop_resolves_fresh_equivalent_models(baseline, monkeypatch, stream):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)

    @function_tool
    def echo(value: str) -> str:
        """Return a deterministic synthetic tool result."""
        return value

    steps = [[baseline.call("tool-1", "echo", {"value": "ok"})], [baseline.text("finished")]]
    models = []

    def resolve(name):
        model = baseline.model(session, [steps[len(models)]])
        model.model = "glm-effective"
        models.append(model)
        return ModelWrapper(model, input_processor=process_input)

    provider = SimpleNamespace(
        get_model=Mock(side_effect=resolve),
        get_token_counting_info=Mock(return_value=TokenCountingInfo("glm-effective")),
    )
    config = RunConfig(tracing_disabled=True, model="configured-alias", model_provider=provider)
    await run_default(baseline, session, "unused-model", stream=stream, config=config, context=context, tools=[echo])
    assert len(models) == 2 and models[0] is not models[1]
    assert all(len(model.requests) == 1 for model in models)
    assert provider.get_model.call_count == 2
    provider.get_token_counting_info.assert_called_once_with("configured-alias")
    assert all(call.args[0] == "glm-effective" for call in counter.call_args_list)
    assert counter.call_count == 3
    assert counter.call_args_list[2].kwargs == {"diagnostics": {}}
    assert counter.call_args_list[2].args[1][0]["type"] == "function_call_output"
    assert session.state.context_token_baseline is not None
    assert config.model == "configured-alias"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("change", ["name", "protocol", "projection", "replay", "processor"])
async def test_mismatch_aborts_warm_budget_without_committing_hook_queue(baseline, monkeypatch, stream, change):
    from siada.provider.responses import ResponsesModel

    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    original = baseline.model(session, [[baseline.text("initial", "initial")]])
    original.model = "glm-effective"
    info = TokenCountingInfo("glm-effective", "responses" if change == "projection" else "chat")
    original.supports_native_responses_items = info.protocol == "responses"
    provider = SimpleNamespace(get_model=Mock(return_value=original), get_token_counting_info=lambda name: info)
    config = RunConfig(tracing_disabled=True, model="configured-alias", model_provider=provider)
    await run_default(baseline, session, "unused-model", stream=stream, config=config, context=context, input="initial")
    saved = copy.deepcopy(load_state(session.openai_session.session_folder, session.session_id))
    assert saved["context_token_baseline"] is not None
    counter.reset_mock()
    actual = baseline.model(session, [[baseline.text("must not send")]])
    actual.model = "glm-effective"
    if change == "name":
        actual.model = "different-model"
    elif change == "protocol":
        actual.supports_native_responses_items = True
    elif change == "projection":
        transport = SimpleNamespace(create=Mock())
        actual = ResponsesModel("glm-effective", transport=transport)
    elif change == "replay":
        actual.should_replay_reasoning_content = lambda value: False
    elif change == "processor":
        actual = ModelWrapper(actual, input_processor=lambda value: value)
    provider.get_model = Mock(return_value=actual)
    reminder = {"role": "system", "content": "synthetic uncommitted reminder"}

    class ReminderHooks(RunHooks):
        async def on_llm_start(self, wrapped, agent, system_prompt, input_items):
            wrapped.context.pending_reminder_items = [copy.deepcopy(reminder)]
            input_items.append(copy.deepcopy(reminder))

    with pytest.raises(SessionStorageError, match="counting semantics changed; restart"):
        await run_default(
            baseline, session, "unused-model", stream=stream, config=config, context=context,
            input="continue", hooks=ReminderHooks(),
        )
    assert context.session.state.context_token_baseline is None
    assert context.runtime_session._request_token_signature is None
    assert context.pending_reminder_items == [reminder]
    assert reminder not in await session.openai_session.get_context_items()
    assert reminder not in await session.openai_session.get_history_items()
    assert load_state(session.openai_session.session_folder, session.session_id)["usage"] == saved["usage"]
    assert counter.call_count == 1
    counter.assert_called_once_with("glm-effective", [{"role": "user", "content": "continue"}], diagnostics={})
    if change == "projection":
        transport.create.assert_not_called()
    else:
        assert getattr(actual, "wrapped_model", actual).requests == []
    provider.get_model.assert_called_once_with("configured-alias")


@pytest.mark.parametrize("description", [None, "invalid"])
def test_custom_named_provider_requires_valid_counting_information(baseline, description):
    provider = SimpleNamespace(get_model=Mock())
    if description is not None:
        provider.get_token_counting_info = lambda name: description
    config = RunConfig(model="custom-model", model_provider=provider)
    bridge = EffectiveContextSession(baseline.session().openai_session)
    with pytest.raises(ValueError, match="get_token_counting_info"):
        bridge.configure_run(config, agent=Agent(name="synthetic", model="unused-model"))
    provider.get_model.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_model_mutation_in_post_filter_hook_is_verified_before_send(baseline, monkeypatch, stream):
    session = baseline.session()
    model = baseline.model(session, [[baseline.text("must not send")]])
    model.model = "glm-effective"
    monkeypatch.setattr(estimator, "calculate_tokens", Mock(return_value=10))

    class MutatingHooks(RunHooks):
        async def on_llm_start(self, context, agent, system_prompt, input_items):
            model.model = "different-model"

    with pytest.raises(SessionStorageError, match="counting semantics changed"):
        await run_default(baseline, session, model, stream=stream, hooks=MutatingHooks())
    assert model.requests == []
    assert token_counting_info_from_model(model).model_name == "different-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_reconfigured_route_recounts_incompatible_durable_anchor_after_mismatch(baseline, monkeypatch, stream):
    session = baseline.session()
    context = baseline.context(session)
    counter = Mock(return_value=10)
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    first = baseline.model(session, [[baseline.text("initial", "initial")]])
    first.model = "glm-first"
    provider = SimpleNamespace(
        get_model=Mock(return_value=first), get_token_counting_info=Mock(return_value=TokenCountingInfo("glm-first")),
    )
    config = RunConfig(tracing_disabled=True, model="synthetic-alias", model_provider=provider)
    await run_default(baseline, session, "unused-model", stream=stream, config=config, context=context, input="initial")
    old_anchor = session.state.context_token_baseline
    second = baseline.model(session, [[baseline.text("recovered", "recovered")]])
    second.model = "glm-second"
    provider.get_model = Mock(return_value=second)
    with pytest.raises(SessionStorageError, match="counting semantics changed"):
        await run_default(baseline, session, "unused-model", stream=stream, config=config, context=context, input="continue")
    assert second.requests == [] and session.state.context_token_baseline is None
    provider.get_token_counting_info.return_value = TokenCountingInfo("glm-second")
    # Restore the persisted anchor, as reconnect/resume would, before retrying.
    session.state.context_token_baseline = old_anchor
    counter.reset_mock()
    await run_default(baseline, session, "unused-model", stream=stream, config=config, context=context, input=[])
    assert len(second.requests) == 1
    assert second.requests[0]["input"].count({"role": "user", "content": "continue"}) == 1
    assert counter.call_count == 2
    assert counter.call_args_list[0].kwargs == {"tools": [], "diagnostics": {}}
    assert counter.call_args_list[0].args[1] == second.requests[0]["input"]
    assert all(call.args[0] == "glm-second" for call in counter.call_args_list)
    assert session.state.context_token_baseline.signature != old_anchor.signature
