"""Offline installed-proxy verification, enabled with SIADA_TEST_PROXY_ENTRY."""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
from pathlib import Path

import pytest

from siada.browser_addon import manager, paths


_CLIENT = """
import assert from 'node:assert/strict';
const ws = new WebSocket(process.argv[1]);
const timeout = setTimeout(() => { throw new Error('synthetic client timeout'); }, 15000);
let updates = 0;
ws.addEventListener('open', () => ws.send(JSON.stringify({ type: 'connect' })));
ws.addEventListener('error', () => { throw new Error('synthetic websocket failure'); });
ws.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  const send = (type, payload) => ws.send(JSON.stringify({ type, payload }));
  if (message.type === 'status' && message.payload.connected) {
    send('new_session', { cwd: process.argv[2] });
  } else if (message.type === 'session_created') {
    send('prompt', { content: [{ type: 'text', text: 'logging-stream' }] });
  } else if (message.type === 'session_update') {
    updates++;
  } else if (message.type === 'error') {
    throw new Error(message.payload.message);
  } else if (message.type === 'prompt_complete') {
    assert.equal(message.payload.stopReason, 'end_turn');
    assert.equal(updates, 1000);
    console.log('PASS: received all 1000 stream updates');
    clearTimeout(timeout);
    ws.close();
  }
});
"""


@pytest.mark.skipif(not os.environ.get("SIADA_TEST_PROXY_ENTRY"), reason="requires an explicitly selected built proxy")
@pytest.mark.parametrize("debug", [False, True], ids=["info", "debug"])
def test_installed_managed_proxy_stream_logging(tmp_path, monkeypatch, debug):
    entry = Path(os.environ["SIADA_TEST_PROXY_ENTRY"]).resolve()
    assert entry.is_file()
    node = paths.node_binary()
    fixture = Path(__file__).resolve().parents[3] / "chrome-acp/packages/proxy-server/test/fixtures/fake-agent.mjs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = tmp_path / "logs"
    monkeypatch.setenv("SIADA_BROWSER_HOME", str(tmp_path / "browser"))
    monkeypatch.setenv("SIADA_CLI_LOG_DIR", str(root))
    monkeypatch.delenv("SIADA_PROXY_LOG_DIR", raising=False)
    monkeypatch.setattr(paths, "proxy_entry", lambda: entry)
    command = [node, str(entry), "--host", "127.0.0.1", "--port", str(port)]
    if debug:
        command.append("--debug")
    command += [node, "--", str(fixture)]
    monkeypatch.setenv("SIADA_BROWSER_PROXY_CMD", shlex.join(command))
    state = manager.init_state(port)
    try:
        assert manager.start() == "started"
        client = subprocess.run(
            [node, "--input-type=module", "-e", _CLIENT,
             f"ws://127.0.0.1:{port}/ws?token={state['token']}", str(tmp_path)],
            capture_output=True, text=True, timeout=20,
        )
        assert client.returncode == 0, client.stderr
        assert "PASS: received all 1000 stream updates" in client.stdout
    finally:
        if (paths.browser_home() / "proxy.pid").exists():
            manager.stop()
    runtime = list((root / "proxy").glob("acp-proxy-*.log"))
    runtime = [file for file in runtime if file.name != "acp-proxy-launch.log"]
    assert len(runtime) == 1
    text = runtime[0].read_text()
    assert state["token"] not in text
    records = [json.loads(line) for line in text.splitlines()]
    completed = [record for record in records if record["msg"] == "Prompt completed"]
    assert len(completed) == 1
    assert completed[0]["sessionId"] == "fake-session"
    assert completed[0]["requestId"] != "-"
    assert not any(record["level"] >= 50 for record in records)
    chunks = [record for record in records if record["msg"] == "Agent session update"]
    if debug:
        assert len(chunks) == 1000
        assert all(record["requestId"] == completed[0]["requestId"] for record in chunks)
    else:
        assert chunks == []
        assert len(records) < 30
        assert not any(record["level"] < 30 for record in records)
    assert paths.log_path().stat().st_size == 0