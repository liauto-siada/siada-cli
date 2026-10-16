"""Offline regression coverage for the additive versioned storage foundation."""

import base64
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from siada.services.file_session import FileSession
from siada.services.session_management import SessionManager
from siada.services.session_storage import ContextVersionConflict, SessionStorageError


def save_snapshot(store, items, index):
    history = store._read_session_data()
    native = [item for item in history if not store._is_injected(item)]
    from siada.services.session_signature import compute_last_item_signature

    SessionManager.sync_api_messages(
        store.session_folder, store.session_id, items,
        last_index=index, last_signature=compute_last_item_signature(native[:index + 1]),
    )


@pytest.mark.asyncio
async def test_preparation_is_explicit_and_does_not_cut_over_default_readers(baseline):
    store = baseline.session().openai_session
    history = [{"role": "user", "content": "original"}]
    await store.add_items(history)
    with pytest.raises(SessionStorageError, match="explicit approval"):
        await store.migrate_legacy_context()
    assert not store.context_file.exists()
    with pytest.raises(SessionStorageError):
        await store.get_context_items()
    prepared = await store.migrate_legacy_context(allow_history_only=True)
    assert prepared["items"] == history
    assert prepared["migration_source"] == "explicit_history_only"
    assert await store.get_items() == history
    assert await store.get_history_items(include_injected=False) == history


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "summary only"}]])
async def test_migration_preserves_empty_or_summary_snapshot_and_pending_delta(baseline, items):
    store = baseline.session().openai_session
    history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "unsent"}]
    await store.add_items(history)
    save_snapshot(store, items, 0)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    prepared = await store.migrate_legacy_context()
    assert prepared["items"] == items + history[1:]
    for name, content in before.items():
        assert (store.session_folder / name).read_bytes() == content
    assert await store.migrate_legacy_context() == prepared
    assert await store.get_context_items(limit=0) == []
    assert await store.get_history_items(limit=0) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"session_id": "wrong"}, {"last_index": 20}, {"last_index": -1, "last_signature": ""},
    {"last_signature": "wrong"}, {"api_messages": None}, {"last_index": True},
])
async def test_invalid_migration_is_rejected_without_changing_legacy_files(baseline, change):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "original"}])
    save_snapshot(store, [], 0)
    path = store.session_folder / "api_messages.json"
    data = json.loads(path.read_bytes())
    data.update(change)
    path.write_text(json.dumps(data), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    with pytest.raises(SessionStorageError):
        await store.migrate_legacy_context(allow_history_only=True)
    assert not store.context_file.exists()
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


@pytest.mark.asyncio
@pytest.mark.parametrize("with_signature", [False, True])
async def test_migration_recovers_reset_boundary_without_resurrecting_history(baseline, with_signature):
    store = baseline.session().openai_session
    history = [
        {"role": "user", "content": "discarded original"},
        {"type": "function_call", "call_id": "read-1", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "read-1", "output": "kept result"},
        {"role": "assistant", "content": "pending reply"},
    ]
    await store.add_items(history)
    store.inject_items([{"role": "user", "content": "route only"}], "source", position="prepend")
    summary = [{"role": "user", "content": "saved summary"}]
    items = summary if with_signature else summary + history[1:3]
    from siada.services.session_signature import compute_last_item_signature

    SessionManager.sync_api_messages(
        store.session_folder, store.session_id, items, last_index=-1,
        last_signature=compute_last_item_signature(history[:3]) if with_signature else "",
    )
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    prepared = await store.migrate_legacy_context()
    assert prepared["items"] == items + history[3:]
    assert prepared["migration_source"] == "legacy_snapshot"
    assert len(prepared["routed_items"]) == 1
    assert await store.migrate_legacy_context() == prepared
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")
                      if path != store.context_file}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    "empty", "summary", "duplicate", "duplicate_signature", "trailing_summary", "wrong_signature",
])
async def test_migration_rejects_reset_boundary_without_unique_final_anchor(baseline, case):
    store = baseline.session().openai_session
    anchor = {"role": "user", "content": "repeated request"}
    history = [anchor, {"role": "assistant", "content": "pending reply"}]
    if case in ("duplicate", "duplicate_signature"):
        history += [anchor]
    await store.add_items(history)
    summary = {"role": "user", "content": "summary without native anchor"}
    items = {
        "empty": [], "summary": [summary], "duplicate": [anchor], "duplicate_signature": [summary],
        "trailing_summary": [anchor, summary], "wrong_signature": [anchor],
    }[case]
    from siada.services.session_signature import compute_last_item_signature

    signature = compute_last_item_signature([anchor]) if case == "duplicate_signature" else ""
    SessionManager.sync_api_messages(
        store.session_folder, store.session_id, items,
        last_signature="wrong" if case == "wrong_signature" else signature,
    )
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    with pytest.raises(SessionStorageError, match="trustworthy history boundary"):
        await store.migrate_legacy_context(allow_history_only=True)
    assert not store.context_file.exists()
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["not json", "[]", "{}", '{"items": null}'])
async def test_damaged_versioned_context_never_falls_back_to_full_history(baseline, payload):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "must not resurrect"}])
    store.context_file.write_text(payload, encoding="utf-8")
    with pytest.raises(SessionStorageError):
        await store.get_context_items()
    with pytest.raises(SessionStorageError):
        await store.migrate_legacy_context(allow_history_only=True)
    assert store.context_file.read_text(encoding="utf-8") == payload


@pytest.mark.asyncio
async def test_context_replacement_preserves_history_metadata_signature_and_routing(baseline):
    store = baseline.session().openai_session
    history = [
        {"role": "user", "content": "full original"},
        {"type": "function_call", "call_id": "c", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c", "output": "full tool result"},
    ]
    await store.add_items(history)
    store.inject_items([{"role": "user", "content": "route only"}], "source")
    prepared = await store.migrate_legacy_context(allow_history_only=True)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")
              if path != store.context_file}
    observed = []

    async def callback(items):
        observed.append(items)

    store.on_items_added = callback
    summary = [{"role": "user", "content": "summary"}]
    assert await store.replace_context_items(summary, expected_version=0) == 1
    assert await store.get_context_items() == summary
    assert (await store.get_context_snapshot())["routed_items"] == prepared["routed_items"]
    assert store.get_inject_info() == ("source", "route only")
    assert observed == []
    for name, content in before.items():
        assert (store.session_folder / name).read_bytes() == content
    assert await store.get_history_items(include_injected=False) == history
    summary[0]["content"] = "mutated caller data"
    assert (await store.get_context_items())[0]["content"] == "summary"
    with pytest.raises(ContextVersionConflict):
        await store.replace_context_items([], expected_version=0)
    assert await store.replace_context_items([], expected_version=1) == 2
    assert await store.get_context_items() == []
    assert await store.get_items() == []
    assert await store.get_history_items(include_injected=False) == history


def test_two_instances_cannot_commit_the_same_context_version(baseline):
    first = baseline.session().openai_session
    first.migrate_legacy_context_sync(allow_history_only=True)
    second = FileSession(first.session_id, first.sessions_dir)

    def replace(store, content):
        try:
            return store.replace_context_items_sync(
                [{"role": "user", "content": content}], expected_version=0,
            )
        except ContextVersionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda pair: replace(*pair), [(first, "one"), (second, "two")]))
    assert sorted(map(str, results)) == ["1", "conflict"]
    assert first.get_context_snapshot_sync()["context_version"] == 1


@pytest.mark.asyncio
async def test_prepared_append_updates_both_views_and_fences_stale_replacement(baseline):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    await store.add_items([{"role": "user", "content": "new arrival"}])
    with pytest.raises(ContextVersionConflict, match="changed"):
        await store.replace_context_items([], expected_version=0)
    assert await store.get_context_items() == [{"role": "user", "content": "new arrival"}]
    assert await store.get_items() == await store.get_history_items()


@pytest.mark.asyncio
async def test_legacy_snapshot_writer_is_rejected_without_invalidating_preparation(baseline):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    with pytest.raises(SessionStorageError, match="legacy snapshot"):
        SessionManager.sync_api_messages(store.session_folder, store.session_id, [])
    assert await store.get_context_items() == []
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


@pytest.mark.asyncio
async def test_failed_context_replace_restores_previous_version(baseline, monkeypatch):
    import siada.services.file_session as module

    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    before = store.context_file.read_bytes()

    def fail(path, data):
        path.write_text("partial context", encoding="utf-8")
        raise OSError("synthetic context failure")

    monkeypatch.setattr(module, "write_json", fail)
    with pytest.raises(OSError, match="synthetic context failure"):
        await store.replace_context_items([], expected_version=0)
    assert store.context_file.read_bytes() == before
    assert (await store.get_context_snapshot())["context_version"] == 0


@pytest.mark.asyncio
async def test_reentrant_read_inside_transaction_does_not_recover_live_write(baseline, monkeypatch):
    store = baseline.session().openai_session
    write = store._write_metadata

    def read_during_write(metadata):
        assert store.native_item_count == 1
        write(metadata)

    monkeypatch.setattr(store, "_write_metadata", read_during_write)
    await store.add_items([{"role": "user", "content": "committed"}])
    assert (await store.get_history_items())[0]["content"] == "committed"


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [-1, -10])
async def test_negative_message_limits_are_rejected(baseline, limit):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    for reader in (store.get_items, store.get_all_items, store.get_history_items, store.get_context_items):
        with pytest.raises(ValueError, match="nonnegative"):
            await reader(limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["[]", "{}", '{"version": 1, "before": {"../escape": null}}'])
async def test_invalid_transaction_journal_blocks_read_without_touching_history(baseline, payload):
    store = baseline.session().openai_session
    before = store.history_file.read_bytes()
    journal = store.session_folder / ".storage-transaction.json"
    journal.write_text(payload, encoding="utf-8")
    with pytest.raises(SessionStorageError, match="journal"):
        await store.get_history_items()
    assert store.history_file.read_bytes() == before
    assert journal.read_text(encoding="utf-8") == payload


@pytest.mark.asyncio
async def test_process_exit_during_transaction_recovers_real_journal(baseline):
    import siada.services.session_storage as storage

    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "before crash"}])
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    script = """
import importlib.util
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("session_storage", sys.argv[1])
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
folder = Path(sys.argv[2])
with storage.storage_transaction(folder):
    (folder / "api_history.json").write_text("partial history", encoding="utf-8")
    (folder / "signature.json").write_text("partial signature", encoding="utf-8")
    os._exit(7)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, storage.__file__, str(store.session_folder)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 7, result.stderr
    assert (store.session_folder / ".storage-transaction.json").exists()
    assert await store.get_history_items() == [{"role": "user", "content": "before crash"}]
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


@pytest.mark.asyncio
async def test_signature_failure_rolls_back_history_and_metadata(baseline, monkeypatch):
    from pathlib import Path

    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "before"}])
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}
    replace = Path.replace

    def fail(path, target):
        if target == store.session_folder / "signature.json":
            raise OSError("synthetic signature failure")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="synthetic signature failure"):
        await store.add_items([{"role": "user", "content": "after"}])
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("*.json")}


def test_nested_mutation_cannot_expand_unjournaled_targets(baseline):
    from siada.services.session_storage import storage_transaction

    store = baseline.session().openai_session
    before = store.history_file.read_bytes()
    with pytest.raises(SessionStorageError, match="Nested mutation targets"):
        with storage_transaction(store.session_folder, ("api_message.json",)):
            with storage_transaction(store.session_folder):
                store.history_file.write_text("not allowed", encoding="utf-8")
    assert store.history_file.read_bytes() == before
    assert not (store.session_folder / ".storage-transaction.json").exists()


def test_acp_display_replay_uses_full_native_history_not_context_mirror(baseline):
    from types import SimpleNamespace
    from siada.acp_server.runtime import SiadaTurnRunner

    session = baseline.session()
    store = session.openai_session
    native = [{"role": "user", "content": "original task"}, {"role": "assistant", "content": "original reply"}]
    store.add_items_sync(native)
    store.inject_items([{"role": "user", "content": "external routed message"}], "source")
    store.migrate_legacy_context_sync(allow_history_only=True)
    store.replace_context_items_sync([], expected_version=0)
    session.task_message_state.reset_message_history([{"role": "user", "content": "stale mirror"}])
    runner = SiadaTurnRunner.__new__(SiadaTurnRunner)
    runner._sessions = {session.session_id: SimpleNamespace(session=session)}
    assert runner.load_history_messages(session.session_id) == native


def test_ui_pull_after_context_replacement_keeps_full_history_and_native_count(baseline):
    from siada.entrypoint.interaction.controller_ui import ControllerUI

    session = baseline.session()
    store = session.openai_session
    first = [{"role": "user", "content": "original"}]
    second = [{"role": "assistant", "content": "reply"}]
    store.add_items_sync(first)
    notifications = []
    ui = ControllerUI.__new__(ControllerUI)
    ui._known_sig, ui._known_count = "", 0
    ui.send_notification = lambda method, params: notifications.append((method, params))
    ui.sync_history_state(session)
    assert ui._known_count == 1
    store.add_items_sync(second)
    store.inject_items([{"role": "user", "content": "not a native user turn"}], "source")
    store.migrate_legacy_context_sync(allow_history_only=True)
    store.replace_context_items_sync([], expected_version=0)
    ui.sync_history_state(session)
    assert notifications[-1] == ("session/pullHistoryDone", {"messages": second})
    assert ui._known_count == store.native_item_count == 2


def test_from_file_recovers_deleted_history_before_path_validation(baseline):
    store = baseline.session().openai_session
    before = store.history_file.read_bytes()
    journal = store.session_folder / ".storage-transaction.json"
    journal.write_text(json.dumps({"version": 1, "before": {
        "api_history.json": base64.b64encode(before).decode("ascii"),
    }}), encoding="utf-8")
    store.history_file.unlink()
    restored = FileSession.from_file(store.history_file)
    assert restored.history_file.read_bytes() == before
    assert not journal.exists()


@pytest.mark.asyncio
async def test_interrupted_multi_file_write_is_rolled_back_before_read(baseline):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": "before"}])
    paths = [store.history_file, store.metadata_file, store.session_folder / "signature.json"]
    before = {path.name: path.read_bytes() for path in paths}
    journal = store.session_folder / ".storage-transaction.json"
    journal.write_text(json.dumps({"version": 1, "before": {
        name: base64.b64encode(content).decode("ascii") for name, content in before.items()
    }}), encoding="utf-8")
    for path in paths:
        path.write_text("interrupted", encoding="utf-8")
    assert await store.get_history_items() == [{"role": "user", "content": "before"}]
    assert not journal.exists()
    assert before == {path.name: path.read_bytes() for path in paths}


@pytest.mark.asyncio
async def test_public_distribution_disables_conversation_collection(baseline):
    """The private telemetry upload hook is not part of this distribution.

    ``_create_telemetry_hook`` returns None here, so a context replacement can
    never leak the discarded full history into a conversation collector.
    """
    from siada.session.session_manager import RunningSessionManager

    session = baseline.session()
    store = session.openai_session
    history = [
        {"role": "user", "content": "full original"},
        {"type": "function_call", "call_id": "c", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c", "output": "full tool result"},
    ]
    await store.add_items(history)
    store.inject_items([{"role": "user", "content": "must be excluded"}], "source")
    await store.migrate_legacy_context(allow_history_only=True)
    assert RunningSessionManager._create_telemetry_hook(session, session.siada_config) is None
    await store.replace_context_items([], expected_version=0)