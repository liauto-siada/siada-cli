"""Per-agent ``model`` override for sub-agent runs.

A user-defined agent definition (``.agents/agents/*.md`` ``model`` field) must
take precedence over the conf.yaml ``sub_agent.llm_config`` model, keep the
provider this spawn would use anyway, and degrade to the configured model
(with a warning) when the name is not a known model.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from siada.config.config_loader import Config, LLMConfig, SubAgentConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_run_config import ModelRunConfig
from siada.provider import provider_factory
from siada.services.sub_agent_run_config import (
    _model_override_llm_config,
    build_sub_agent_run_config,
    resolve_sub_agent_llm_config,
)
from siada.session.session_models import RunningSession


def _llm_config(
    model: str = "claude-sonnet-5", provider: str = "default"
) -> ModelRunConfig:
    llm_config = ModelRunConfig(model)
    llm_config.provider = provider
    return llm_config


def _context(llm_config) -> CodeAgentContext:
    session = MagicMock(spec=RunningSession)
    session.session_id = "sub-agent-config-test"
    session.siada_config = MagicMock()
    session.siada_config.llm_config = llm_config
    session.siada_config.tracing_disabled = True
    return CodeAgentContext(root_dir="/tmp", session=session)


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    # Keep routing assertions independent of credentials and provider imports.
    providers = {"alternate": MagicMock(), "default": MagicMock()}
    monkeypatch.setattr(provider_factory, "provider_map", providers)
    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    return providers


def _build(llm_config, model=None, effort=None):
    # Pin the resolved sub-agent config to the parent's, so the assertion does
    # not depend on the developer's own conf.yaml `sub_agent.llm_config`.
    with patch(
        "siada.services.sub_agent_run_config.resolve_sub_agent_llm_config",
        return_value=llm_config,
    ):
        return build_sub_agent_run_config(
            _context(llm_config), effort=effort, model=model
        )


class TestModelOverrideHelper:
    def test_override_keeps_the_provider_of_the_base_config(self):
        override = _model_override_llm_config("gpt-6-luna", _llm_config(provider="li"))

        assert override.model_name == "gpt-6-luna"
        assert override.provider == "li"

    def test_unknown_model_returns_none(self):
        assert _model_override_llm_config("gpt-5.6-luna", _llm_config()) is None


class TestBuildSubAgentRunConfigModelOverride:
    def test_model_override_wins_over_the_resolved_config(self):
        run_config = _build(_llm_config(), model="gpt-6-luna")

        assert run_config.model == "gpt-6-luna"

    def test_override_keeps_the_gateway_provider(self):
        with patch("siada.services.sub_agent_run_config.get_provider") as get_provider:
            _build(_llm_config(provider="li"), model="gpt-6-luna")

        get_provider.assert_called_once_with("li")

    def test_unknown_model_is_ignored_and_the_configured_model_kept(self):
        run_config = _build(_llm_config(), model="gpt-5.6-luna")

        assert run_config.model == "claude-sonnet-5"

    def test_same_model_does_not_rebuild_the_config(self):
        with patch(
            "siada.services.sub_agent_run_config._model_override_llm_config"
        ) as override:
            run_config = _build(_llm_config(), model="claude-sonnet-5")

        override.assert_not_called()
        assert run_config.model == "claude-sonnet-5"

    def test_effort_is_mapped_against_the_overridden_model(self):
        run_config = _build(_llm_config(), model="gpt-6-luna", effort="medium")

        # GPT-5/6 rides the native Responses API: the effort lands in
        # extra_body["reasoning"] (Claude would use output_config instead).
        assert run_config.model_settings.extra_body["reasoning"] == {"effort": "medium"}

    def test_no_override_keeps_the_previous_behaviour(self):
        run_config = _build(_llm_config())

        assert run_config.model == "claude-sonnet-5"


@pytest.mark.parametrize(
    "configured_provider, active_provider, parent_provider, expected_provider",
    [
        (None, None, "gateway", "gateway"),
        ("missing-provider", "gateway", "default", "gateway"),
        ("missing-provider", None, "gateway", "gateway"),
        ("gateway", None, "default", "gateway"),
        (None, None, None, "default"),
        ("missing-provider", None, "missing-parent", "default"),
    ],
)
def test_sub_agent_provider_resolution(
    monkeypatch, configured_provider, active_provider, parent_provider,
    expected_provider,
):
    parent = _llm_config(provider=parent_provider)
    context = _context(parent)
    context.provider = active_provider
    conf = Config(
        sub_agent_config=SubAgentConfig(
            llm_config=LLMConfig(
                model="gpt-6-luna", provider=configured_provider
            )
        )
    )
    providers = {"default": MagicMock(), "gateway": MagicMock()}
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", providers)

    with patch("siada.config.config_loader.load_conf", return_value=conf):
        resolved = resolve_sub_agent_llm_config(context)
        run_config = build_sub_agent_run_config(context)

    assert resolved.provider == (configured_provider or parent_provider)
    assert run_config.model == "gpt-6-luna"
    assert run_config.model_provider.base_provider is providers[expected_provider]
    assert parent.model_name == "claude-sonnet-5"
    assert parent.provider == parent_provider


def test_sub_agent_reports_empty_registry(monkeypatch):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {})

    with pytest.raises(ValueError, match="No model providers found or registered"):
        _build(_llm_config())


@pytest.mark.asyncio
async def test_run_subtask_returns_hello_with_model_only_override(monkeypatch):
    from siada.tools.agent.run_subtask import run_subtask_impl

    context = _context(_llm_config())
    conf = Config(
        sub_agent_config=SubAgentConfig(
            llm_config=LLMConfig(model="gpt-6-luna")
        )
    )
    provider = MagicMock()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": provider})

    async def stream_events():
        return
        yield

    result = MagicMock()
    result.stream_events = stream_events
    result.final_output = "hello"
    with patch("siada.config.config_loader.load_conf", return_value=conf), patch(
        "siada.tools.agent.run_subtask.SubTaskAgent", return_value=MagicMock()
    ), patch(
        "siada.tools.agent.run_subtask.Runner.run_streamed", return_value=result
    ) as run_streamed:
        output = await run_subtask_impl(
            instruction="Reply with exactly hello.",
            agent_context=context,
        )

    assert output == "hello"
    run_config = run_streamed.call_args.kwargs["run_config"]
    assert run_config.model == "gpt-6-luna"
    assert run_config.model_provider.base_provider is provider


class TestSubAgentProviderInheritance:
    @pytest.mark.parametrize("provider", [None, ""])
    def test_model_only_override_inherits_parent_provider(
        self, provider, isolated_providers
    ):
        parent = _llm_config(provider="default")
        context = _context(parent)
        conf = SimpleNamespace(
            sub_agent_config=SubAgentConfig(
                llm_config=LLMConfig(model="gpt-6-luna", provider=provider)
            )
        )
        with patch("siada.config.config_loader.load_conf", return_value=conf):
            effective = resolve_sub_agent_llm_config(context)
            run_config = build_sub_agent_run_config(context)

        assert effective.provider == "default"
        assert run_config.model == "gpt-6-luna"
        assert run_config.model_provider.base_provider is isolated_providers["default"]
        assert parent.model_name == "claude-sonnet-5"
        assert parent.provider == "default"

    def test_explicit_sub_agent_provider_is_preserved(self, isolated_providers):
        context = _context(_llm_config(provider="default"))
        conf = SimpleNamespace(
            sub_agent_config=SubAgentConfig(
                llm_config=LLMConfig(model="gpt-6-luna", provider="alternate")
            )
        )
        with patch("siada.config.config_loader.load_conf", return_value=conf):
            run_config = build_sub_agent_run_config(context)

        assert run_config.model_provider.base_provider is isolated_providers["alternate"]
