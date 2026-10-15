import asyncio
import logging
import multiprocessing
import json
from io import BytesIO
from types import SimpleNamespace

import pytest

from siada.foundation.context import context_dict_var, get_context_var, set_context_var, AGENT_NAME
from siada.foundation.log_context import log_fields, log_scope, logged_request, REQUEST_ID
from siada.foundation.logging import FileFormatter, SafeTimedRotatingFileHandler


@pytest.mark.asyncio
async def test_parallel_request_and_agent_scopes_restore_on_failure():
    token = context_dict_var.set({})
    try:
        @logged_request
        async def prompt(session_id, **_):
            with log_scope(agent="MemoryAgent", agent_run_id=session_id + "-run"):
                await asyncio.sleep(0)
                fields = log_fields()
                set_context_var(AGENT_NAME, "changed")
                return fields

        a, b = await asyncio.gather(
            prompt("a", _meta={"siadaLog": {"requestId": "request-a"}}),
            prompt("b", _meta={"siadaLog": {"requestId": "request-b"}}),
        )
        assert a == dict(sessionId="a", requestId="request-a", agent="MemoryAgent", agentRunId="a-run")
        assert b["sessionId"] == "b" and b["requestId"] == "request-b"
        assert all(value == "-" for value in log_fields().values())
        with pytest.raises(RuntimeError):
            with log_scope(request_id="failed", agent="CodeAgent"):
                raise RuntimeError("synthetic")
        assert get_context_var(REQUEST_ID) is None
    finally:
        context_dict_var.reset(token)


@pytest.mark.asyncio
async def test_sdk_agent_scope_and_stream_producer_inherit_context(monkeypatch):
    from siada.foundation.agent_logging import LoggingRunner, Runner

    async def run(**kwargs):
        await asyncio.sleep(0)
        return log_fields()

    monkeypatch.setattr(Runner, "run", run)
    # Match the SDK's synchronous creation of a producer task.
    monkeypatch.setattr(Runner, "run_streamed", lambda **kwargs: asyncio.create_task(run(**kwargs)))
    with log_scope(session_id="parent-session", request_id="turn", agent="CodeAgent"):
        a, b = await asyncio.gather(
            LoggingRunner.run(starting_agent=SimpleNamespace(name="MemoryAgent")),
            LoggingRunner.run(starting_agent=SimpleNamespace(name="Verifier")),
        )
        producer = LoggingRunner.run_streamed(starting_agent=SimpleNamespace(name="SubAgent"))
        assert log_fields()["agent"] == "CodeAgent"
        streamed = await producer
    assert a["agent"] == "MemoryAgent" and b["agent"] == "Verifier"
    assert a["agentRunId"] != b["agentRunId"]
    assert streamed["agent"] == "SubAgent"
    assert streamed["requestId"] == a["requestId"] == "turn"
    assert streamed["sessionId"] == "parent-session"


def test_file_formatter_tags_custom_message_types_and_interpolates():
    formatter = FileFormatter("%(message)s")
    record = logging.LogRecord("synthetic", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.msg_type = "OBSERVATION"
    with log_scope(session_id="s", request_id="r", agent="CodeAgent", agent_run_id="run"):
        text = formatter.format(record)
    assert "sessionId=s requestId=r agent=CodeAgent agentRunId=run" in text
    assert "hello world" in text
    assert f"pid={record.process}" in text


def test_stdio_metadata_preserves_stream_fields_and_does_not_mutate_message():
    from siada.io.acp.transport.stdio import StdioTransport

    output = BytesIO()
    transport = StdioTransport(stdout=SimpleNamespace(buffer=output))
    original = {
        "jsonrpc": "2.0", "method": "session/update",
        "params": {"metadata": {"streamStartId": "stream"}, "_meta": {"custom": "preserved"}},
    }
    message = SimpleNamespace(method="session/update", to_dict=lambda: original)
    with log_scope(session_id="s", request_id="r", agent="MemoryAgent", agent_run_id="run"):
        transport.send_sync(message)
    encoded = output.getvalue()
    assert encoded.startswith(b"\x1e")
    wire = json.loads(encoded[1:])
    assert wire["params"]["metadata"]["streamStartId"] == "stream"
    assert wire["params"]["_meta"]["custom"] == "preserved"
    assert wire["params"]["_meta"]["siadaLog"]["agentRunId"] == "run"
    assert original["params"]["_meta"] == {"custom": "preserved"}


def _write_logs(path, worker):
    handler = SafeTimedRotatingFileHandler(path, when="midnight", backupCount=100, maxBytes=512)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for index in range(40):
        record = logging.LogRecord("synthetic", logging.INFO, "", 1, f"worker-{worker}-{index}", (), None)
        handler.handle(record)
    handler.close()


def test_multiprocess_rotation_keeps_every_record(tmp_path):
    target = tmp_path / "synthetic.log"
    ctx = multiprocessing.get_context("spawn")
    workers = [ctx.Process(target=_write_logs, args=(str(target), index)) for index in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        if worker.is_alive():
            worker.terminate()
            worker.join()
            pytest.fail("Log writer did not terminate")
        assert worker.exitcode == 0
    lines = []
    for path in tmp_path.glob("synthetic.log*"):
        lines.extend(path.read_text().splitlines())
    expected = {f"worker-{worker}-{index}" for worker in range(3) for index in range(40)}
    assert set(lines) == expected
    assert len(lines) == len(expected)
    assert len(list(tmp_path.glob("synthetic.log*"))) > 1


def test_rotation_retention_is_bounded(tmp_path):
    target = tmp_path / "synthetic.log"
    handler = SafeTimedRotatingFileHandler(target, when="midnight", backupCount=3, maxBytes=32)
    try:
        for i in range(40):
            handler.handle(logging.LogRecord("test", 20, "", 1, f"record-{i}", (), None))
        assert len(list(tmp_path.glob("synthetic.log*"))) == 4
        assert "record-39" in target.read_text()
    finally:
        handler.close()


def test_rotation_errors_are_throttled_and_never_written_to_acp_stdout(tmp_path, monkeypatch, capsys):
    from concurrent_log_handler import ConcurrentTimedRotatingFileHandler

    handler = SafeTimedRotatingFileHandler(tmp_path / "synthetic.log", when="midnight")
    now = [100.0]
    monkeypatch.setattr("siada.foundation.logging.time.monotonic", lambda: now[0])
    def locked(_self):
        raise PermissionError("synthetic lock failure")
    monkeypatch.setattr(ConcurrentTimedRotatingFileHandler, "doRollover", locked)
    try:
        handler.doRollover()
        handler.doRollover()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.count("synthetic lock failure") == 1
        now[0] += 60
        handler.doRollover()
        assert capsys.readouterr().err.count("synthetic lock failure") == 1
    finally:
        handler.close()


def test_midnight_rollover_is_shared_by_two_writers(tmp_path, monkeypatch):
    target = tmp_path / "synthetic.log"
    first = SafeTimedRotatingFileHandler(target, when="midnight", backupCount=3)
    second = SafeTimedRotatingFileHandler(target, when="midnight", backupCount=3)
    try:
        before = logging.LogRecord("test", 20, "", 1, "before-midnight", (), None)
        first.handle(before)
        now = first.rolloverAt + 1
        monkeypatch.setattr(first, "_get_current_time", lambda: now)
        monkeypatch.setattr(second, "_get_current_time", lambda: now)
        first.handle(logging.LogRecord("test", 20, "", 1, "after-first", (), None))
        second.handle(logging.LogRecord("test", 20, "", 1, "after-second", (), None))
        assert "after-first" in target.read_text()
        assert "after-second" in target.read_text()
        backups = [path for path in tmp_path.glob("synthetic.log*") if path != target]
        assert len(backups) == 1
        assert "before-midnight" in backups[0].read_text()
    finally:
        first.close()
        second.close()


@pytest.mark.asyncio
async def test_periodic_memory_analysis_uses_exported_session_not_current_session(tmp_path, monkeypatch):
    from siada.agent_hub.proactive.scheduler import ProactiveScheduler
    from siada.services.memory import memory_agent, memory_review_agent

    seen = []
    async def fake_agent(*args, **kwargs):
        await asyncio.sleep(0)
        seen.append(log_fields())
        return {"success": True}

    monkeypatch.setattr(memory_agent, "analyze_and_update_memory", fake_agent)
    monkeypatch.setattr(memory_review_agent, "review_and_update_inline_memory", fake_agent)
    files = []
    for name in ("a", "b"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"# Session\n\n- **Session ID**: source-{name}\n\n## Conversation Summary\nsynthetic")
        files.append(path)
    with log_scope(session_id="foreground", request_id="foreground-request"):
        await asyncio.gather(*(ProactiveScheduler._analyze_session_file(None, path) for path in files))
        assert log_fields()["sessionId"] == "foreground"
    assert {fields["sessionId"] for fields in seen} == {"source-a", "source-b"}
    by_session = {}
    for fields in seen:
        by_session.setdefault(fields["sessionId"], set()).add(fields["requestId"])
    assert len(by_session["source-a"]) == len(by_session["source-b"]) == 1
    assert by_session["source-a"].isdisjoint(by_session["source-b"])
    assert all(fields["requestId"] != "foreground-request" for fields in seen)