"""Browser login runs the CLI wizard without a terminal or exposing keys."""
import io
import json
import pytest
from types import SimpleNamespace

from siada.entrypoint import browser_login
from siada.entrypoint.login import login_prompt


def test_browser_login_retries_with_cli_protocol(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(
        '{"choice":"3","payload":{"api_key":"synthetic"}}\n'
        '{"choice":"3","payload":{"api_key":"corrected"}}\n'
    ))
    reads = []

    def wizard(frontend):
        raw = login_prompt._read_acp_stdin_message()
        reads.append(raw)
        frontend.acp_adapter.transport.send_sync(SimpleNamespace(
            method="ui/loginError" if len(reads) == 1 else "ui/loginSuccess",
            params={"error": "Try again"} if len(reads) == 1 else {},
        ))
        return None if len(reads) == 1 else "configured"

    monkeypatch.setattr(login_prompt, "_ensure_logged_in_acp", wizard)
    assert browser_login.main() == 0
    output = capsys.readouterr().out
    assert "synthetic" not in output and "corrected" not in output
    assert reads[0].startswith("__LOGIN_CHOICE__:3:")
    assert [json.loads(line)["method"] for line in output.splitlines()][0] == "ui/loginError"


def test_browser_login_eof_exits_without_spin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr(login_prompt, "_ensure_logged_in_acp", lambda _io: login_prompt._read_acp_stdin_message())
    assert browser_login.main() == 0


def test_reconfigure_skips_existing_login_fast_path(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr(login_prompt, "_ensure_logged_in_acp", lambda _io: pytest.fail("Fast path must not run"))
    monkeypatch.setattr(login_prompt, "reconfigure_acp", lambda _io: login_prompt._read_acp_stdin_message())
    assert browser_login.main(reconfigure=True) == 0