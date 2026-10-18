"""Exercise Windows storage branches with strict flush and replace guards.

This is not a substitute for native Win32 locking and sharing tests.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.agent_hub.context_filter import request_token_estimator as estimator
from siada.services import session_runtime_state as state
from siada.services import session_storage as storage
from siada.support.resume_service import ResumeService
from siada.support.usage_utils import serialize_usage
from tests.session.baseline.test_default_context_cutover import run_default


@pytest.fixture
def windows_storage(monkeypatch):
    """Patch only storage's OS facade; keep native pathlib and file locking."""
    opened = []
    streams = {}
    flushed = []
    replaced = []
    path_open = Path.open
    fdopen = os.fdopen
    fsync = os.fsync
    replace = os.replace

    def track(stream):
        opened.append(stream)
        streams[stream.fileno()] = stream
        return stream

    def open_path(path, *args, **kwargs):
        return track(path_open(path, *args, **kwargs))

    def open_descriptor(*args, **kwargs):
        return track(fdopen(*args, **kwargs))

    def flush(fd):
        stream = streams[fd]
        assert not stream.closed and stream.writable(), "Windows fsync requires a writable handle"
        flushed.append(stream.name)
        return fsync(fd)

    def replace_closed(source, target):
        assert all(stream.closed for stream in opened), "Close file handles before Windows replacement"
        replaced.append(target)
        return replace(source, target)

    directory_open = Mock(side_effect=AssertionError("Windows cannot fsync directory handles"))
    facade = SimpleNamespace(
        name="nt", open=directory_open, fsync=flush, fdopen=open_descriptor, replace=replace_closed,
    )
    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(storage, "os", facade)
    yield SimpleNamespace(os=facade, flushed=flushed, replaced=replaced, streams=streams)
    directory_open.assert_not_called()
    assert all(stream.closed for stream in opened)


@pytest.mark.parametrize("fail", [False, True])
def test_windows_transaction_commits_or_rolls_back_utf8_pair(tmp_path, windows_storage, fail):
    folder = tmp_path / "synthetic 会话 storage"
    folder.mkdir()
    context_file = folder / "api_message.json"
    state_file = folder / "runtime_state.json"
    storage.write_json(context_file, {"value": "synthetic 原始 context"})
    storage.write_json(state_file, {"value": "synthetic 原始 usage"})
    before = {path: path.read_bytes() for path in (context_file, state_file)}

    def commit():
        with storage.storage_transaction(folder, ("api_message.json", "runtime_state.json")):
            storage.write_json(context_file, {"value": "synthetic 更新 context"})
            with storage.storage_transaction(folder, ("runtime_state.json",)):
                storage.write_json(state_file, {"value": "synthetic 更新 usage"})
            if fail:
                raise OSError("synthetic commit failure")

    if fail:
        with pytest.raises(OSError, match="synthetic commit failure"):
            commit()
        assert {path: path.read_bytes() for path in before} == before
    else:
        commit()
        assert all(path.read_bytes() != content for path, content in before.items())
        assert str(context_file) in windows_storage.flushed
        assert str(state_file) in windows_storage.flushed
    assert not (folder / ".storage-transaction.json").exists()
    assert not list(folder.glob("*.tmp"))


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("compacted", [False, True])
async def test_windows_response_anchor_and_resume_keep_delta_budget(
    baseline, monkeypatch, windows_storage, stream, compacted,
):
    workspace = baseline.workspace("synthetic 项目 with spaces")
    original = baseline.session("original", workspace=workspace)
    counter = Mock(side_effect=[200, 10, 25])
    monkeypatch.setattr(estimator, "calculate_tokens", counter)
    baseline.compact_at = 1 if compacted else None
    usage = baseline.usage(900, 100)
    first = baseline.model(original, [[baseline.text("synthetic 回复", "first")]], usages=[usage])
    await run_default(baseline, original, first, stream=stream, input="synthetic 输入")
    saved = state.load_state(original.openai_session.session_folder, original.session_id)
    assert saved["usage"] == serialize_usage(usage)
    assert saved["context_token_baseline"] == original.state.context_token_baseline.to_dict()
    assert original.state.context_token_baseline.context_tokens == usage.total_tokens
    baseline.compact_at = None

    fresh = baseline.session("fresh", workspace=workspace)
    resume = ResumeService(original.siada_config.workspace)
    data = resume.session_manager.load_session(original.session_id, original.openai_session.session_folder)
    resume.restore_to_running_session(data, fresh)
    assert fresh.state.context_token_baseline == original.state.context_token_baseline
    assert fresh.state.context_token_baseline is not original.state.context_token_baseline
    second = baseline.model(fresh, [[baseline.text("synthetic resumed reply", "second")]])
    second.requests.extend(first.requests)
    await run_default(baseline, fresh, second, stream=stream, input="synthetic continue")
    assert counter.call_count == 3
    assert counter.call_args_list[2].args[1] == [{"role": "user", "content": "synthetic continue"}]
    assert counter.call_args_list[2].kwargs == {"diagnostics": {}}
    folder = fresh.openai_session.session_folder
    assert str(folder / state.STATE_FILE) in windows_storage.flushed
    assert not (folder / ".storage-transaction.json").exists()
    assert not list(folder.glob("*.tmp"))


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_windows_final_response_flush_failure_rolls_back_and_retries(
    baseline, monkeypatch, windows_storage, stream,
):
    session = baseline.session()
    store = session.openai_session
    context = baseline.context(session)
    monkeypatch.setattr(estimator, "calculate_tokens", Mock(return_value=10))
    reply = baseline.text("synthetic reply", "reply")
    native = reply.model_dump(exclude_none=True)
    usage = baseline.usage(900, 100)
    model = baseline.model(session, [[reply]], usages=[usage])
    flush = windows_storage.os.fsync
    failed = []

    def fail_response_flush(fd):
        runtime = context.runtime_session
        stream = windows_storage.streams[fd]
        if (not failed and runtime is not None and runtime._pending_response is not None
                and stream.name == str(store.session_folder / state.STATE_FILE)):
            failed.append(True)
            raise OSError("synthetic final flush failure")
        return flush(fd)

    monkeypatch.setattr(windows_storage.os, "fsync", fail_response_flush)
    with pytest.raises(OSError, match="synthetic final flush failure"):
        await run_default(baseline, session, model, stream=stream, context=context, input="synthetic input")
    assert failed == [True]
    saved = state.load_state(store.session_folder, session.session_id)
    assert saved["usage"] == serialize_usage(usage)
    assert saved["context_token_baseline"] is None
    assert session.state.context_token_baseline is None
    assert store.get_context_snapshot_sync()["items"] == [{"role": "user", "content": "synthetic input"}]
    assert native not in await store.get_history_items()
    assert context.runtime_session._pending_response is not None

    await context.runtime_session.add_items([native])
    assert context.runtime_session._pending_response is None
    anchor = session.state.context_token_baseline
    assert anchor.context_tokens == usage.total_tokens
    assert state.load_state(store.session_folder, session.session_id)["context_token_baseline"] == anchor.to_dict()
    assert (await store.get_items()).count(native) == (await store.get_history_items()).count(native) == 1
    assert len(model.requests) == 1