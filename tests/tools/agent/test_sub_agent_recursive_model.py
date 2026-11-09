"""
Recursive sub-agent model inheritance (root -> named child -> grandchild).

Covers the ``sub_agent.allow_recursive_subagents`` inheritance chain:

- A named depth-1 agent that selects its own model (definition ``model``
  field) must pass that *effective* model on to any depth-2 (grandchild)
  agent it spawns, instead of falling back to the root session's model.
- The grandchild's compaction (token counting, context window, summary
  request model) must follow the grandchild's own effective model, with
  ``SIADA_COMPACT_MODEL`` still overriding the summary model.
- ``sub_agent.llm_config`` (conf.yaml) and named-agent ``model`` overrides
  keep their precedence at every nesting level.
- The non-recursive path is untouched: recursion-off clones carry neither a
  session nor an inherited llm config.

All tests are offline: ``Runner.run_streamed`` is replaced by a capture stub
and providers are synthetic objects — no real model is ever called.
"""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents.run_config import CallModelData, ModelInputData

from siada.agent_hub.context_filter import compaction_strategy
from siada.config.config_loader import LLMConfig, SubAgentConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_run_config import ModelRunConfig
from siada.provider import provider_factory
from siada.provider.token_counting import TokenCountingInfo
from siada.services import sub_agent_run_config
from siada.services.agents.models import AgentScope, UserAgentDefinition
from siada.session.session_models import RunningSession
from siada.tools.agent import sub_agent_compaction_filter as compaction
from siada.tools.agent.run_subtask import _clone_context_for_subagent

subtask = importlib.import_module("siada.tools.agent.run_subtask")

ROOT_MODEL = "kivy-kimi-k3"
CHILD_MODEL = "gpt-6-luna"
GRANDCHILD_DEFINITION_MODEL = "kivy-glm-5.2"
CONFIGURED_MODEL = "kivy-glm-5.2"


def _make_root_context(tmp_path, model=ROOT_MODEL, provider="default", recursive=True):
    """Root (main-agent) context whose session runs on *model*."""
    llm = ModelRunConfig(model)
    llm.provider = provider
    session = MagicMock(spec=RunningSession)
    session.session_id = "synthetic-recursive-root"
    session.siada_config = MagicMock(llm_config=llm, tracing_disabled=True)
    context = CodeAgentContext(
        root_dir=str(tmp_path),
        session=session,
        allow_recursive_subagents=recursive,
    )
    return context, session, llm


def _install_offline_overrides(monkeypatch, conf_sub_llm=None):
    """Synthetic providers + empty sub_agent conf + silent notifications."""
    routes = []

    class Provider:
        def __init__(self, name):
            self.name = name

        def get_token_counting_info(self, model_name):
            routes.append((self.name, model_name))
            return TokenCountingInfo(model_name)

    providers = {"default": Provider("default"), "alternate": Provider("alternate")}
    monkeypatch.setattr(sub_agent_run_config, "get_provider", providers.__getitem__)
    monkeypatch.setattr(provider_factory, "get_provider", providers.__getitem__)
    conf = SimpleNamespace(sub_agent_config=SubAgentConfig(llm_config=conf_sub_llm))
    monkeypatch.setattr("siada.config.config_loader.load_conf", lambda: conf)
    monkeypatch.setattr(
        "siada.tools.agent.sub_agent_notifier._send_notification", lambda *args: None
    )
    return routes


def _capture_runner(captured, *, invoke_filter=False, filter_input=None):
    """Replace Runner.run_streamed: record kwargs, optionally run the filter."""

    def run_streamed(**kwargs):
        captured.append(kwargs)

        async def stream_events():
            if invoke_filter:
                data = CallModelData(
                    model_data=ModelInputData(
                        input=list(filter_input or [{"role": "user", "content": "synthetic"}]),
                        instructions="synthetic",
                    ),
                    agent=kwargs["starting_agent"],
                    context=kwargs["context"],
                )
                await kwargs["run_config"].call_model_input_filter(data)
            if False:
                yield None

        return SimpleNamespace(final_output="done", new_items=[], stream_events=stream_events)

    return run_streamed


def _gpt_agent_definition(tmp_path, model=CHILD_MODEL, name="gpt-agent"):
    return UserAgentDefinition(
        name=name,
        description="Synthetic GPT agent",
        prompt="",
        path=tmp_path / f"{name}.md",
        scope=AgentScope.REPO,
        model=model,
    )


async def _spawn_depth1(tmp_path, monkeypatch, *, definition_model=CHILD_MODEL,
                         conf_sub_llm=None):
    """Spawn a named depth-1 agent from the Kimi root; return (depth1_ctx, captured)."""
    root_ctx, _, _ = _make_root_context(tmp_path)
    _install_offline_overrides(monkeypatch, conf_sub_llm=conf_sub_llm)
    captured = []
    monkeypatch.setattr(subtask.Runner, "run_streamed", _capture_runner(captured))

    await subtask.run_subtask_impl(
        "child task",
        agent_context=root_ctx,
        agent_definition=_gpt_agent_definition(tmp_path, model=definition_model),
    )
    depth1_kwargs = captured[-1]
    assert depth1_kwargs["run_config"].model == definition_model
    return depth1_kwargs["context"], captured


# ---------------------------------------------------------------------------
# 1. Grandchild inherits the direct parent's effective model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grandchild_without_model_inherits_child_effective_model(tmp_path, monkeypatch):
    depth1_ctx, captured = await _spawn_depth1(tmp_path, monkeypatch)

    # The depth-1 context is spawn-capable (recursion enabled) and carries
    # the effective GPT configuration for its own run.
    assert depth1_ctx.is_subagent
    assert depth1_ctx.allow_recursive_subagents
    assert depth1_ctx.model_run_config.model_name == CHILD_MODEL

    await subtask.run_subtask_impl("grandchild task", agent_context=depth1_ctx, child_depth=2)

    depth2_kwargs = captured[-1]
    depth2_ctx = depth2_kwargs["context"]
    assert depth2_ctx.subagent_depth == 2
    # The unnamed grandchild must run on its direct parent's effective model
    # (GPT), not the root session's model (Kimi).
    assert depth2_kwargs["run_config"].model == CHILD_MODEL
    assert depth2_kwargs["run_config"].model_run_config.model_name == CHILD_MODEL


@pytest.mark.asyncio
async def test_grandchild_definition_model_wins_over_inherited_model(tmp_path, monkeypatch):
    depth1_ctx, captured = await _spawn_depth1(tmp_path, monkeypatch)

    await subtask.run_subtask_impl(
        "grandchild task",
        agent_context=depth1_ctx,
        agent_definition=_gpt_agent_definition(
            tmp_path, model=GRANDCHILD_DEFINITION_MODEL, name="glm-agent"
        ),
    )

    depth2_kwargs = captured[-1]
    assert depth2_kwargs["run_config"].model == GRANDCHILD_DEFINITION_MODEL


@pytest.mark.asyncio
async def test_configured_sub_agent_model_still_overrides_at_depth_2(tmp_path, monkeypatch):
    # conf.yaml sub_agent.llm_config keeps precedence at every level: the
    # grandchild runs on the configured model/provider, not the inherited GPT.
    depth1_ctx, captured = await _spawn_depth1(
        tmp_path, monkeypatch,
        conf_sub_llm=LLMConfig(model=CONFIGURED_MODEL, provider="alternate"),
    )

    await subtask.run_subtask_impl("grandchild task", agent_context=depth1_ctx, child_depth=2)

    depth2_kwargs = captured[-1]
    assert depth2_kwargs["run_config"].model == CONFIGURED_MODEL
    assert depth2_kwargs["run_config"].model_run_config.provider == "alternate"


# ---------------------------------------------------------------------------
# 2. Grandchild compaction follows the grandchild's effective model
# ---------------------------------------------------------------------------

def _install_compaction_overrides(monkeypatch, *, token_count, compact_model=None):
    if compact_model:
        monkeypatch.setenv("SIADA_COMPACT_MODEL", compact_model)
    else:
        monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    monkeypatch.setattr(compaction, "calculate_tokens", lambda *args, **kwargs: token_count)
    monkeypatch.setattr(compaction_strategy, "calculate_tokens", lambda *args, **kwargs: 100)
    completion = AsyncMock(return_value=object())
    monkeypatch.setattr(compaction_strategy, "one_shot_completion", completion)
    monkeypatch.setattr(
        compaction_strategy, "extract_response_text", lambda _: "<context>summary</context>"
    )
    return completion


async def _run_grandchild_with_compaction(tmp_path, monkeypatch, *, token_count,
                                          compact_model=None):
    depth1_ctx, captured = await _spawn_depth1(tmp_path, monkeypatch)
    completion = _install_compaction_overrides(
        monkeypatch, token_count=token_count, compact_model=compact_model
    )
    history = [{"role": "user", "content": f"synthetic message {i}"} for i in range(8)]
    monkeypatch.setattr(
        subtask.Runner, "run_streamed", _capture_runner(captured, invoke_filter=True,
                                                        filter_input=history)
    )

    await subtask.run_subtask_impl("grandchild task", agent_context=depth1_ctx, child_depth=2)
    return captured[-1], completion


@pytest.mark.asyncio
async def test_grandchild_compaction_uses_grandchild_model(tmp_path, monkeypatch):
    # gpt-6-luna window is 1,000,000 -> threshold 750,000; 800,000 triggers.
    depth2_kwargs, completion = await _run_grandchild_with_compaction(
        tmp_path, monkeypatch, token_count=800_000
    )

    assert depth2_kwargs["run_config"].model == CHILD_MODEL
    completion.assert_awaited_once()
    # The summary request must go to the grandchild's own model/provider,
    # not the root session's Kimi.
    assert completion.await_args.kwargs["model"] == CHILD_MODEL
    assert completion.await_args.kwargs["provider"] == "default"


@pytest.mark.asyncio
async def test_grandchild_compaction_respects_siada_compact_model(tmp_path, monkeypatch):
    depth2_kwargs, completion = await _run_grandchild_with_compaction(
        tmp_path, monkeypatch, token_count=800_000, compact_model=ROOT_MODEL
    )

    assert depth2_kwargs["run_config"].model == CHILD_MODEL
    completion.assert_awaited_once()
    # SIADA_COMPACT_MODEL overrides only the summary model; the grandchild
    # still runs (and counts context) on its own effective model.
    assert completion.await_args.kwargs["model"] == ROOT_MODEL
    assert completion.await_args.kwargs["provider"] == "default"


# ---------------------------------------------------------------------------
# 3. Non-recursive path is untouched
# ---------------------------------------------------------------------------

def test_clone_context_keeps_llm_config_only_under_recursion(tmp_path):
    root_ctx, _, root_llm = _make_root_context(tmp_path, recursive=True)

    clone = _clone_context_for_subagent(root_ctx, llm_config=root_llm)
    assert clone.session is root_ctx.session
    assert clone.subagent_llm_config is root_llm
    assert clone.model_run_config is root_llm

    non_recursive_ctx, _, non_recursive_llm = _make_root_context(tmp_path, recursive=False)
    plain_clone = _clone_context_for_subagent(non_recursive_ctx, llm_config=non_recursive_llm)
    assert plain_clone.session is None
    assert plain_clone.subagent_llm_config is None


def test_clone_context_llm_config_defaults_to_none(tmp_path):
    root_ctx, _, _ = _make_root_context(tmp_path, recursive=True)
    clone = _clone_context_for_subagent(root_ctx)
    assert clone.subagent_llm_config is None
    # Without an override the property keeps reading the root session config.
    assert clone.model_run_config.model_name == ROOT_MODEL
