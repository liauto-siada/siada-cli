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
            response = replies.popleft()
            if callable(response):
                response = response(message.params["requestId"])
            for reply in response if isinstance(response, list) else [response]:
                monitor._dispatch_or_enqueue([
                    "<<<SIADA_MSG_START>>>\n",
                    reply + "\n",
                    "<<<SIADA_MSG_END>>>\n",
                ])

    # Fail promptly if routing strands a reply, instead of hanging the test.
    read_line = monitor.read_login_reply_line

    def bounded_readline(timeout=0.1):
        line = read_line(timeout=0.01)
        if not line:
            raise EOFError("Login reply did not reach the wizard")
        return line

    monkeypatch.setattr(monitor, "read_login_reply_line", bounded_readline)
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


@pytest.mark.parametrize("first_choice", ["submit", "cancel"])
def test_only_one_reply_is_consumed_per_configuration(wizard, first_choice):
    io, replies, notifications, saved = wizard
    config = {
        "provider_id": "kimi",
        "model": "kimi-k3",
        "api_key": "synthetic-kimi-key",
        "base_url": "https://example.test/v1",
    }
    submit = "__LOGIN_CHOICE__:3:" + json.dumps(config)
    cancel = "__LOGIN_CHOICE__:cancel"
    replies.append([submit, cancel, submit] if first_choice == "submit" else [cancel, submit])

    expected = "api-key-user:kimi" if first_choice == "submit" else None
    assert login_prompt.reconfigure_acp(io) == expected
    assert monitor_module.get_stdin_monitor()._queue.empty()
    assert monitor_module.get_stdin_monitor()._login_reply_queue.empty()
    assert not monitor_module.drain_pending_injections()

    replies.append(submit)
    assert login_prompt.reconfigure_acp(io) == "api-key-user:kimi"
    assert notifications[-1] == "ui/loginSuccess"
    assert saved.call_count == (2 if first_choice == "submit" else 1)


def test_scoped_replies_reject_delayed_cancellation_from_previous_selector(wizard):
    io, replies, notifications, saved = wizard
    request_ids = []
    config = {
        "provider_id": "kimi",
        "model": "kimi-k3",
        "api_key": "synthetic-kimi-key",
        "base_url": "https://example.test/v1",
    }

    def respond(request_id):
        responses = []
        if request_ids:
            responses.append("__LOGIN_CHOICE__:cancel:" + json.dumps({
                "requestId": request_ids[-1], "payload": None,
            }))
        request_ids.append(request_id)
        responses.append("__LOGIN_CHOICE__:3:" + json.dumps({
            "requestId": request_id, "payload": json.dumps(config),
        }))
        return responses

    for _ in range(3):
        replies.append(respond)
        assert login_prompt.reconfigure_acp(io) == "api-key-user:kimi"
        assert monitor_module.get_stdin_monitor()._queue.empty()
        assert monitor_module.get_stdin_monitor()._login_reply_queue.empty()
        assert login_prompt.get_applied_api_key_config() == config
        assert notifications[-1] == "ui/loginSuccess"
    assert len(set(request_ids)) == 3
    assert saved.call_count == 3


def test_failed_selector_notification_closes_reply_window(wizard):
    io, _, _, _ = wizard
    io.acp_adapter.transport.send_sync = Mock(side_effect=OSError("synthetic write failure"))
    login_prompt._send_acp_notification(io, "ui/showLoginSelector", {})
    monitor = monitor_module.get_stdin_monitor()
    monitor._dispatch_or_enqueue([
        "<<<SIADA_MSG_START>>>\n", "__LOGIN_CHOICE__:cancel\n", "<<<SIADA_MSG_END>>>\n",
    ])
    assert monitor._queue.empty()


def test_configuration_does_not_consume_an_ordinary_queued_message(wizard):
    io, replies, _, saved = wizard
    monitor = monitor_module.get_stdin_monitor()
    ordinary = [
        "<<<SIADA_MSG_START>>>\n", "ordinary user message\n", "<<<SIADA_MSG_END>>>\n",
    ]
    for line in ordinary:
        monitor._queue.put(line)
    replies.append("__LOGIN_CHOICE__:cancel")
    assert login_prompt.reconfigure_acp(io) is None
    assert [monitor.readline() for _ in ordinary] == ordinary
    saved.assert_not_called()