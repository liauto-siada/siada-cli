"""The legacy ACP adapter is where an agent waits on the human.

An interactive input request (password, confirmation) means the turn is parked
until the user answers, which is exactly what Herdr surfaces as a blocked pane.
The cancel notification ends that wait, so the pane goes back to `working`
until the agent run itself reports otherwise.
"""

from unittest.mock import MagicMock

import pytest

from siada.foundation import herdr_reporter
from siada.io.acp import legacy_adapter as legacy_adapter_module
from siada.io.acp.legacy_adapter import LegacyACPAdapter


@pytest.fixture
def reports(monkeypatch):
    captured = []

    def _capture(state, message=None, session_id=None):
        captured.append((state, message))

    monkeypatch.setattr(
        legacy_adapter_module.herdr_reporter, "report_state", _capture
    )
    return captured


def test_interactive_input_request_reports_blocked(reports):
    adapter = LegacyACPAdapter(acp_enabled=True, transport=MagicMock())

    adapter.interactive_input_request(
        "Password:", input_type="password", is_password=True
    )

    assert reports == [(herdr_reporter.STATE_BLOCKED, "Password:")]


def test_interactive_input_cancel_reports_working(reports):
    adapter = LegacyACPAdapter(acp_enabled=True, transport=MagicMock())

    adapter.interactive_input_cancel(reason="timeout")

    assert reports == [(herdr_reporter.STATE_WORKING, None)]


def test_non_acp_mode_still_reports_the_wait(reports):
    """Without ACP the same wait happens on the terminal itself."""
    adapter = LegacyACPAdapter(acp_enabled=False, transport=MagicMock())

    adapter.interactive_input_request("Continue?")

    assert reports == [(herdr_reporter.STATE_BLOCKED, "Continue?")]
