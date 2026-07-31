from types import SimpleNamespace

from siada.agent_hub.proactive.ipc_server import (
    _handle_lark_status,
    send_lark_message_direct,
)
from siada.tools.lark.lark_tools import get_available_proactive_lark_tools


class DummyLarkController:
    platform_name = "lark"

    def __init__(self, running: bool):
        self._running = running
        self._mode = "direct"

    @property
    def is_running(self) -> bool:
        return self._running


class DummyWeComController:
    platform_name = "wecom"

    def __init__(self, running: bool):
        self._running = running

    @property
    def is_running(self) -> bool:
        return self._running

    async def enqueue_ipc_message(self, **kwargs):
        return {"sent": True}


def test_handle_lark_status_only_reports_lark_controllers():
    daemon = SimpleNamespace(
        im_controllers=[
            DummyWeComController(running=True),
            DummyLarkController(running=False),
        ]
    )
    server = SimpleNamespace(daemon=daemon)

    result = _handle_lark_status({}, server)

    assert result["active"] is False
    assert len(result["controllers"]) == 1
    assert result["controllers"][0]["class"] == "DummyLarkController"
    assert result["controllers"][0]["running"] is False


def test_send_lark_message_direct_ignores_non_lark_controller():
    daemon = SimpleNamespace(
        im_controllers=[DummyWeComController(running=True)],
        _im_loops=[SimpleNamespace(is_closed=lambda: False)],
    )

    result = send_lark_message_direct(daemon=daemon, content="hello")

    assert result == {"sent": False, "reason": "no active LarkController available"}


def test_get_available_proactive_lark_tools_uses_daemon_initialization(monkeypatch):
    monkeypatch.setattr("siada.tools.lark.lark_tools.is_lark_active", lambda: False)
    monkeypatch.setattr(
        "siada.tools.lark.lark_tools.has_initialized_daemon_lark_controller",
        lambda daemon=None: True,
    )

    tools = get_available_proactive_lark_tools()

    assert [tool.name for tool in tools] == ["send_daily_summary_to_lark"]