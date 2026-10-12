"""Public-build tests for ``TokenUsageReporterProcessor``.

The processor used to upload per-call token/cost telemetry to a private
endpoint. In this build it must stay in the hook chain (``SiadaAgentHooks``
imports it and delegates every lifecycle callback to it) while reporting
nothing anywhere.
"""

import contextlib
import socket
from pathlib import Path

import pytest
from agents import AgentHooks

from siada.agent_hub.hooks.processors.token_usage_reporter_processor import (
    TokenUsageReporterProcessor,
)
from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks

REPO_ROOT = Path(__file__).resolve().parents[3]

# Callbacks ``SiadaAgentHooks`` delegates to every processor.
DELEGATED_CALLBACKS = (
    "on_start",
    "on_end",
    "on_agent_start",
    "on_agent_end",
    "on_llm_start",
    "on_llm_end",
    "on_tool_start",
    "on_tool_end",
)


@contextlib.contextmanager
def _no_network():
    """Fail the test if the processor opens a socket."""

    def _blocked(*args, **kwargs):
        raise AssertionError("token usage reporting attempted a network call")

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    socket.socket.connect = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo


def test_processor_declares_every_callback_the_composite_delegates():
    processor = TokenUsageReporterProcessor()

    missing = [name for name in DELEGATED_CALLBACKS if not callable(getattr(processor, name, None))]

    assert missing == []


def test_processor_does_not_override_the_llm_callbacks():
    """Inherited no-ops prove nothing is collected or uploaded per call."""
    for name in ("on_start", "on_end", "on_llm_start", "on_llm_end", "on_tool_start", "on_tool_end"):
        assert getattr(TokenUsageReporterProcessor, name) is getattr(AgentHooks, name), name


def test_processor_module_references_no_endpoint_or_private_tree():
    source = (
        REPO_ROOT / "siada/agent_hub/hooks/processors/token_usage_reporter_processor.py"
    ).read_text(encoding="utf-8")

    assert "http://" not in source
    assert "https://" not in source
    assert "siada.internal" not in source
    assert "requests" not in source


@pytest.mark.asyncio
async def test_composite_hook_chain_runs_without_reporting_anything():
    hooks = SiadaAgentHooks(processors=[TokenUsageReporterProcessor()])

    with _no_network():
        await hooks.on_start(None, None)
        await hooks.on_llm_start(None, None, "system", [])
        await hooks.on_llm_end(None, None, None)
        await hooks.on_tool_start(None, None, None)
        await hooks.on_tool_end(None, None, None, "result")
        await hooks.on_end(None, None, "output")


@pytest.mark.asyncio
async def test_default_hook_chain_still_contains_the_processor():
    hooks = SiadaAgentHooks()

    assert any(
        isinstance(processor, TokenUsageReporterProcessor) for processor in hooks.processors
    )

    with _no_network():
        await hooks.on_start(None, None)
        await hooks.on_end(None, None, "output")