"""Tests for idle-based P2P session reset in LarkSessionResolver.

Covers the behavior where, after a configurable idle window, the next DM
message starts a fresh session and the user is told how to /resume the
previous one.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.im.feishu.lark_session_resolver import LarkSessionResolver


def _make_msg(chat_id: str = "oc_chat", open_id: str = "ou_user"):
    """Minimal P2P IMMessage-like object for resolver tests."""
    return SimpleNamespace(
        request_id="req-1",
        chat_id=chat_id,
        chat_type="p2p",
        sender_open_id=open_id,
        content="hello",
        parent_id=None,
        quoted_content=None,
        quoted_sender=None,
    )


def _make_ctrl(*, idle_timeout: float, current_session_id: str, last_ts,
               controller_start_ts: float | None = None):
    """Build a fake LarkController exposing only what the resolver touches."""
    ctrl = MagicMock()

    # Idle config + activity tracking
    ctrl._resolve_idle_session_timeout.return_value = idle_timeout
    ctrl._last_activity_ts = {}
    if last_ts is not None:
        ctrl._last_activity_ts["oc_chat"] = last_ts

    # _controller_start_ts must be a real float so arithmetic comparisons work.
    # Default to "just now" so that tests without an explicit value don't
    # spuriously trigger idle resets.
    ctrl._controller_start_ts = controller_start_ts if controller_start_ts is not None else time.time()

    # Thread router resolves to the same (current) session — the "continue"
    # path where idle reset applies.
    ctrl._thread_router = MagicMock()
    ctrl._thread_router.resolve_target_session = AsyncMock(
        return_value=current_session_id,
    )
    ctrl._get_routed_session_id.return_value = current_session_id

    # Routing already bound to current session (skip open_id binding branch).
    ctrl._routing = MagicMock()
    ctrl._routing.get_session_id.return_value = current_session_id

    # Session creation / cache
    new_session = SimpleNamespace(session_id="new_session_id")
    existing_session = SimpleNamespace(session_id=current_session_id)
    ctrl.create_new_session.return_value = new_session
    ctrl._session_cache = {current_session_id: existing_session}

    # Notification machinery
    ctrl._resolve_preferred_language.return_value = "en"
    ctrl._card_sender = MagicMock()
    ctrl._card_sender.send_im = AsyncMock()

    ctrl._new_session = new_session
    ctrl._existing_session = existing_session
    return ctrl


@pytest.mark.asyncio
async def test_idle_exceeded_starts_new_session_and_notifies():
    ctrl = _make_ctrl(
        idle_timeout=7200, current_session_id="old_sid", last_ts=0.0,
    )
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg()

    # last_ts=0 -> idle is "now" which is huge (> 7200), reset triggers.
    session, _ = await resolver._resolve_p2p_session(msg, MagicMock())

    assert session is ctrl._new_session
    ctrl.create_new_session.assert_called_once()
    ctrl._card_sender.send_im.assert_awaited_once()
    # Notification must mention the previous session id for /resume.
    sent_text = ctrl._card_sender.send_im.await_args.args[2]
    assert "old_sid" in sent_text
    assert "/resume" in sent_text


@pytest.mark.asyncio
async def test_recent_activity_keeps_current_session():
    import time

    ctrl = _make_ctrl(
        idle_timeout=7200, current_session_id="old_sid",
        last_ts=time.time(),  # just now -> not idle
    )
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg()

    session, _ = await resolver._resolve_p2p_session(msg, MagicMock())

    assert session is ctrl._existing_session
    ctrl.create_new_session.assert_not_called()
    ctrl._card_sender.send_im.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_zero_disables_reset():
    ctrl = _make_ctrl(
        idle_timeout=0, current_session_id="old_sid", last_ts=0.0,
    )
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg()

    session, _ = await resolver._resolve_p2p_session(msg, MagicMock())

    assert session is ctrl._existing_session
    ctrl.create_new_session.assert_not_called()


@pytest.mark.asyncio
async def test_first_message_no_prior_activity_no_reset():
    # last_ts=None and controller_start_ts="just now" -> idle_seconds ≈ 0,
    # well below the 7200 s threshold, so no reset fires on the first message
    # after a fresh daemon startup.
    ctrl = _make_ctrl(
        idle_timeout=7200, current_session_id="old_sid", last_ts=None,
    )
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg()

    session, _ = await resolver._resolve_p2p_session(msg, MagicMock())

    assert session is ctrl._existing_session
    ctrl.create_new_session.assert_not_called()
    # Activity timestamp recorded for future idle detection.
    assert "oc_chat" in ctrl._last_activity_ts


@pytest.mark.asyncio
async def test_activity_is_persisted_on_each_message():
    ctrl = _make_ctrl(
        idle_timeout=7200, current_session_id="old_sid", last_ts=None,
    )
    resolver = LarkSessionResolver(ctrl)
    await resolver._resolve_p2p_session(_make_msg(), MagicMock())
    ctrl._persist_last_activity.assert_called()


@pytest.mark.asyncio
async def test_group_idle_exceeded_starts_new_session_and_notifies():
    ctrl = _make_ctrl(
        idle_timeout=86400, current_session_id="grp_old", last_ts=None,
    )
    # Prior activity recorded long ago for this group chat -> idle reset fires.
    ctrl._last_activity_ts["oc_group"] = 0.0
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg(chat_id="oc_group", open_id="ou_user")
    msg.chat_type = "group"

    session, _ = await resolver._resolve_group_session(msg, MagicMock())

    assert session is ctrl._new_session
    # Group session must be created in the group routing table.
    _, kwargs = ctrl.create_new_session.call_args
    assert kwargs.get("is_single_chat") is False
    ctrl._card_sender.send_im.assert_awaited_once()
    sent_text = ctrl._card_sender.send_im.await_args.args[2]
    assert "grp_old" in sent_text
    assert "/resume" in sent_text


@pytest.mark.asyncio
async def test_group_recent_activity_keeps_current_session():
    ctrl = _make_ctrl(
        idle_timeout=86400, current_session_id="grp_old", last_ts=time.time(),
    )
    # get_or_create delegates to resolve_session; return a sentinel.
    ctrl.resolve_session.return_value = ctrl._existing_session
    resolver = LarkSessionResolver(ctrl)
    msg = _make_msg(chat_id="oc_group")
    msg.chat_type = "group"

    session, _ = await resolver._resolve_group_session(msg, MagicMock())

    assert session is ctrl._existing_session
    ctrl.create_new_session.assert_not_called()

