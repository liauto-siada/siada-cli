"""Tests for ``PreCompactionMemoryUpdater`` (sync_stage / async_stage).

Both stages are validated independently against a mocked
``MemoryService`` + monkey-patched ``review_and_update_inline_memory``,
so we exercise the wiring without spinning up the real LLM agent.

Two-stage design contract under test:

* ``sync_stage`` calls ``MemoryService.save_session_memory(view, workspace=...)``
  with a ``_SnapshotSessionView`` that exposes the snapshot.
* ``async_stage`` reuses the SAME view (snapshot consistency) and feeds
  the formatted session content into the review agent.
* Both stages tolerate missing/odd contexts (mocks supply only what's
  strictly needed).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.services.memory.memory_update import updater as updater_module
from siada.services.memory.memory_update.snapshot_view import (
    _SnapshotSessionView,
)
from siada.services.memory.memory_update.updater import (
    PreCompactionMemoryUpdater,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_context(*, session_id="sess-A", root_dir="/tmp/work", folder=None):
    """Build a CodeAgentContext-like SimpleNamespace.

    Covers all the attributes the updater actually reads:
    ``session_id`` / ``root_dir`` / ``session.openai_session.session_folder``.
    """
    openai_session = SimpleNamespace(session_folder=folder)
    session = SimpleNamespace(openai_session=openai_session)
    return SimpleNamespace(
        session_id=session_id,
        root_dir=root_dir,
        session=session,
    )


def _make_memory_service_mock(
    *,
    messages: List[dict] | None = None,
    formatted: str = "user: hi\n\nassistant: there",
):
    """A MagicMock standing in for ``MemoryService``.

    Configures the three methods the updater touches:
    ``save_session_memory`` (async), ``_get_all_messages`` (async),
    ``_format_session_content`` (sync).
    """
    svc = MagicMock(name="MemoryService")
    svc.save_session_memory = AsyncMock(return_value="/tmp/memory.md")
    svc._get_all_messages = AsyncMock(
        return_value=messages
        if messages is not None
        else [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "there"},
        ]
    )
    svc._format_session_content = MagicMock(return_value=formatted)
    return svc


# ---------------------------------------------------------------------------
# sync_stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_stage_calls_save_session_memory_with_view():
    svc = _make_memory_service_mock()
    upd = PreCompactionMemoryUpdater(svc)
    ctx = _fake_context(folder=Path("/tmp/sess"))
    snapshot = [{"role": "user", "content": "x"}]

    await upd.sync_stage(context=ctx, snapshot=snapshot, tokens_count=42)

    svc.save_session_memory.assert_awaited_once()
    args, kwargs = svc.save_session_memory.call_args
    # First positional arg is the view, second kwarg is workspace.
    view = args[0]
    assert isinstance(view, _SnapshotSessionView)
    assert view.session_id == "sess-A"
    assert view.session_folder == Path("/tmp/sess")
    assert kwargs.get("workspace") == "/tmp/work"

    # Snapshot content survived the wrapping (effective view path).
    assert await view.get_effective_messages() == snapshot


@pytest.mark.asyncio
async def test_sync_stage_propagates_save_failure():
    """sync_stage MUST NOT swallow — the scheduler does that.

    Letting the exception bubble allows the scheduler to log
    ``[memory-update] sync stage failed`` while still proceeding to
    schedule async_stage.
    """
    svc = _make_memory_service_mock()
    svc.save_session_memory.side_effect = RuntimeError("disk full")
    upd = PreCompactionMemoryUpdater(svc)

    with pytest.raises(RuntimeError, match="disk full"):
        await upd.sync_stage(
            context=_fake_context(),
            snapshot=[{"role": "user", "content": "x"}],
            tokens_count=1,
        )


@pytest.mark.asyncio
async def test_sync_stage_tolerates_missing_session():
    """Tests/mocks may pass contexts without a real ``session``."""
    svc = _make_memory_service_mock()
    upd = PreCompactionMemoryUpdater(svc)
    bare_ctx = SimpleNamespace(
        session_id="bare", root_dir="/r", session=None,
    )

    await upd.sync_stage(
        context=bare_ctx, snapshot=["x"], tokens_count=0,
    )
    view = svc.save_session_memory.call_args.args[0]
    assert view.session_id == "bare"
    assert view.session_folder is None  # graceful fallback


@pytest.mark.asyncio
async def test_sync_stage_handles_missing_session_id():
    """Defensive: ``session_id is None`` should still produce a usable view."""
    svc = _make_memory_service_mock()
    upd = PreCompactionMemoryUpdater(svc)
    ctx = SimpleNamespace(session_id=None, root_dir="/r", session=None)

    await upd.sync_stage(context=ctx, snapshot=["x"], tokens_count=0)
    view = svc.save_session_memory.call_args.args[0]
    assert view.session_id == "unknown-session"


# ---------------------------------------------------------------------------
# async_stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_stage_invokes_review_with_formatted_content(monkeypatch):
    svc = _make_memory_service_mock(formatted="USER: hi\n\nASSISTANT: y")
    upd = PreCompactionMemoryUpdater(svc)

    review_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(
        "siada.services.memory.memory_review_agent.review_and_update_inline_memory",
        review_mock,
    )

    snapshot = [{"role": "user", "content": "hi"}]
    await upd.async_stage(
        context=_fake_context(),
        snapshot=snapshot,
        tokens_count=10,
    )

    # _get_all_messages was called against the SAME view shape
    svc._get_all_messages.assert_awaited_once()
    view = svc._get_all_messages.await_args.args[0]
    assert isinstance(view, _SnapshotSessionView)
    assert await view.get_effective_messages() == snapshot

    # _format_session_content was called with the messages from svc
    svc._format_session_content.assert_called_once_with(
        await svc._get_all_messages(view)
    )

    # Review was called with the formatted string
    review_mock.assert_awaited_once_with("USER: hi\n\nASSISTANT: y")


@pytest.mark.asyncio
async def test_async_stage_skips_when_no_messages(monkeypatch):
    """Empty snapshot → no review call, no error."""
    svc = _make_memory_service_mock(messages=[])
    upd = PreCompactionMemoryUpdater(svc)

    review_mock = AsyncMock()
    monkeypatch.setattr(
        "siada.services.memory.memory_review_agent.review_and_update_inline_memory",
        review_mock,
    )

    await upd.async_stage(
        context=_fake_context(), snapshot=[], tokens_count=0,
    )

    svc._format_session_content.assert_not_called()
    review_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_stage_propagates_review_failure(monkeypatch):
    """Like sync_stage, async_stage lets the scheduler do the swallow.

    The scheduler's ``_run_async_safely`` is the documented place to
    catch this; the updater itself is a thin wrapper.
    """
    svc = _make_memory_service_mock()
    upd = PreCompactionMemoryUpdater(svc)

    review_mock = AsyncMock(side_effect=RuntimeError("LLM down"))
    monkeypatch.setattr(
        "siada.services.memory.memory_review_agent.review_and_update_inline_memory",
        review_mock,
    )

    with pytest.raises(RuntimeError, match="LLM down"):
        await upd.async_stage(
            context=_fake_context(),
            snapshot=[{"role": "user", "content": "x"}],
            tokens_count=1,
        )


# ---------------------------------------------------------------------------
# snapshot consistency between stages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_stages_observe_the_same_snapshot(monkeypatch):
    """sync_stage and async_stage must see identical snapshot contents.

    Each stage receives the SAME shallow-copied list reference from the
    scheduler; no internal deep-copy / re-read should diverge them.
    """
    svc = _make_memory_service_mock()
    upd = PreCompactionMemoryUpdater(svc)

    review_mock = AsyncMock()
    monkeypatch.setattr(
        "siada.services.memory.memory_review_agent.review_and_update_inline_memory",
        review_mock,
    )

    snapshot = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
    ]
    ctx = _fake_context()

    # Run both stages on the same snapshot.
    await upd.sync_stage(context=ctx, snapshot=snapshot, tokens_count=0)
    await upd.async_stage(context=ctx, snapshot=snapshot, tokens_count=0)

    sync_view = svc.save_session_memory.call_args.args[0]
    async_view = svc._get_all_messages.await_args.args[0]

    assert (
        await sync_view.get_effective_messages()
        == await async_view.get_effective_messages()
        == snapshot
    )


def test_module_exports():
    """Smoke check: package surface is stable."""
    assert hasattr(updater_module, "MemoryUpdater")
    assert hasattr(updater_module, "PreCompactionMemoryUpdater")
