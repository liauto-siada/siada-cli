"""Offline regression tests for API reconfiguration during an active turn."""

import collections
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.entrypoint.login import login_prompt
from siada.io import stdin_interrupt_monitor as monitor_module


@pytest.fixture
def wizard(monkeypatch):
    monitor = monitor_module.StdinInterruptMonitor()
    monitor._running = True
    monkeypatch.setattr(monitor_module, "_monitor", monitor)
    monkeypatch.setattr(monitor_module, "_agent_running", True)
    monkeypatch.setattr(monitor_module, "_pending_injections", collections.deque())
    monkeypatch.setattr(login_prompt, "_applied_api_key_config", None)
    monkeypatch.setenv("API_KEY", "synthetic-old-key")
    monkeypatch.setenv("BASE_URL", "https://old.example.test/v1")
    monkeypatch.setattr(
        "siada.provider.models_dev.get_providers_for_ui", lambda: [],
    )
    saved = Mock()
    monkeypatch.setattr(login_prompt, "_save_provider_config", saved)
    notifications = []
    replies = collections.deque()

    def send(message):
        notifications.append(message.method)
        if message.method == "ui/showLoginSelector":
            monitor._dispatch_or_enqueue([
                "<<<SIADA_MSG_START>>>\n",
                replies.popleft() + "\n",
                "<<<SIADA_MSG_END>>>\n",
            ])

    # Fail promptly if routing strands a reply, instead of hanging the test.
    read_line = monitor.readline

    def bounded_readline(timeout=0.1):
        line = read_line(timeout=0.01)
        if not line:
            raise EOFError("Login reply did not reach the wizard")
        return line

    monkeypatch.setattr(monitor, "readline", bounded_readline)
    io = SimpleNamespace(acp_adapter=SimpleNamespace(
        transport=SimpleNamespace(is_connected=True, send_sync=send),
    ))
    return io, replies, notifications, saved


def test_repeated_api_configuration_during_command_turn(wizard, caplog):
    io, replies, notifications, saved = wizard
    for provider, model in [("openai", "test-model"), ("kimi", "kimi-k3"), ("kimi", "kimi-k3")]:
        config = {
            "provider_id": provider,
            "model": model,
            "api_key": f"synthetic-{provider}-key",
            "base_url": "https://example.test/v1",
        }
        replies.append("__LOGIN_CHOICE__:3:" + json.dumps(config))

        assert login_prompt.reconfigure_acp(io) == f"api-key-user:{provider}"
        assert login_prompt.get_applied_api_key_config() == config
        assert not monitor_module.drain_pending_injections()
        assert notifications[-1] == "ui/loginSuccess"

    assert saved.call_count == 3
    assert "synthetic-openai-key" not in caplog.text
    assert "synthetic-kimi-key" not in caplog.text


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-pro"])
def test_deepseek_reconfiguration_saves_and_applies_selected_model(wizard, model):
    io, replies, notifications, saved = wizard
    config = {
        "provider_id": "deepseek",
        "model": model,
        "api_key": "synthetic-deepseek-key",
        "base_url": "https://api.deepseek.com/v1",
    }
    replies.append("__LOGIN_CHOICE__:3:" + json.dumps(config))

    assert login_prompt.reconfigure_acp(io) == "api-key-user:deepseek"
    saved.assert_called_once_with(
        "deepseek", "synthetic-deepseek-key", "https://api.deepseek.com/v1", model,
    )
    assert login_prompt.get_applied_api_key_config() == config
    assert notifications[-1] == "ui/loginSuccess"
    assert not monitor_module.drain_pending_injections()


@pytest.mark.parametrize("choice", ["cancel", "skip"])
def test_cancel_during_reconfiguration_reaches_wizard(wizard, choice):
    io, replies, notifications, saved = wizard
    replies.append(f"__LOGIN_CHOICE__:{choice}")

    assert login_prompt.reconfigure_acp(io) is None
    assert notifications == ["ui/showLoginSelector", "ui/loginDismiss"]
    assert not monitor_module.drain_pending_injections()
    saved.assert_not_called()