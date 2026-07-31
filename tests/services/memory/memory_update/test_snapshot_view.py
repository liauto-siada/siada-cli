"""Tests for ``_SnapshotSessionView``.

The view's job is to satisfy the duck-typed FileSession protocol from a
plain in-memory list. We verify:

* ``session_id`` / ``session_folder`` are exposed verbatim;
* ``get_items()`` returns a fresh copy (mutation-safe);
* ``get_items(limit=N)`` matches FileSession's tail-truncation semantics;
* ``get_effective_messages()`` returns the snapshot as-is;
* ``get_api_messages()`` reports "no snapshot file" via ``(None, -1)``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from siada.services.memory.memory_update.snapshot_view import (
    _SnapshotSessionView,
)


def _make_view(snapshot=None, *, session_id="sess-1", folder=None):
    return _SnapshotSessionView(
        session_id=session_id,
        session_folder=folder,
        snapshot=list(snapshot or []),
    )


@pytest.mark.asyncio
async def test_attributes_passthrough():
    folder = Path("/tmp/example")
    view = _make_view(["a", "b"], session_id="abc", folder=folder)
    assert view.session_id == "abc"
    assert view.session_folder is folder


@pytest.mark.asyncio
async def test_get_items_returns_fresh_copy():
    items = [{"role": "user", "content": "hi"}]
    view = _make_view(items)

    out = await view.get_items()
    # Same content, different list identity → mutating ``out`` must not
    # leak back into the snapshot.
    assert out == items
    assert out is not items
    out.append({"role": "x"})
    out2 = await view.get_items()
    assert out2 == items  # still original


@pytest.mark.asyncio
async def test_get_items_with_limit_tail():
    items = [f"m{i}" for i in range(5)]
    view = _make_view(items)

    # limit smaller than length → tail
    assert await view.get_items(limit=2) == ["m3", "m4"]
    # limit equal length → full
    assert await view.get_items(limit=5) == items
    # limit greater than length → full (no padding)
    assert await view.get_items(limit=10) == items
    # limit None / 0 → full / empty respectively
    assert await view.get_items(limit=None) == items


@pytest.mark.asyncio
async def test_get_effective_messages_is_full_copy():
    items = [{"role": "user", "content": "x"}]
    view = _make_view(items)
    out = await view.get_effective_messages()
    assert out == items
    assert out is not items


@pytest.mark.asyncio
async def test_get_api_messages_is_unavailable():
    """A view has no on-disk api_messages.json → expect ``(None, -1)``."""
    view = _make_view(["x"])
    api_msgs, last_idx = await view.get_api_messages()
    assert api_msgs is None
    assert last_idx == -1


@pytest.mark.asyncio
async def test_outer_mutation_does_not_leak_into_snapshot():
    """External mutation of the source list must not affect the view."""
    src = [{"role": "user", "content": "1"}]
    view = _make_view(src)

    src.append({"role": "user", "content": "2"})  # mutate source
    src[0]["content"] = "changed"  # mutate inner dict (shallow copy)

    items = await view.get_items()
    # List length is unchanged (the view stored a shallow list copy):
    assert len(items) == 1
    # Inner dict IS shared by reference (snapshot is shallow), so the
    # field change is visible — this matches the design's documented
    # trade-off (see §6.2 "dict 共享引用的处理").
    assert items[0]["content"] == "changed"
