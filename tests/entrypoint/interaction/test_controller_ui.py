"""
Offline tests for ControllerUI — the ACP presentation sidecar extracted from
Controller (siada/entrypoint/interaction/controller_ui.py).

All network-backed services (quota fetch, session-title LLM call, theme
detection) are mocked; nothing here touches the network, config files or
private session trees.
"""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from siada.entrypoint.interaction.controller_ui import ControllerUI


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _FakeTimer:
    """Recording stand-in for threading.Timer used in timer tests."""

    instances = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.cancelled = False
        self.started = False
        _FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def tick(self):
        self.function()


class _SlashCommandsStub:
    def get_commands(self, session):
        return ["/help", "/model"]

    def cmd_help(self):
        """Show help."""
        return None

    def cmd_model(self):
        """Switch model."""
        return None


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """Poll until predicate() is truthy (background threads are async)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _build_ui(acp_mode: bool = True):
    """Build a ControllerUI with a recording ACP adapter.

    Returns a namespace with:
      - ui:      the ControllerUI instance
      - sent:    list of ACPMessage objects captured by the fake adapter
      - holder:  one-element list standing in for the mutable "current
                 session" slot (mimics Controller.session being reassigned
                 by /clear)
    """
    sent = []
    adapter = SimpleNamespace(_send_if_acp=lambda fn: sent.append(fn()))
    io = SimpleNamespace(acp_adapter=adapter, _notification_handler=None)
    llm_config = SimpleNamespace(
        provider="test-provider",
        model_name="test-model",
        get_thinking_tokens=lambda: "adaptive",
        get_reasoning_effort=lambda: "high",
        enable_thinking=True,
        parallel_tool_calls=True,
    )
    config = SimpleNamespace(
        acp_mode=acp_mode,
        io=io,
        workspace="/ws",
        agent_name="test-agent",
        memory_enabled=True,
        enable_notification=True,
        llm_config=llm_config,
    )
    holder = [None]
    ui = ControllerUI(config, _SlashCommandsStub(), lambda: holder[0])
    return SimpleNamespace(ui=ui, sent=sent, holder=holder)


def _make_session(session_id="sess-1", file_session=None):
    return SimpleNamespace(
        session_id=session_id,
        state=SimpleNamespace(session_title=None),
        openai_session=file_session,
        checkpoint_service=None,
    )


def _make_file_session(signature, items):
    return SimpleNamespace(last_signature=signature, get_history_items=AsyncMock(return_value=items))


def _messages_with_reason(sent, reason):
    return [m for m in sent if getattr(m, "params", {}).get("reason") == reason]


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #
class TestQuota:
    def test_quota_update_payload_and_refresh_throttle(self):
        ctx = _build_ui()
        with patch("siada.services.quota_service.get_quota_usage", return_value="88.97%"):
            ctx.ui.send_quota_update_async()
            ctx.ui.send_quota_update_async()  # within 10s window -> throttled
            assert _wait_for(lambda: _messages_with_reason(ctx.sent, "quota_update"))

        updates = _messages_with_reason(ctx.sent, "quota_update")
        assert len(updates) == 1
        msg = updates[0]
        # Wire payload preserved: session/update + session_update params.
        assert msg.method == "session/update"
        assert msg.params["reason"] == "quota_update"
        assert json.loads(msg.params["content"]) == {"quota_usage": "88.97%"}
        # metadata={} was passed explicitly in the original code, which yields
        # no _meta key on the wire.
        assert "_meta" not in msg.params

    def test_quota_update_skipped_when_usage_unavailable(self):
        ctx = _build_ui()
        fetched = threading.Event()

        def _no_usage():
            fetched.set()
            return None

        with patch("siada.services.quota_service.get_quota_usage", new=_no_usage):
            ctx.ui.send_quota_update_async()
            assert fetched.wait(5.0)
        assert _messages_with_reason(ctx.sent, "quota_update") == []

    def test_low_quota_threshold_notifies_once(self):
        ctx = _build_ui()
        with patch("siada.notifications.show_completion_notification") as notify:
            ctx.ui._check_quota_thresholds("15.00%")
            ctx.ui._check_quota_thresholds("15.00%")
        assert notify.call_count == 1

    def test_quota_threshold_skips_healthy_and_disabled(self):
        ctx = _build_ui()
        with patch("siada.notifications.show_completion_notification") as notify:
            ctx.ui._check_quota_thresholds("88.97%")  # above threshold
            ctx.ui.config.enable_notification = False
            ctx.ui._check_quota_thresholds("5.00%")  # disabled
        assert notify.call_count == 0


# --------------------------------------------------------------------------- #
# Session title
# --------------------------------------------------------------------------- #
class TestSessionTitle:
    def test_title_payload_persisted_and_one_shot_guard(self):
        ctx = _build_ui()
        session = _make_session()
        ctx.holder[0] = session
        title = "Fix login button on mobile"

        with patch(
            "siada.services.session_title.generate_session_title",
            new=AsyncMock(return_value=title),
        ):
            ctx.ui.send_session_title_async("fix login")
            assert _wait_for(
                lambda: bool(_messages_with_reason(ctx.sent, "session_title"))
            )
            # Guard consumed: a second call must not produce another message.
            ctx.ui.send_session_title_async("another message")
            time.sleep(0.1)

        assert len(_messages_with_reason(ctx.sent, "session_title")) == 1
        msg = _messages_with_reason(ctx.sent, "session_title")[0]
        assert msg.method == "session/update"
        assert msg.params == {"reason": "session_title", "content": title}
        assert session.state.session_title == title
        assert ctx.ui._session_title_sent is True

    def test_title_goes_to_session_captured_at_start(self):
        ctx = _build_ui()
        session = _make_session(session_id="captured")
        ctx.holder[0] = session

        with patch(
            "siada.services.session_title.generate_session_title",
            new=AsyncMock(return_value="New session title"),
        ):
            ctx.ui.send_session_title_async("hello")
            assert _wait_for(
                lambda: bool(_messages_with_reason(ctx.sent, "session_title"))
            )

        assert session.state.session_title == "New session title"

    def test_stale_title_not_pushed_after_clear(self):
        ctx = _build_ui()
        old = _make_session(session_id="old")
        new = _make_session(session_id="new")
        ctx.holder[0] = old

        async def _generate_switching_session(_text):
            import asyncio

            await asyncio.sleep(0.05)
            ctx.holder[0] = new  # /clear swaps the session mid-generation
            ctx.ui.reset_history_state()
            return "Stale Title"

        with patch(
            "siada.services.session_title.generate_session_title",
            new=_generate_switching_session,
        ):
            ctx.ui.send_session_title_async("first")
            # Worker finishes by re-arming the guard after dropping the title.
            assert _wait_for(lambda: ctx.ui._session_title_sent is False)

        assert _messages_with_reason(ctx.sent, "session_title") == []
        assert old.state.session_title is None
        assert new.state.session_title is None
        # Re-armed so the new session can get its own title on the next message.
        assert ctx.ui._session_title_sent is False


# --------------------------------------------------------------------------- #
# Notifications + notification handler
# --------------------------------------------------------------------------- #
class TestNotifications:
    def test_send_notification_custom_payload(self):
        ctx = _build_ui()
        ctx.ui.send_notification("ui/example", {"k": "v"})
        assert len(ctx.sent) == 1
        assert ctx.sent[0].method == "ui/example"
        assert ctx.sent[0].params == {"k": "v"}

    def test_register_notification_handler_routes_to_current_session(self):
        ctx = _build_ui()
        fs_a = _make_file_session("sig-a", [])
        fs_b = _make_file_session("sig-b", [])
        sess_a = SimpleNamespace(openai_session=fs_a, session_id="a")
        sess_b = SimpleNamespace(openai_session=fs_b, session_id="b")
        ctx.holder[0] = sess_a

        with patch(
            "siada.support.message_classifier.format_native_items_for_display",
            return_value=[],
        ):
            ctx.ui.register_notification_handler()
            handler = ctx.ui.config.io._notification_handler
            assert handler is not None

            handler("session/pullHistory", {})
            assert ctx.ui._known_sig == "sig-a"
            assert ctx.ui._known_count == 0

            # /clear: the getter now returns the new session, so the next
            # notification necessarily syncs against it.
            ctx.holder[0] = sess_b
            handler("session/pullHistory", {})
            assert ctx.ui._known_sig == "sig-b"
            assert ctx.ui._known_count == 0

    def test_register_notification_handler_noop_without_acp(self):
        ctx = _build_ui(acp_mode=False)
        ctx.ui.register_notification_handler()
        assert ctx.ui.config.io._notification_handler is None


# --------------------------------------------------------------------------- #
# History state
# --------------------------------------------------------------------------- #
class TestHistoryState:
    def test_first_sync_sets_state_and_acknowledges_without_messages(self):
        ctx = _build_ui()
        items = [{"id": "1"}, {"id": "2"}]
        session = _make_session(file_session=_make_file_session("sig-v2", items))

        ctx.ui.sync_history_state(session)

        assert ctx.ui._known_sig == "sig-v2"
        assert ctx.ui._known_count == 2
        assert ctx.sent[-1].method == "session/pullHistoryDone"
        assert ctx.sent[-1].params == {}

    def test_diverged_sync_sends_new_messages_and_updates_state(self):
        ctx = _build_ui()
        items = [{"id": "1"}, {"id": "2"}]
        session = _make_session(file_session=_make_file_session("sig-v2", items))
        ctx.ui._known_sig = "sig-v1"
        ctx.ui._known_count = 1

        with patch(
            "siada.support.message_classifier.format_native_items_for_display",
            return_value=[{"role": "user", "content": "new message"}],
        ):
            ctx.ui.sync_history_state(session)

        assert ctx.ui._known_sig == "sig-v2"
        assert ctx.ui._known_count == 2
        done = ctx.sent[-1]
        assert done.method == "session/pullHistoryDone"
        assert done.params == {"messages": [{"role": "user", "content": "new message"}]}
        session.openai_session.get_history_items.assert_awaited_once_with(include_injected=False)

    def test_sync_without_session_acknowledges_immediately(self):
        ctx = _build_ui()
        ctx.ui.sync_history_state(None)
        assert ctx.sent[-1].method == "session/pullHistoryDone"
        assert ctx.sent[-1].params == {}

    def test_reset_history_state_forgets_known_transcript(self):
        ctx = _build_ui()
        session = _make_session(file_session=_make_file_session("sig-v9", [{"id": "1"}]))
        ctx.ui.sync_history_state(session)
        assert ctx.ui._known_sig == "sig-v9"
        assert ctx.ui._known_count == 1

        ctx.ui.reset_history_state()
        assert ctx.ui._known_sig == ""
        assert ctx.ui._known_count == 0


# --------------------------------------------------------------------------- #
# Banner info (show_announcements)
# --------------------------------------------------------------------------- #
class TestShowAnnouncements:
    def test_banner_payload_theme_slash_commands_and_quota_kickoff(self):
        ctx = _build_ui()
        session = _make_session(session_id="sess-42")
        ctx.holder[0] = session

        with patch("siada.config.conf_store.get_conf_value", return_value="auto"), \
             patch(
                 "siada.io.system_theme_detector.resolve_theme_for_ui",
                 return_value="dark",
                 create=True,  # not present on this refactor branch yet
             ), \
             patch("siada.services.quota_service.get_quota_usage", return_value="50.00%"):
            ctx.ui.show_announcements()
            # Immediate quota fetch fires right after the banner.
            assert _wait_for(lambda: _messages_with_reason(ctx.sent, "quota_update"))

        banners = _messages_with_reason(ctx.sent, "banner_info")
        assert len(banners) == 1
        banner = banners[0]
        assert banner.method == "session/update"
        assert banner.params["_meta"] == {"type": "banner"}

        info = json.loads(banner.params["content"])
        assert info["version"]
        assert info["agent"] == "test-agent"
        assert info["provider"] == "test-provider"
        assert info["model"] == "test-model"
        assert info["working_dir"]
        assert info["thinking_tokens"] == "adaptive"
        assert info["reasoning_effort"] == "high"
        assert info["thinking_enabled"] is True
        assert info["parallel_tool_calls"] is True
        assert info["session_id"] == "sess-42"
        assert info["project_hash"]
        assert info["memory_enabled"] is True
        assert info["theme"] == "dark"

        names = [c["name"] for c in info["slash_commands"]]
        assert "help" in names and "model" in names
        help_cmd = next(c for c in info["slash_commands"] if c["name"] == "help")
        assert help_cmd["description"] == "Show help."

    def test_show_announcements_noop_without_acp(self):
        ctx = _build_ui(acp_mode=False)
        with patch("siada.services.quota_service.get_quota_usage", return_value="50.00%"):
            ctx.ui.show_announcements()
            time.sleep(0.1)
        assert ctx.sent == []
        assert ctx.ui._quota_timer is None


# --------------------------------------------------------------------------- #
# Quota timer lifecycle
# --------------------------------------------------------------------------- #
class TestQuotaTimer:
    def test_timer_starts_once_and_close_stops(self):
        _FakeTimer.instances.clear()
        ctx = _build_ui()

        with patch.object(threading, "Timer", _FakeTimer), \
             patch("siada.services.quota_service.get_quota_usage", return_value="50.00%"), \
             patch("siada.config.conf_store.get_conf_value", return_value="dark"):
            ctx.ui.show_announcements()
            first = _FakeTimer.instances[-1]
            assert first.started and not first.cancelled

            # A second show_announcements (e.g. after /clear or a model
            # switch) must NOT start a second timer chain.
            ctx.ui.show_announcements()
            assert len(_FakeTimer.instances) == 1

            # A fired tick reschedules exactly one follow-up timer.
            first.tick()
            assert len(_FakeTimer.instances) == 2
            second = _FakeTimer.instances[-1]
            assert ctx.ui._quota_timer is second

            # close() cancels the live timer...
            ctx.ui.close()
            assert second.cancelled

            # ...and ticks after close are no-ops (no reschedule, no fetch).
            n_before = len(_FakeTimer.instances)
            second.tick()
            assert len(_FakeTimer.instances) == n_before

    def test_close_is_idempotent(self):
        ctx = _build_ui()
        ctx.ui.close()
        ctx.ui.close()  # must not raise
        assert ctx.ui._exiting is True

def test_processing_and_cancelled_messages_use_acp_adapter():
    ctx = _build_ui()
    ctx.ui.set_processing(True)
    ctx.ui.set_processing(False)
    ctx.ui.send_cancelled("interrupted")
    assert ctx.sent[0].params["reason"] == "processing_started"
    assert ctx.sent[0].params["_meta"]["animation_control"] == "start"
    assert ctx.sent[1].params["reason"] == "input_ready"
    assert ctx.sent[1].params["_meta"]["animation_control"] == "stop"
    assert "interrupted" in ctx.sent[2].to_json()
    ctx.ui.close()
    ctx.ui.set_processing(True)
    assert len(ctx.sent) == 3


def test_remember_own_turn_does_not_replay_history():
    ctx = _build_ui()
    session = _make_session(file_session=SimpleNamespace(
        last_signature="own-turn", native_item_count=4,
    ))
    ctx.ui.remember_history_state(session)
    assert (ctx.ui._known_sig, ctx.ui._known_count) == ("own-turn", 4)
    assert ctx.sent == []


def test_theme_auto_uses_dark_without_detection():
    ctx = _build_ui()
    with patch("siada.config.conf_store.get_conf_value", return_value="auto"), patch(
        "siada.io.system_theme_detector.SystemThemeDetector.detect_theme",
        side_effect=AssertionError("unexpected detection"),
    ) as detector:
        assert ctx.ui._resolve_ui_theme() == "dark"
        detector.assert_not_called()


def test_stale_title_worker_cannot_reset_new_session_guard():
    ctx = _build_ui()
    ctx.holder[0] = _make_session("old")
    workers = []

    def deferred_thread(target, daemon):
        workers.append(target)
        return SimpleNamespace(start=lambda: None)

    with patch("threading.Thread", side_effect=deferred_thread), patch(
        "siada.services.session_title.generate_session_title",
        new=AsyncMock(return_value="Old title"),
    ):
        ctx.ui.send_session_title_async("old prompt")
        ctx.holder[0] = _make_session("new")
        ctx.ui.reset_history_state()
        ctx.ui.send_session_title_async("new prompt")
        workers[0]()
    assert ctx.ui._session_title_sent is True
    assert ctx.sent == []
