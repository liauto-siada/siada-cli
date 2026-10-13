"""Context and memory source diagnostics must not expose transcript content."""

import importlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents import Agent, RunConfig

from siada.agent_hub.proactive.scheduler import ProactiveScheduler
from siada.services.effective_context_session import EffectiveContextSession, configure_effective_run
from siada.services.memory.memory_service import MemoryService
from siada.services.memory.memory_update.snapshot_view import _SnapshotSessionView
from siada.services.memory.memory_update.updater import PreCompactionMemoryUpdater
from siada.services.session_storage import SessionStorageError

from test_default_context_cutover import run_default


@pytest.fixture(autouse=True)
def source_logs(baseline, monkeypatch, caplog):
    logger = logging.getLogger(__name__)
    caplog.set_level(logging.INFO, logger=logger.name)
    for name, attribute in (
        ("siada.services.file_session", "logger"),
        ("siada.services.effective_context_session", "logger"),
        ("siada.services.memory.memory_service", "logger"),
        ("siada.services.memory.memory_update.updater", "logger"),
        ("siada.agent_hub.proactive.scheduler", "logger"),
        ("siada.agent_hub.context_filter.context_capture_filter", "logging"),
    ):
        monkeypatch.setattr(importlib.import_module(name), attribute, logger)


@pytest.mark.asyncio
@pytest.mark.parametrize("getter", ["get_context_items", "get_runtime_items", "get_effective_messages"])
@pytest.mark.parametrize("items", [[], [{"role": "user", "content": "synthetic private summary"}]])
async def test_prepared_read_logs_source_version_and_count(baseline, caplog, getter, items):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    await store.replace_context_items(items, expected_version=0)
    before = store.context_file.read_bytes()
    caplog.clear()

    assert await getattr(store, getter)() == items

    assert f"session={store.session_id} mode=prepared source=api_message.json version=1 items={len(items)}" in caplog.text
    assert "synthetic private summary" not in caplog.text
    assert "mode=legacy" not in caplog.text
    assert store.context_file.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("last_index, snapshot, source, expected", [
    (None, None, "api_history.json", ["old", "tail"]),
    (0, [], "api_history.json", ["old", "tail"]),
    (0, ["summary"], "api_messages.json+delta", ["summary", "tail"]),
    (1, ["summary"], "api_messages.json", ["summary"]),
    (-1, ["summary"], "api_messages.json", ["summary"]),
    (99, ["summary"], "api_messages.json", ["summary"]),
])
async def test_legacy_read_logs_actual_source(baseline, caplog, last_index, snapshot, source, expected):
    store = baseline.session().openai_session
    await store.add_items([{"role": "user", "content": text} for text in ("old", "tail")])
    if snapshot is not None:
        (store.session_folder / "api_messages.json").write_text(json.dumps({
            "api_messages": [{"role": "user", "content": text} for text in snapshot],
            "last_index": last_index,
        }), encoding="utf-8")
    caplog.clear()

    assert await store.get_runtime_items() == [{"role": "user", "content": text} for text in expected]

    assert f"session={store.session_id} mode=legacy source={source} items={len(expected)}" in caplog.text
    assert not store.context_file.exists()


@pytest.mark.asyncio
async def test_damaged_prepared_read_does_not_log_success_or_use_legacy(baseline, monkeypatch, caplog):
    store = baseline.session().openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    store.context_file.write_text("{}", encoding="utf-8")
    fallback = AsyncMock(side_effect=AssertionError("Legacy reads must not run"))
    monkeypatch.setattr(store, "get_effective_messages", fallback)
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    caplog.clear()

    with pytest.raises(SessionStorageError):
        await memory._fetch_effective_items(store)

    fallback.assert_not_called()
    assert "[effective-context][read]" not in caplog.text
    assert "[memory-source][read]" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("custom", [False, True])
async def test_default_run_logs_bridge_and_committed_request(baseline, caplog, stream, custom):
    session = baseline.session()
    model = baseline.model(session, [[baseline.text("synthetic private answer")]])

    async def custom_filter(data):
        return data.model_data

    config = RunConfig(tracing_disabled=True, call_model_input_filter=custom_filter if custom else None)
    await run_default(baseline, session, model, stream=stream, config=config, input="synthetic private input")

    filter_kind = "custom" if custom else "default"
    assert f"[effective-context][run] session={session.session_id} mode=prepared bridge=enabled filter={filter_kind}" in caplog.text
    assert f"[effective-context][request] session={session.session_id} mode=prepared source=api_message.json" in caplog.text
    assert "stage=filter_committed" in caplog.text
    assert "admission_id=" in caplog.text
    assert "mode=legacy" not in caplog.text
    assert "synthetic private input" not in caplog.text
    assert "synthetic private answer" not in caplog.text


@pytest.mark.asyncio
async def test_non_file_storage_logs_passthrough_not_legacy(baseline, caplog):
    storage = SimpleNamespace(session_id="external-session")
    config = RunConfig(tracing_disabled=True)

    assert await configure_effective_run(storage, config, agent=Agent(name="test")) == (storage, config)

    assert "session=external-session mode=passthrough bridge=disabled storage=SimpleNamespace" in caplog.text
    assert "mode=legacy" not in caplog.text


def test_rejected_bridge_config_does_not_log_enabled(baseline, caplog):
    bridge = EffectiveContextSession(baseline.session().openai_session)
    config = RunConfig(session_input_callback=lambda *args: [])

    with pytest.raises(ValueError):
        bridge.configure_run(config)

    assert "bridge=enabled" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_failed_request_commit_does_not_log_committed_or_call_model(baseline, monkeypatch, caplog, stream):
    session = baseline.session()
    model = baseline.model(session, [[baseline.text("unused answer")]])
    fail = AsyncMock(side_effect=SessionStorageError("synthetic write failure"))
    monkeypatch.setattr(session.openai_session, "replace_context_items", fail)

    with pytest.raises(SessionStorageError):
        await run_default(baseline, session, model, stream=stream)

    fail.assert_awaited_once()
    assert model.requests == []
    assert "[effective-context][request]" not in caplog.text
    assert "stage=filter_committed" not in caplog.text


@pytest.mark.asyncio
async def test_legacy_filter_has_explicit_marker(baseline, caplog):
    session = baseline.session()
    model = baseline.model(session, [[baseline.text("answer")]])

    await baseline.run(session, model)

    assert f"[effective-context][filter] session={session.session_id} mode=legacy filter=context_capture_filter" in caplog.text
    assert "bridge=enabled" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, source", [
    ("file", "runtime_items"),
    ("snapshot", "in_memory_snapshot"),
    ("effective_adapter", "effective_adapter"),
    ("items_adapter", "items_adapter"),
    ("failed_adapter", "items_adapter"),
])
async def test_memory_read_logs_source_without_content(baseline, caplog, kind, source):
    items = [{"role": "user", "content": "synthetic private memory"}]
    if kind == "file":
        session = baseline.session().openai_session
        await session.migrate_legacy_context(allow_history_only=True)
        await session.add_items(items)
    elif kind == "snapshot":
        session = _SnapshotSessionView("memory-session", None, items)
    else:
        session = SimpleNamespace(session_id="memory-session", get_items=AsyncMock(return_value=items))
        if kind == "effective_adapter":
            session.get_effective_messages = AsyncMock(return_value=items)
        elif kind == "failed_adapter":
            session.get_effective_messages = AsyncMock(side_effect=RuntimeError("synthetic failure"))
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    caplog.clear()

    assert await memory._fetch_effective_items(session) == items

    assert f"[memory-source][read] session={session.session_id} source={source} items=1" in caplog.text
    assert "synthetic private memory" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [[], [
    {"role": "user", "content": "synthetic private preference"},
    {"role": "assistant", "content": "synthetic private response"},
    {"type": "function_call_output", "call_id": "tool-1", "output": "synthetic private tool output"},
]])
async def test_precompaction_review_logs_snapshot_and_filtered_counts(baseline, monkeypatch, caplog, items):
    review = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("siada.services.memory.memory_review_agent.review_and_update_inline_memory", review)
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=100)
    context = baseline.context(baseline.session())

    await PreCompactionMemoryUpdater(memory).async_stage(context=context, snapshot=items, tokens_count=10)

    assert f"[memory-source][review] session={context.session_id} trigger=pre_compaction source=in_memory_snapshot" in caplog.text
    assert f"raw_items={len(items)} messages={2 if items else 0}" in caplog.text
    if items:
        review.assert_awaited_once_with("user: synthetic private preference\n\nassistant: synthetic private response")
    else:
        review.assert_not_awaited()
        assert "status=skipped reason=no_text_messages" in caplog.text
    assert "synthetic private" not in caplog.text


@pytest.mark.asyncio
async def test_periodic_review_logs_markdown_without_claiming_storage_origin(baseline, monkeypatch, caplog):
    content = "# Session\n\nuser: synthetic private transcript"
    path = baseline.root / "synthetic-session.md"
    path.write_text(content, encoding="utf-8")
    analyze = AsyncMock(return_value={"success": True})
    review = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("siada.services.memory.memory_agent.analyze_and_update_memory", analyze)
    monkeypatch.setattr("siada.services.memory.memory_review_agent.review_and_update_inline_memory", review)

    await ProactiveScheduler._analyze_session_file(SimpleNamespace(), path)

    analyze.assert_awaited_once_with(session_content=content)
    review.assert_awaited_once_with(content)
    assert f"[memory-source][analyze] trigger=periodic source=session_markdown file={path.name} chars={len(content)}" in caplog.text
    assert f"[memory-source][review] trigger=periodic source=session_markdown file={path.name} chars={len(content)}" in caplog.text
    assert "mode=prepared" not in caplog.text
    assert "synthetic private transcript" not in caplog.text
    assert str(baseline.root) not in caplog.text


@pytest.mark.asyncio
async def test_failed_periodic_analysis_logs_its_input_but_not_review_start(baseline, monkeypatch, caplog):
    path = baseline.root / "synthetic-session.md"
    path.write_text("synthetic private input", encoding="utf-8")
    analyze = AsyncMock(side_effect=RuntimeError("synthetic analysis failure"))
    review = AsyncMock()
    monkeypatch.setattr("siada.services.memory.memory_agent.analyze_and_update_memory", analyze)
    monkeypatch.setattr("siada.services.memory.memory_review_agent.review_and_update_inline_memory", review)

    await ProactiveScheduler._analyze_session_file(SimpleNamespace(), path)

    analyze.assert_awaited_once()
    review.assert_not_awaited()
    assert "[memory-source][analyze] trigger=periodic source=session_markdown" in caplog.text
    assert "[memory-source][review]" not in caplog.text
    assert "synthetic private input" not in caplog.text


@pytest.mark.asyncio
async def test_memory_export_logs_truncation_without_generated_file_name(baseline, monkeypatch, caplog):
    items = [{"role": "user", "content": text} for text in ("synthetic private old", "synthetic private new")]
    memory = MemoryService(memory_dir=baseline.root / "memory", max_session_tokens=1)
    path = baseline.root / "synthetic-session.md"
    save = AsyncMock(return_value=path)
    monkeypatch.setattr(memory, "_determine_and_save", save)
    monkeypatch.setattr(memory, "_post_save_operations", lambda *args: None)
    view = _SnapshotSessionView("memory-session", None, items)

    assert await memory.save_session_memory(view) == str(path)

    assert "[memory-source][export] session=memory-session messages=1 truncated=True" in caplog.text
    # The conversation-derived slug file name must never reach the logs.
    assert path.name not in caplog.text
    assert save.await_args.kwargs["was_truncated"] is True
    assert save.await_args.args[0] == items[-1:]
    assert "synthetic private" not in caplog.text