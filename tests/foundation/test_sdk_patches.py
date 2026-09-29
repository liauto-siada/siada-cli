"""Tests for ``siada.foundation.sdk_patches``.

Covers the startup race fixed for openai-agents 0.22.x: the patch runs in a
background warmup thread, and importing the ``agents`` *package root* there
(``from agents import FunctionTool``) can observe a partially initialized
``agents.items`` — 0.22.x's ``__init__`` chain (sandbox → run_config →
guardrail → items → tool) widened that window. The patch must therefore (a)
serialize on a lock, (b) wait for the package import, and (c) import from
concrete submodules.
"""

import sys
import threading
import time
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from siada.foundation import sdk_patches


@pytest.fixture
def clean_patch_state(monkeypatch):
    """Restore global flags and the patched SDK function after each test."""
    from agents.run_internal import turn_resolution

    original = turn_resolution.process_model_response
    monkeypatch.setattr(sdk_patches, "_PATCHED", False)
    yield
    monkeypatch.setattr(turn_resolution, "process_model_response", original)


def test_apply_patches_is_idempotent(clean_patch_state, monkeypatch):
    patch_mock = MagicMock()
    monkeypatch.setattr(
        sdk_patches, "_patch_unknown_tool_to_synthetic_stub", patch_mock
    )

    sdk_patches.apply_sdk_patches()
    sdk_patches.apply_sdk_patches()

    assert patch_mock.call_count == 1
    assert sdk_patches._PATCHED is True


def test_apply_patches_retries_after_transient_failure(
    clean_patch_state, monkeypatch
):
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise ImportError(
                "cannot import name 'TResponseInputItem' from partially "
                "initialized module 'agents.items'"
            )

    monkeypatch.setattr(sdk_patches, "_patch_unknown_tool_to_synthetic_stub", flaky)

    sdk_patches.apply_sdk_patches()
    assert sdk_patches._PATCHED is False  # failure must stay retryable

    sdk_patches.apply_sdk_patches()
    assert sdk_patches._PATCHED is True
    assert len(attempts) == 2


def test_concurrent_apply_runs_patch_once(clean_patch_state, monkeypatch):
    calls = []

    def slow_patch():
        calls.append(1)
        time.sleep(0.05)

    monkeypatch.setattr(
        sdk_patches, "_patch_unknown_tool_to_synthetic_stub", slow_patch
    )

    threads = [
        threading.Thread(target=sdk_patches.apply_sdk_patches) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1


def test_patch_tolerates_partially_initialized_package(
    clean_patch_state, monkeypatch
):
    """Regression: the patch must not read ``FunctionTool`` off the package root.

    A partially initialized ``agents`` package (what the racing warmup thread
    observes) has no such attribute; importing the concrete submodule instead
    keeps the patch working.
    """
    import agents

    partial_package = ModuleType("agents")
    partial_package.__path__ = list(agents.__path__)
    monkeypatch.setitem(sys.modules, "agents", partial_package)

    sdk_patches._patch_unknown_tool_to_synthetic_stub()  # must not raise


def test_ensure_agents_imported_is_idempotent(monkeypatch):
    monkeypatch.setattr(sdk_patches, "_AGENTS_IMPORTED", False)

    sdk_patches.ensure_agents_imported()
    sdk_patches.ensure_agents_imported()

    assert sdk_patches._AGENTS_IMPORTED is True
    assert "agents" in sys.modules


def test_ensure_agents_imported_serializes_threads(monkeypatch):
    monkeypatch.setattr(sdk_patches, "_AGENTS_IMPORTED", False)
    errors = []

    def worker():
        try:
            sdk_patches.ensure_agents_imported()
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sdk_patches._AGENTS_IMPORTED is True


def test_warmup_handshake_helpers(monkeypatch):
    monkeypatch.setattr(sdk_patches, "_AGENTS_WARMUP_STARTED", threading.Event())
    monkeypatch.setattr(sdk_patches, "_AGENTS_READY", threading.Event())

    assert sdk_patches.agents_warmup_active() is False  # nothing started yet

    sdk_patches.begin_agents_warmup()
    assert sdk_patches.agents_warmup_active() is True
    assert sdk_patches.wait_agents_ready(timeout=0.05) is False  # still pending

    sdk_patches.mark_agents_ready()
    assert sdk_patches.agents_warmup_active() is False
    assert sdk_patches.wait_agents_ready(timeout=0.05) is True


def test_wait_agents_ready_wakes_up_on_mark(monkeypatch):
    monkeypatch.setattr(sdk_patches, "_AGENTS_WARMUP_STARTED", threading.Event())
    monkeypatch.setattr(sdk_patches, "_AGENTS_READY", threading.Event())
    sdk_patches.begin_agents_warmup()

    def mark_later():
        time.sleep(0.05)
        sdk_patches.mark_agents_ready()

    thread = threading.Thread(target=mark_later)
    thread.start()
    try:
        assert sdk_patches.wait_agents_ready(timeout=5.0) is True
    finally:
        thread.join()