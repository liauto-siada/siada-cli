"""Sub-agent compaction follows the model selected for that run."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import Agent, RunConfig, RunContextWrapper
from agents.run_config import CallModelData, ModelInputData

from siada.agent_hub.context_filter import compaction_strategy
from siada.config.config_loader import LLMConfig, SubAgentConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_run_config import ModelRunConfig
from siada.provider import provider_factory
from siada.provider.default import default_provider
from siada.provider.token_counting import TokenCountingInfo
from siada.services import sub_agent_run_config
from siada.services.agents.models import AgentScope, UserAgentDefinition
from siada.services.model_wrapper import ModelWrapper
from siada.session.session_models import RunningSession
from siada.tools.agent import sub_agent_compaction_filter as compaction
from tests.tools.agent.test_sub_agent_compaction_e2e import _ScriptedModel, _text


subtask = importlib.import_module("siada.tools.agent.run_subtask")


def _named_model(name, form):
    if form == "string":
        return name
    model = _ScriptedModel([[_text("done")]])
    model.model = name
    if form in ("wrapped", "nested"):
        model = ModelWrapper(model)
    if form == "nested":
        model = ModelWrapper(model)
    return model


@pytest.fixture
def default_route(monkeypatch):
    provider = default_provider.DefaultProvider()
    monkeypatch.setattr(default_provider, "get_default_credentials", lambda: (None, None))

    def get_provider(name):
        assert name == "default"
        return provider

    monkeypatch.setattr(provider_factory, "get_provider", get_provider)
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "parent_model",
        "configured_model",
        "definition_model",
        "expected_model",
        "expected_provider",
        "compacts",
        "change_parent_window",
        "initial_window",
        "compact_model",
        "explicit_run_config",
    ),
    [
        pytest.param(
            "gpt-6-luna", None, "kivy-kimi-k3", "kivy-kimi-k3", "default",
            True, False, None, None, False, id="definition",
        ),
        pytest.param(
            "kivy-kimi-k3", "gpt-6-luna", None, "gpt-6-luna", "alternate",
            False, False, None, None, False, id="configured",
        ),
        pytest.param(
            "gpt-6-luna", "kivy-kimi-k3", "gpt-6-luna", "gpt-6-luna", "alternate",
            False, False, None, None, False, id="definition-priority",
        ),
        pytest.param(
            "kivy-kimi-k3", None, None, "kivy-kimi-k3", "default",
            True, True, None, None, False, id="inherited-snapshot",
        ),
        pytest.param(
            "kivy-kimi-k3", None, None, "kivy-kimi-k3", "default",
            False, False, 1_000_000, None, False, id="inherited-custom-window",
        ),
        pytest.param(
            "gpt-6-luna", "kivy-kimi-k3", "unknown-synthetic-model", "kivy-kimi-k3",
            "alternate", True, False, None, None, False, id="unknown-definition-fallback",
        ),
        pytest.param(
            "gpt-6-luna", None, "kivy-kimi-k3", "kivy-kimi-k3", "default",
            True, False, None, "gpt-6-luna", False, id="summary-model-override",
        ),
        pytest.param(
            "gpt-6-luna", None, None, "kivy-kimi-k3", "alternate",
            True, False, None, None, True, id="explicit-run-config",
        ),
    ],
)
async def test_subtask_compaction_uses_selected_model(
    tmp_path,
    monkeypatch,
    parent_model,
    configured_model,
    definition_model,
    expected_model,
    expected_provider,
    compacts,
    change_parent_window,
    initial_window,
    compact_model,
    explicit_run_config,
):
    parent = ModelRunConfig(parent_model)
    parent.provider = "default"
    if initial_window is not None:
        parent.context_window = initial_window
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-compaction-model"
    session.siada_config = MagicMock()
    session.siada_config.llm_config = parent
    session.siada_config.tracing_disabled = True
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    sub_llm = (
        LLMConfig(model=configured_model, provider="alternate")
        if configured_model
        else None
    )
    conf = SimpleNamespace(sub_agent_config=SubAgentConfig(llm_config=sub_llm))
    monkeypatch.setattr("siada.config.config_loader.load_conf", lambda: conf)

    counting_routes = []

    class Provider:
        def __init__(self, name):
            self.name = name

        def get_token_counting_info(self, model_name):
            counting_routes.append((self.name, model_name))
            return TokenCountingInfo(model_name)

    providers = {name: Provider(name) for name in ("default", "alternate")}
    monkeypatch.setattr(sub_agent_run_config, "get_provider", providers.__getitem__)
    monkeypatch.setattr(provider_factory, "get_provider", providers.__getitem__)
    if compact_model:
        monkeypatch.setenv("SIADA_COMPACT_MODEL", compact_model)
    else:
        monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(compaction, "calculate_tokens", lambda *args, **kwargs: 500_000)
    monkeypatch.setattr(compaction_strategy, "calculate_tokens", lambda *args, **kwargs: 100)
    completion = AsyncMock(return_value=object())
    monkeypatch.setattr(compaction_strategy, "one_shot_completion", completion)
    monkeypatch.setattr(
        compaction_strategy, "extract_response_text", lambda _: "<context>summary</context>"
    )

    history = [{"role": "user", "content": f"synthetic message {i}"} for i in range(8)]
    observed = {}

    def run_streamed(**kwargs):
        observed["run_config"] = kwargs["run_config"]

        async def stream_events():
            if change_parent_window:
                parent.context_window = 1_000_000
                parent.model_name = "gpt-6-luna"
                parent.provider = "alternate"
            data = CallModelData(
                model_data=ModelInputData(input=history, instructions="synthetic"),
                agent=kwargs["starting_agent"],
                context=kwargs["context"],
            )
            observed["input"] = (await kwargs["run_config"].call_model_input_filter(data)).input
            if False:
                yield None

        return SimpleNamespace(final_output="done", new_items=[], stream_events=stream_events)

    monkeypatch.setattr(subtask.Runner, "run_streamed", run_streamed)
    definition = (
        UserAgentDefinition(
            name="synthetic",
            description="Synthetic agent",
            prompt="",
            path=tmp_path / "synthetic.md",
            scope=AgentScope.REPO,
            model=definition_model,
        )
        if definition_model
        else None
    )

    selected_config = None
    selected_model_config = None
    if explicit_run_config:
        selected_config = RunConfig(model=expected_model, tracing_disabled=True)
        selected_model_config = ModelRunConfig(expected_model)
        selected_model_config.provider = expected_provider

    assert await subtask.run_subtask_impl(
        "Synthetic task",
        agent_context=context,
        agent_definition=definition,
        run_config=selected_config,
        model_run_config=selected_model_config,
    ) == "done"
    assert observed["run_config"].model == expected_model
    assert counting_routes[0] == (expected_provider, expected_model)
    if compacts:
        completion.assert_awaited_once()
        assert completion.await_args.kwargs["model"] == (compact_model or expected_model)
        assert completion.await_args.kwargs["provider"] == expected_provider
        if compact_model:
            assert (expected_provider, compact_model) in counting_routes
        assert any("summary" in str(item.get("content", "")) for item in observed["input"])
    else:
        completion.assert_not_awaited()
        assert observed["input"] == history


@pytest.mark.asyncio
@pytest.mark.parametrize("provide_mismatched_config", [False, True])
async def test_explicit_named_model_requires_matching_compaction_config(
    tmp_path, monkeypatch, provide_mismatched_config
):
    parent = ModelRunConfig("kivy-kimi-k3")
    parent.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-explicit-run"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    explicit_config = parent if provide_mismatched_config else None
    provider = SimpleNamespace(get_token_counting_info=TokenCountingInfo)
    monkeypatch.setattr(provider_factory, "get_provider", lambda _: provider)

    with pytest.raises(ValueError, match="model.*config|model_run_config"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model="gpt-6-luna", tracing_disabled=True),
            model_run_config=explicit_config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["string", "model", "wrapped", "nested"])
@pytest.mark.parametrize("explicit_config", [False, True])
async def test_explicit_model_accepts_provider_normalized_name(
    tmp_path, monkeypatch, default_route, form, explicit_config
):
    parent = ModelRunConfig("claude-sonnet-5")
    parent.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-routed-model"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    selected = _named_model("anthropic/claude-sonnet-5", form)
    observed = []
    monkeypatch.setattr(
        compaction, "calculate_tokens",
        lambda model_name, *args, **kwargs: observed.append(model_name) or 100,
    )

    def run_streamed(**kwargs):
        async def stream_events():
            data = CallModelData(
                model_data=ModelInputData(
                    input=[{"role": "user", "content": "synthetic"}],
                    instructions="synthetic",
                ),
                agent=kwargs["starting_agent"],
                context=kwargs["context"],
            )
            await kwargs["run_config"].call_model_input_filter(data)
            if False:
                yield None

        return SimpleNamespace(final_output="done", new_items=[], stream_events=stream_events)

    monkeypatch.setattr(subtask.Runner, "run_streamed", run_streamed)
    result = await subtask.run_subtask_impl(
        "Synthetic task",
        agent_context=context,
        run_config=RunConfig(model=selected, tracing_disabled=True),
        model_run_config=parent if explicit_config else None,
    )

    assert result == "done"
    assert observed == ["anthropic/claude-sonnet-5"]


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["string", "model", "wrapped", "nested"])
@pytest.mark.parametrize("explicit_config", [False, True])
async def test_explicit_model_rejects_mismatched_compaction_configuration(
    tmp_path, monkeypatch, default_route, form, explicit_config
):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-mismatched-model"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    selected = _named_model("kivy-kimi-k3", form)
    run_streamed = MagicMock(side_effect=AssertionError("model must not be called"))
    monkeypatch.setattr(subtask.Runner, "run_streamed", run_streamed)

    with pytest.raises(ValueError, match="model.*config|model_run_config"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model=selected, tracing_disabled=True),
            model_run_config=parent if explicit_config else None,
        )

    run_streamed.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["string", "model", "wrapped", "nested"])
async def test_explicit_model_normalizes_both_model_names(
    tmp_path, monkeypatch, default_route, form
):
    parent = ModelRunConfig("claude-sonnet-5")
    parent.provider = "default"
    explicit_config = ModelRunConfig("claude-sonnet-5")
    explicit_config.model_name = "anthropic/claude-sonnet-5"
    explicit_config.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-normalized-string"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)

    async def stream_events():
        if False:
            yield None

    result = SimpleNamespace(final_output="done", new_items=[], stream_events=stream_events)
    monkeypatch.setattr(subtask.Runner, "run_streamed", lambda **kwargs: result)
    assert await subtask.run_subtask_impl(
        "Synthetic task",
        agent_context=context,
        run_config=RunConfig(
            model=_named_model("claude-sonnet-5", form),
            model_provider=default_route,
            tracing_disabled=True,
        ),
        model_run_config=explicit_config,
    ) == "done"


@pytest.mark.asyncio
async def test_missing_provider_route_does_not_hide_different_models(tmp_path, monkeypatch):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "synthetic"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-missing-route"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    provider = SimpleNamespace(get_token_counting_info=lambda _: TokenCountingInfo(None))
    monkeypatch.setattr(provider_factory, "get_provider", lambda _: provider)

    with pytest.raises(ValueError, match="model.*config|model_run_config"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model="kivy-kimi-k3", tracing_disabled=True),
            model_run_config=parent,
        )


@pytest.mark.asyncio
async def test_matching_wire_name_does_not_hide_different_protocols(tmp_path, monkeypatch):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "synthetic"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-protocol-mismatch"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)

    def counting_info(name):
        if name == "gpt-6-luna":
            return TokenCountingInfo("synthetic-wire-model", "responses", "siada_responses")
        return TokenCountingInfo("synthetic-wire-model", "chat")

    provider = SimpleNamespace(get_token_counting_info=counting_info)
    monkeypatch.setattr(provider_factory, "get_provider", lambda _: provider)

    with pytest.raises(ValueError, match="model.*config|model_run_config"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model="synthetic-alias", tracing_disabled=True),
            model_run_config=parent,
        )


@pytest.mark.asyncio
async def test_cyclic_model_wrapper_fails_before_running(tmp_path):
    parent = ModelRunConfig("gpt-6-luna")
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-wrapper-cycle"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    model = ModelWrapper(_ScriptedModel([[_text("done")]]))
    model.wrapped_model = model

    with pytest.raises(ValueError, match="cycle"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model=model, tracing_disabled=True),
        )


@pytest.mark.asyncio
async def test_wrapper_of_named_custom_model_rejects_mismatch(
    tmp_path, monkeypatch, default_route
):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-wrapped-custom-model"
    session.siada_config = MagicMock(llm_config=parent)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session)
    model = ModelWrapper(SimpleNamespace(model="kivy-kimi-k3"))
    run_streamed = MagicMock(side_effect=AssertionError("model must not be called"))
    monkeypatch.setattr(subtask.Runner, "run_streamed", run_streamed)

    with pytest.raises(ValueError, match="model.*config|model_run_config"):
        await subtask.run_subtask_impl(
            "Synthetic task",
            agent_context=context,
            run_config=RunConfig(model=model, tracing_disabled=True),
            model_run_config=parent,
        )
    run_streamed.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_real_runner_accepts_provider_normalized_model(
    tmp_path, monkeypatch, default_route, wrapped
):
    parent = ModelRunConfig("claude-sonnet-5")
    parent.provider = "default"
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-normalized-runner"
    session.siada_config = MagicMock(llm_config=parent, tracing_disabled=True)
    context = CodeAgentContext(root_dir=str(tmp_path), session=session, web_tools_enabled=False)
    model = _ScriptedModel([[_text("done")]])
    model.model = "anthropic/claude-sonnet-5"
    selected = ModelWrapper(model) if wrapped else model
    monkeypatch.setattr(compaction, "calculate_tokens", lambda *args, **kwargs: 100)
    monkeypatch.setattr("siada.tools.agent.sub_agent_notifier._send_notification", lambda *args: None)

    assert await subtask.run_subtask_impl(
        "Synthetic task",
        agent_context=context,
        run_config=RunConfig(model=selected, tracing_disabled=True),
    ) == "done"
    assert len(model.received_inputs) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_real_runner_compacts_using_explicit_model_configuration(
    tmp_path, monkeypatch, wrapped
):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "default"
    child = ModelRunConfig("kivy-kimi-k3")
    child.provider = "synthetic"
    provider = SimpleNamespace(
        get_token_counting_info=lambda name: TokenCountingInfo(name.removeprefix("kivy-"))
    )
    monkeypatch.setattr(provider_factory, "get_provider", lambda _: provider)
    history = [{"role": "user", "content": f"synthetic message {i}"} for i in range(8)]
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-explicit-compaction"
    session.siada_config = MagicMock(llm_config=parent, tracing_disabled=True)
    session.openai_session = SimpleNamespace(get_runtime_items=AsyncMock(return_value=history))
    context = CodeAgentContext(root_dir=str(tmp_path), session=session, web_tools_enabled=False)
    run_ctx = RunContextWrapper(context=context)
    run_ctx.agent = Agent(name="synthetic-parent", instructions="Synthetic instructions", tools=[])
    model = _ScriptedModel([[_text("done")]])
    model.model = "kimi-k3"
    selected = ModelWrapper(model) if wrapped else model
    monkeypatch.setattr("siada.tools.agent.sub_agent_notifier._send_notification", lambda *args: None)
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(compaction, "calculate_tokens", lambda *args, **kwargs: 500_000)
    monkeypatch.setattr(compaction_strategy, "calculate_tokens", lambda *args, **kwargs: 100)
    completion = AsyncMock(return_value=object())
    monkeypatch.setattr(compaction_strategy, "one_shot_completion", completion)
    monkeypatch.setattr(
        compaction_strategy, "extract_response_text", lambda _: "<context>synthetic summary</context>"
    )

    assert await subtask.run_subtask_impl(
        "Synthetic task",
        agent_context=context,
        run_config=RunConfig(model=selected, tracing_disabled=True),
        model_run_config=child,
        fork=True,
        run_ctx=run_ctx,
    ) == "done"
    completion.assert_awaited_once()
    assert completion.await_args.kwargs["model"] == "kivy-kimi-k3"
    assert completion.await_args.kwargs["provider"] == "synthetic"
    assert any(
        "synthetic summary" in str(item.get("content", ""))
        for item in model.received_inputs[0]
    )
    assert parent.context_window == 1_000_000


@pytest.mark.asyncio
async def test_real_runner_uses_selected_model_for_fork_compaction(tmp_path, monkeypatch):
    parent = ModelRunConfig("gpt-6-luna")
    parent.provider = "default"
    history = [{"role": "user", "content": f"synthetic message {i}"} for i in range(8)]
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-runner"
    session.siada_config = MagicMock(llm_config=parent, tracing_disabled=True)
    session.openai_session = SimpleNamespace(get_runtime_items=AsyncMock(return_value=history))
    context = CodeAgentContext(root_dir=str(tmp_path), session=session, web_tools_enabled=False)
    run_ctx = RunContextWrapper(context=context)
    run_ctx.agent = Agent(name="synthetic-parent", instructions="Synthetic instructions", tools=[])
    conf = SimpleNamespace(
        sub_agent_config=SubAgentConfig(
            llm_config=LLMConfig(model="kivy-kimi-k3", provider="alternate")
        )
    )
    monkeypatch.setattr("siada.config.config_loader.load_conf", lambda: conf)
    monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setenv("SIADA_SUBAGENT_DUMP", "0")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setattr("siada.tools.agent.sub_agent_notifier._send_notification", lambda *args: None)

    model = _ScriptedModel([[_text("done")]])
    selected_models = []
    counting_models = []

    class Provider:
        def get_model(self, model_name):
            selected_models.append(model_name)
            return model

        def get_token_counting_info(self, model_name):
            counting_models.append(model_name)
            return TokenCountingInfo(model_name)

    provider = Provider()

    def get_provider(name):
        assert name == "alternate"
        return provider

    monkeypatch.setattr(sub_agent_run_config, "get_provider", get_provider)
    monkeypatch.setattr(provider_factory, "get_provider", get_provider)
    monkeypatch.setattr(compaction, "calculate_tokens", lambda *args, **kwargs: 500_000)
    monkeypatch.setattr(compaction_strategy, "calculate_tokens", lambda *args, **kwargs: 100)
    completion = AsyncMock(return_value=object())
    monkeypatch.setattr(compaction_strategy, "one_shot_completion", completion)
    monkeypatch.setattr(
        compaction_strategy, "extract_response_text", lambda _: "<context>synthetic summary</context>"
    )

    result = await subtask.run_subtask_impl(
        "Synthetic task", agent_context=context, fork=True, run_ctx=run_ctx
    )

    assert result == "done"
    assert selected_models == ["kivy-kimi-k3"]
    assert counting_models[0] == "kivy-kimi-k3"
    completion.assert_awaited_once()
    assert completion.await_args.kwargs["model"] == "kivy-kimi-k3"
    assert completion.await_args.kwargs["provider"] == "alternate"
    assert any(
        "synthetic summary" in str(item.get("content", ""))
        for item in model.received_inputs[0]
    )
    assert parent.model_name == "gpt-6-luna"
    assert parent.context_window == 1_000_000