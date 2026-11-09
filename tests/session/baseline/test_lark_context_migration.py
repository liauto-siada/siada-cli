"""Exercise Lark's owned storage preparation and real offline Runner boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import RunConfig

from siada.foundation.code_agent_context import RuntimeSource
from siada.im.feishu.lark_agent_executor import LarkAgentExecutor
from siada.im.models import IMMessage
from siada.services.session_management import SessionManager
from siada.services.session_storage import SessionStorageError
from siada.services.siada_runner import SiadaRunner
from siada.session.ownership import SessionOwner, SessionOwnershipManager
from tests.session.baseline.test_default_context_cutover import run_default


def make_executor(session, monkeypatch):
    store = session.openai_session
    ctrl = SimpleNamespace(
        _config={},
        _workspace=session.siada_config.workspace,
        _agent_name="baseline-agent",
        _active_entries={},
        _lark_io=MagicMock(),
        _card_sender=SimpleNamespace(
            add_typing=AsyncMock(), remove_typing=AsyncMock(), send_im=AsyncMock(),
        ),
        _session_resolver=SimpleNamespace(ensure_in_cache=MagicMock()),
        _verbose_config=SimpleNamespace(is_verbose=lambda *args: False),
        _transport=SimpleNamespace(send_ack=AsyncMock()),
        _stream_consumer=SimpleNamespace(consume_stream=AsyncMock()),
        _resolve_task_key=lambda msg: msg.chat_id,
        _get_session_dir=lambda *args: store.session_folder,
    )
    executor = LarkAgentExecutor(ctrl)
    monkeypatch.setattr(executor, "_resolve_quoted_message", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_collect_media", AsyncMock(return_value=[]))
    return executor, ctrl


def make_message(chat_type):
    return IMMessage(
        request_id="synthetic-request", platform="lark", user_id="synthetic-user",
        chat_id="synthetic-chat", chat_type=chat_type, content_type="text",
        content="continue", timestamp=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
@pytest.mark.parametrize("storage_mode", ["empty", "history_only", "legacy_snapshot", "prepared"])
async def test_lark_prepares_owned_context_before_initialization_and_streaming(
    baseline, monkeypatch, chat_type, storage_mode,
):
    session = baseline.session()
    store = session.openai_session
    history = [] if storage_mode == "empty" else [{"role": "user", "content": "original task"}]
    await store.add_items(history)
    if storage_mode == "history_only":
        with pytest.raises(SessionStorageError, match="history-only migration requires explicit approval"):
            await store.migrate_legacy_context()
        assert not store.has_prepared_context
    expected = history
    summary = [{"role": "user", "content": "saved summary"}]
    if storage_mode == "legacy_snapshot":
        SessionManager.sync_api_messages(
            store.session_folder, store.session_id, summary,
            last_index=0, last_signature=store.last_signature,
        )
        expected = summary
    elif storage_mode == "prepared":
        await store.migrate_legacy_context(allow_history_only=True)
        await store.replace_context_items(summary, expected_version=0)
        expected = summary
    legacy_path = store.session_folder / "api_messages.json"
    legacy_bytes = legacy_path.read_bytes() if legacy_path.exists() else None
    executor, ctrl = make_executor(session, monkeypatch)
    model = baseline.model(session, [[baseline.text("first answer")], [baseline.text("second answer", "second")]])
    context = baseline.context(session)
    results = []

    async def resolve_quoted(msg, running_session):
        assert running_session is session
        assert store.has_prepared_context
        assert await store.get_context_items() == expected
        return None

    async def run_streamed(user_input, context, run_config, openai_session):
        assert openai_session is store
        assert context.runtime_source == RuntimeSource.LARK_CONTROLLER
        # A downstream caller using strict migration sees prepared storage.
        await store.migrate_legacy_context()
        result = await run_default(
            baseline, session, model, stream=True, input=user_input,
            context=context, config=run_config,
        )
        results.append(result)
        return result

    driver = SimpleNamespace(name="baseline-agent", run_streamed=run_streamed)
    monkeypatch.setattr(executor, "_resolve_quoted_message", resolve_quoted)
    monkeypatch.setattr(SiadaRunner, "get_agent", AsyncMock(return_value=driver))
    monkeypatch.setattr(SiadaRunner, "_build_agent_context", AsyncMock(return_value=context))
    monkeypatch.setattr(SiadaRunner, "_build_run_config", lambda *args: RunConfig(tracing_disabled=True))
    monkeypatch.setattr("siada.services.siada_runner.set_trace_processors", lambda *args: None)
    monkeypatch.setattr("siada.services.siada_runner.create_detailed_logger", lambda **kwargs: None)
    msg = make_message(chat_type)

    await executor.run_agent_for_message(msg, session)
    assert results[0].final_output == "first answer"
    first_input = model.requests[0]["input"]
    assert first_input[:-1] == expected
    assert "continue" in first_input[-1]["content"][0]["text"]
    assert (await store.get_history_items())[:len(history)] == history
    expected = await store.get_context_items()
    prepared_version = (await store.get_context_snapshot())["context_version"]

    await executor.run_agent_for_message(msg, session)
    assert results[1].final_output == "second answer"
    assert model.requests[1]["input"] == expected + first_input[-1:]
    assert (await store.get_context_snapshot())["context_version"] > prepared_version
    assert (legacy_path.read_bytes() if legacy_path.exists() else None) == legacy_bytes
    assert store.metadata_file.exists()
    assert "active_owner" not in store._read_metadata()
    assert ctrl._stream_consumer.consume_stream.await_count == 2
    assert ctrl._card_sender.remove_typing.await_count == 2
    assert ctrl._transport.send_ack.await_count == 2
    ctrl._card_sender.send_im.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["history", "legacy_snapshot", "prepared", "migration_write"])
async def test_lark_migration_failure_prevents_initialization_and_releases_ownership(
    baseline, monkeypatch, damage,
):
    session = baseline.session()
    store = session.openai_session
    executor, ctrl = make_executor(session, monkeypatch)
    if damage == "history":
        store.history_file.write_text("not json", encoding="utf-8")
    elif damage == "legacy_snapshot":
        (store.session_folder / "api_messages.json").write_text("not json", encoding="utf-8")
    elif damage == "prepared":
        store.context_file.write_text("{}", encoding="utf-8")
    else:
        import siada.services.file_session as module

        original_write = module.write_json

        def fail_write(path, data):
            if path == store.context_file:
                raise OSError("synthetic migration write failure")
            original_write(path, data)

        monkeypatch.setattr(module, "write_json", fail_write)
    before = {path.name: path.read_bytes() for path in store.session_folder.glob("api_*.json")}
    run_agent = AsyncMock()
    monkeypatch.setattr(SiadaRunner, "run_agent", run_agent)
    release = MagicMock(wraps=SessionOwnershipManager.release_ownership)
    monkeypatch.setattr(SessionOwnershipManager, "release_ownership", release)

    with pytest.raises(OSError if damage == "migration_write" else SessionStorageError):
        await executor.run_agent_for_message(make_message("p2p"), session)

    run_agent.assert_not_awaited()
    executor._resolve_quoted_message.assert_not_awaited()
    executor._collect_media.assert_not_awaited()
    release.assert_called_once()
    assert "active_owner" not in store._read_metadata()
    assert before == {path.name: path.read_bytes() for path in store.session_folder.glob("api_*.json")}
    ctrl._card_sender.remove_typing.assert_awaited_once()
    ctrl._transport.send_ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_ownership_conflict_does_not_migrate_storage(baseline, monkeypatch):
    session = baseline.session()
    store = session.openai_session
    executor, ctrl = make_executor(session, monkeypatch)
    SessionOwnershipManager.set_active_owner(store.session_folder, SessionOwner.CLI)
    migration = AsyncMock()
    monkeypatch.setattr(store, "migrate_legacy_context", migration)

    await executor.run_agent_for_message(make_message("p2p"), session)

    migration.assert_not_awaited()
    executor._resolve_quoted_message.assert_not_awaited()
    assert not store.has_prepared_context
    assert SessionOwnershipManager.get_active_owner(store.session_folder) == SessionOwner.CLI.value
    ctrl._card_sender.send_im.assert_awaited_once()


@pytest.mark.asyncio
async def test_lark_cancelled_migration_releases_ownership(baseline, monkeypatch):
    session = baseline.session()
    store = session.openai_session
    executor, ctrl = make_executor(session, monkeypatch)
    started = asyncio.Event()

    async def migration(**kwargs):
        assert kwargs["allow_history_only"] is True
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(store, "migrate_legacy_context", migration)
    task = asyncio.create_task(executor.run_agent_for_message(make_message("p2p"), session))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    executor._resolve_quoted_message.assert_not_awaited()
    assert "active_owner" not in store._read_metadata()
    ctrl._card_sender.remove_typing.assert_awaited_once()
    ctrl._transport.send_ack.assert_awaited_once()
