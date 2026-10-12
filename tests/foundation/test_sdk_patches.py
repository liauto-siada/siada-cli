"""Tests for ``siada.foundation.sdk_patches``.

Covers serialized, retryable SDK warmup and the absence of private execution
or response-resolution patches in the startup entry point.
"""

import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from siada.foundation import sdk_patches


def test_configure_sdk_run_config_keeps_caller_settings_and_uses_public_recovery():
    from agents import RunConfig, ToolExecutionConfig

    original = RunConfig(
        tracing_disabled=True,
        workflow_name="existing-workflow",
        tool_execution=ToolExecutionConfig(),
        tool_not_found_behavior="raise",
    )
    configured = sdk_patches.configure_sdk_run_config(original)

    assert configured is not original
    assert configured.tool_not_found_behavior == "return_error_to_model"
    assert original.tool_not_found_behavior == "raise"
    assert configured.tracing_disabled is True
    assert configured.workflow_name == "existing-workflow"
    assert configured.tool_execution is original.tool_execution


def test_configure_sdk_run_config_creates_defaults_when_not_provided():
    configured = sdk_patches.configure_sdk_run_config()
    assert configured.tool_not_found_behavior == "return_error_to_model"
    assert configured.tool_execution is None


@pytest.fixture
def clean_patch_state(monkeypatch):
    """Reset only the warmup flag; SDK internals must remain untouched."""
    monkeypatch.setattr(sdk_patches, "_PATCHED", False)


def test_apply_patches_is_idempotent(clean_patch_state, monkeypatch):
    patch_mock = MagicMock()
    monkeypatch.setattr(
        "siada.foundation.sdk_patches.ensure_agents_imported", patch_mock
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

    monkeypatch.setattr("siada.foundation.sdk_patches.ensure_agents_imported", flaky)

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
        "siada.foundation.sdk_patches.ensure_agents_imported", slow_patch
    )

    threads = [
        threading.Thread(target=sdk_patches.apply_sdk_patches) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1


def test_patches_leave_response_and_function_execution_untouched(clean_patch_state):
    from agents.run_internal import tool_execution, turn_resolution
    from agents.run_internal.tool_actions import (
        ApplyPatchAction, ComputerAction, CustomToolAction, LocalShellAction, ShellAction,
    )

    response = turn_resolution.process_model_response
    executor = tool_execution._FunctionToolBatchExecutor
    body = executor._execute_single_tool_body
    invoke = executor._invoke_tool_and_run_post_invoke
    native_actions = [ApplyPatchAction, ComputerAction, CustomToolAction, LocalShellAction, ShellAction]
    native_executors = [action.execute.__func__ for action in native_actions]
    sdk_patches.apply_sdk_patches()
    assert turn_resolution.process_model_response is response
    assert executor._execute_single_tool_body is body
    assert executor._invoke_tool_and_run_post_invoke is invoke
    assert [action.execute.__func__ for action in native_actions] == native_executors


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
