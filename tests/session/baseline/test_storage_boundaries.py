"""Characterize legacy file views, isolation, mutation, and failure boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from contextlib import contextmanager

import pytest

from siada.services.file_session import FileSession
from siada.services.session_management import SessionManager
from siada.session.ownership import SessionOwner, SessionOwnershipManager
from siada.support.resume_service import ResumeService


def snapshot(session, messages, last_index=0):
    SessionManager.sync_api_messages(
        session.session_folder, session.session_id, messages,
        tokens_count=50, last_index=last_index, last_signature=session.last_signature,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [-1, 0, 1, 20])
async def test_effective_snapshot_delta_and_stale_anchor_behavior(baseline, index):
    store = baseline.session().openai_session
    history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "new"}]
    await store.add_items(history)
    compressed = [{"role": "user", "content": "summary"}]
    snapshot(store, compressed, index)
    expected = compressed + history[1:] if index == 0 else compressed
    assert await store.get_effective_messages() == expected
    assert await store.get_items() == history


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, "not json", "{}", '{"api_messages": null}'])
async def test_missing_or_malformed_snapshot_falls_back_to_history(baseline, payload):
    store = baseline.session().openai_session
    history = [{"role": "user", "content": "legacy history"}]
    await store.add_items(history)
    if payload is not None:
        (store.session_folder / "api_messages.json").write_text(payload, encoding="utf-8")
    assert await store.get_api_messages() == (None, -1)
    assert await store.get_effective_messages() == history


@pytest.mark.asyncio
async def test_pop_reset_and_injection_preserve_native_identity(baseline):
    store = baseline.session().openai_session
    native = [{"role": "user", "content": "native"}]
    await store.add_items(native)
    signature = store.last_signature
    store.inject_items([{"role": "user", "content": "IPC note"}], source_session_id="source")
    assert await store.get_items() == native
    assert len(await store.get_all_items()) == 2
    assert store.native_item_count == 1 and store.last_signature == signature
    assert store.get_inject_info() == ("source", "IPC note")
    await store.add_items([{"role": "assistant", "content": "answer"}])
    assert store.get_inject_info() is None
    assert (await store.pop_item())["content"] == "answer"
    assert store.get_inject_info() == ("source", "IPC note")
    replacement = [{"role": "user", "content": "restored"}]
    await store.safe_reset_items(replacement)
    assert await store.get_items() == replacement
    assert len(await store.get_all_items()) == 2
    assert store.native_item_count == 1
    assert store._read_metadata()["message_count"] == 1


@pytest.mark.asyncio
async def test_single_instance_concurrent_appends_are_serialized(baseline):
    store = baseline.session().openai_session
    await asyncio.gather(*[
        store.add_items([{"role": "user", "content": f"message-{index}"}])
        for index in range(20)
    ])
    history = await store.get_items()
    assert len(history) == 20
    assert {item["content"] for item in history} == {f"message-{index}" for index in range(20)}
    assert store.native_item_count == 20
    assert store._read_metadata()["message_count"] == 20


@pytest.mark.asyncio
async def test_failed_atomic_history_replace_keeps_prior_file(baseline, monkeypatch):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "before"}])
    before = store.session_file.read_bytes()
    original_replace = Path.replace

    def fail_replace(path, target):
        if target == store.session_file:
            raise OSError("synthetic replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        await store.add_items([{"role": "user", "content": "after"}])
    assert store.session_file.read_bytes() == before
    assert not store.session_file.with_suffix(".tmp").exists()
    assert store.native_item_count == 1


@pytest.mark.asyncio
async def test_callback_failure_does_not_undo_saved_items(baseline):
    store = baseline.session().openai_session
    observed = []

    async def callback(items):
        observed.extend(await store.get_items())
        raise RuntimeError("synthetic callback failure")

    store.on_items_added = callback
    items = [{"role": "user", "content": "saved before callback"}]
    await store.add_items(items)
    assert observed == items
    assert await store.get_items() == items


@pytest.mark.asyncio
async def test_zero_limit_returns_no_items(baseline):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "history"}])
    assert await store.get_items(limit=0) == []
    assert await store.get_all_items(limit=0) == []


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="G12: empty snapshot falls back to history and resurrects discarded context")
async def test_explicit_empty_snapshot_remains_empty(baseline):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "discarded"}])
    snapshot(store, [])
    assert await store.get_effective_messages() == []


@pytest.mark.asyncio
async def test_clear_removes_effective_context_and_stale_counts(baseline):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "discarded"}])
    snapshot(store, [{"role": "user", "content": "stale summary"}])
    await store.clear_session()
    assert await store.get_items() == []
    assert await store.get_effective_messages() == []
    assert store.native_item_count == 0
    assert store._read_metadata()["message_count"] == 0


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="G14: summary-only snapshot cannot align on resume, which restores raw history")
async def test_summary_only_resume_preserves_compacted_runtime_input(baseline):
    original = baseline.session("original")
    await baseline.run(original, baseline.model(original, [[baseline.text("prior answer")]]))
    history = await original.openai_session.get_items()
    summary = [{"role": "user", "content": "summary only"}]
    snapshot(original.openai_session, summary)
    fresh = baseline.session("fresh")
    resume = ResumeService(original.siada_config.workspace)
    data = resume.session_manager.load_session(original.session_id)
    resume.restore_to_running_session(data, fresh)
    model = baseline.model(fresh, [[baseline.text("next answer")]])
    await baseline.run(fresh, model, input="continue")
    assert model.requests[0]["input"] == summary + history[-1:] + [{"role": "user", "content": "continue"}]


@pytest.mark.asyncio
async def test_metadata_write_failure_rolls_back_history_and_signature(baseline, monkeypatch):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "before"}])
    history_before = store.session_file.read_bytes()
    signature_before = store.last_signature

    def fail_metadata(*args):
        raise OSError("synthetic metadata failure")

    monkeypatch.setattr(store, "_write_metadata", fail_metadata)
    with pytest.raises(OSError):
        await store.add_items([{"role": "user", "content": "after"}])
    assert store.session_file.read_bytes() == history_before
    assert store.last_signature == signature_before


def test_interleaved_metadata_owner_write_retains_owner(baseline, monkeypatch):
    store = baseline.session().openai_session
    original_write = store._write_metadata

    def concurrent_ownership_update(metadata):
        SessionOwnershipManager.set_active_owner(store.session_folder, SessionOwner.LARK)
        original_write(metadata)

    monkeypatch.setattr(store, "_write_metadata", concurrent_ownership_update)
    store.add_items_sync([{"role": "user", "content": "new message"}])
    assert SessionOwnershipManager.get_active_owner(store.session_folder) == "lark"


def test_two_instances_interleaved_appends_keep_both_items(baseline, monkeypatch):
    first = baseline.session().openai_session
    second = FileSession(first.session_id, first.sessions_dir)
    first_entered = Event()
    second_attempted = Event()
    second_committed = Event()
    first_read = first._read_session_data
    second_mutation = second._mutation

    def paused_read():
        items = first_read()
        first_entered.set()
        assert second_attempted.wait(timeout=5)
        assert not second_committed.is_set()
        return items

    @contextmanager
    def observed_mutation():
        assert first_entered.wait(timeout=5)
        second_attempted.set()
        with second_mutation():
            yield
        second_committed.set()

    monkeypatch.setattr(first, "_read_session_data", paused_read)
    monkeypatch.setattr(second, "_mutation", observed_mutation)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(store.add_items_sync, [{"role": "user", "content": content}])
                   for store, content in [(first, "first"), (second, "second")]]
        for future in futures:
            future.result(timeout=5)
    assert {item["content"] for item in first_read()} == {"first", "second"}
    assert first.native_item_count == 2
    assert first._read_metadata()["message_count"] == 2