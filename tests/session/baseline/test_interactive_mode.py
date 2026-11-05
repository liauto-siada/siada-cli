"""Session runtime configuration owns mode, including cached context reuse."""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from siada.services.siada_runner import SiadaRunner


@pytest.mark.asyncio
@pytest.mark.parametrize("argv, interactive", [
    (["--prompt=synthetic task"], False),
    (["-p=synthetic task"], False),
    (["--prompt", "synthetic task"], False),
    (["-p", "synthetic task"], False),
    (["--", "--prompt"], True),
    (["--", "-p"], True),
    (["synthetic positional task"], True),
])
async def test_session_mode_wins_over_process_arguments(baseline, monkeypatch, argv, interactive):
    monkeypatch.setattr(sys, "argv", ["siada-cli", *argv])
    session = baseline.session("mode")
    session.siada_config.interactive = interactive
    context = baseline.context(session)
    context.interactive_mode = not interactive
    await SiadaRunner._prepare_context_for_run(context, session)
    assert context.interactive_mode is interactive


@pytest.mark.asyncio
async def test_cached_context_mode_is_refreshed_each_run(baseline, monkeypatch):
    session = baseline.session("cached-mode")
    context = baseline.context(session)
    agent = SimpleNamespace(name="mode-agent")
    build = AsyncMock(return_value=context)
    monkeypatch.setattr(SiadaRunner, "_build_agent_context", build)
    for interactive in [False, True, False]:
        session.siada_config.interactive = interactive
        cached = await SiadaRunner.get_context(agent, session, session.siada_config.workspace)
        assert cached is context
        await SiadaRunner._prepare_context_for_run(cached, session)
        assert cached.interactive_mode is interactive
    build.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("module_name, class_name", [
    ("siada.agent_hub.coder.code_gen_agent", "CodeGenAgent"),
    ("siada.agent_hub.proactive.proactive_agent", "ProactiveAgent"),
])
@pytest.mark.parametrize("interactive", [False, True])
async def test_builtin_agent_contexts_bind_session_mode(baseline, monkeypatch, module_name, class_name, interactive):
    monkeypatch.setattr(sys, "argv", ["siada-cli", "--prompt=synthetic task"])
    agent_type = getattr(importlib.import_module(module_name), class_name)
    agent = agent_type(name="synthetic-mode", tools=[], hooks=None)
    context = await agent.get_context()
    session = baseline.session("builtin-mode")
    session.siada_config.interactive = interactive
    await SiadaRunner._prepare_context_for_run(context, session)
    assert context.interactive_mode is interactive
