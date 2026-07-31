"""Tests for Lark controller exception formatting and IM session routing."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

import siada.config.config_loader as config_loader
import siada.entrypoint.interaction.lark_controller as lark_controller
import siada.entrypoint.helpers.model_setup as model_setup
import siada.im.feishu.utils as feishu_utils

from siada.config.config_loader import Config
from siada.entrypoint.interaction.lark_controller import (
    LarkController,
    _decode_embedded_bytes_literals,
    _format_exception_for_user,
)
from siada.entrypoint.interaction.im_controller import ImController
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.session.ownership import SessionOwner


def test_decode_embedded_bytes_literals_decodes_utf8_bytes_payload() -> None:
    """Should decode bytes-literal payloads embedded in exception text."""
    raw = (
        "AnthropicException - "
        "b'{\"code\":4000005,\"message\":\"\\xe4\\xbe\\x9b\\xe5\\xba\\x94\\xe5\\x95\\x86\"}'"
    )

    decoded = _decode_embedded_bytes_literals(raw)

    assert "AnthropicException - {\"code\":4000005" in decoded
    assert "供应商" in decoded
    assert "\\xe4" not in decoded


def test_format_exception_for_user_decodes_bytes_literal_message() -> None:
    """Should return a user-friendly decoded exception message."""

    class SampleError(RuntimeError):
        pass

    exc = SampleError(
        "litellm.ServiceUnavailableError: AnthropicException - "
        "b'{\"code\":4000005,\"message\":\"\\xe4\\xbe\\x9b\\xe5\\xba\\x94\\xe5\\x95\\x86\\xe6\\xa8\\xa1\\xe5\\x9e\\x8b\\xe5\\x93\\x8d\\xe5\\xba\\x94\\xe5\\xbc\\x82\\xe5\\xb8\\xb8\"}'"
    )

    formatted = _format_exception_for_user(exc, max_length=500)

    assert "ServiceUnavailableError" in formatted
    assert "供应商模型响应异常" in formatted
    assert "b'" not in formatted


def test_format_exception_for_user_truncates_long_messages() -> None:
    """Should keep final IM error messages within the configured max length."""
    exc = RuntimeError("x" * 50)

    formatted = _format_exception_for_user(exc, max_length=20)

    assert formatted == ("x" * 17) + "..."


def test_decode_embedded_bytes_literals_returns_original_text_on_unexpected_eval_error(
    monkeypatch,
) -> None:
    """Should return the original text when literal_eval fails unexpectedly."""
    raw = "AnthropicException - b'abc'"

    def _raise_recursion_error(_literal: str):
        raise RecursionError("boom")

    monkeypatch.setattr(feishu_utils.ast, "literal_eval", _raise_recursion_error)

    decoded = _decode_embedded_bytes_literals(raw)

    assert decoded == raw


def test_format_exception_for_user_handles_none_exception() -> None:
    """Should return 'Unknown error' when exc is None."""
    assert _format_exception_for_user(None) == "Unknown error"


def test_decode_embedded_bytes_literals_skips_oversized_literal() -> None:
    """Should skip bytes literals longer than 2000 chars without decoding."""
    # Build a bytes literal that exceeds the 2000 char guard
    huge_body = "\\x41" * 600  # each \\x41 = 4 chars -> 2400 chars in the literal
    raw = f"Error - b'{huge_body}'"
    decoded = _decode_embedded_bytes_literals(raw)
    # The oversized literal should remain untouched (still contains b'...')
    assert "b'" in decoded


def test_decode_embedded_bytes_literals_plain_text_passthrough() -> None:
    """Should return plain text unchanged when no bytes literals are present."""
    text = "Something went wrong: connection refused"
    assert _decode_embedded_bytes_literals(text) == text


def test_format_exception_for_user_empty_message_falls_back_to_class_name() -> None:
    """Should use exception class name when str(exc) is empty."""
    exc = ValueError("")
    result = _format_exception_for_user(exc)
    assert result == "ValueError"


def test_build_running_config_reuses_model_setup_logic(monkeypatch) -> None:
    """Should delegate IM model config building to model_setup helper."""
    conf = Config()
    expected_model_config = object()
    io_token = object()

    monkeypatch.setattr(config_loader, "load_conf", lambda: conf)
    monkeypatch.setattr(lark_controller, "get_default_workspace", lambda: "/tmp/lark-workspace")

    captured: dict[str, object] = {}

    def _fake_get_config_from_conf(io, passed_conf):
        captured["io"] = io
        captured["conf"] = passed_conf
        return expected_model_config

    monkeypatch.setattr(model_setup, "get_config_from_conf", _fake_get_config_from_conf)

    controller = LarkController({"lark": {"mode": "direct"}})
    controller._lark_io = io_token

    running_config = controller._build_running_config()

    assert isinstance(running_config, RunningConfig)
    assert running_config.llm_config is expected_model_config
    assert running_config.io is io_token
    assert running_config.workspace == "/tmp/lark-workspace"
    assert captured == {"io": io_token, "conf": conf}


# ── IM Session Routing Tests ─────────────────────────────────────────


class _ConcreteImController(ImController):
    """Minimal concrete implementation of ImController for testing."""

    def __init__(self, workspace_path: Optional[str] = None):
        super().__init__()
        self._workspace = workspace_path

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    @property
    def is_running(self) -> bool:
        return False

    @property
    def owner_type(self) -> SessionOwner:
        return SessionOwner.IM

    @property
    def workspace(self) -> Optional[str]:
        return self._workspace

    @property
    def platform_name(self) -> str:
        return "test"

    @classmethod
    def create_if_configured(cls) -> Optional["ImController"]:
        return None


def _make_mock_running_config() -> MagicMock:
    """Create a lightweight mock RunningConfig."""
    config = MagicMock(spec=RunningConfig)
    config.workspace = "/tmp/test-workspace"
    return config


def _make_mock_session(session_id: str, config: MagicMock) -> MagicMock:
    """Create a mock RunningSession with the given session_id."""
    session = MagicMock()
    session.session_id = session_id
    session.siada_config = config
    session.state = MagicMock()
    session.state.openai_session = MagicMock()
    return session


def _make_routing_entry(session_id: str, is_single_chat: bool = False) -> dict[str, object]:
    """Create a structured routing entry for tests."""
    return {"session_id": session_id, "is_single_chat": is_single_chat}


class TestImControllerRouting:
    """Tests for ImController session routing infrastructure."""

    def test_resolve_session_creates_new(self, tmp_path: Path) -> None:
        """First resolve for a chat_id should create a new session and persist routing."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        config = _make_mock_running_config()

        mock_session = _make_mock_session("1234567890123", config)

        with patch(
            "siada.session.session_manager.RunningSessionManager.create_session",
            return_value=mock_session,
        ) as mock_create, patch.object(
            ctrl, "_get_routing_file_path", return_value=tmp_path / "im_routing.json"
        ):
            session = ctrl.resolve_session("chat_abc", config)

        assert session is mock_session
        # Routing table should have the entry
        assert "chat_abc" in ctrl._routing.chats
        # Session should be cached
        session_id = ctrl._routing.chats["chat_abc"]["session_id"]
        assert ctrl._routing.chats["chat_abc"]["is_single_chat"] is False
        assert session_id in ctrl._session_cache
        mock_create.assert_called_once()

    def test_resolve_session_reuses_cached(self, tmp_path: Path) -> None:
        """Second resolve for the same chat_id should return the cached session."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        config = _make_mock_running_config()

        first_session = _make_mock_session("1234567890123", config)
        refresh_session = _make_mock_session("1234567890123", config)

        call_count = 0

        def _create_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_session
            return refresh_session

        with patch(
            "siada.session.session_manager.RunningSessionManager.create_session",
            side_effect=_create_side_effect,
        ), patch.object(
            ctrl, "_get_routing_file_path", return_value=tmp_path / "im_routing.json"
        ):
            session1 = ctrl.resolve_session("chat_abc", config)
            session2 = ctrl.resolve_session("chat_abc", config)

        # Should return the same cached object (first_session)
        assert session1 is first_session
        assert session2 is first_session
        # create_session called only once (cached session returned directly)
        assert call_count == 1

    def test_set_session_for_chat(self, tmp_path: Path) -> None:
        """set_session_for_chat should update routing and evict old cache entry."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        routing_file = tmp_path / "im_routing.json"

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            # Set up initial routing and cache
            ctrl._routing.chats["chat_abc"] = _make_routing_entry(
                "old_session_123", is_single_chat=True
            )
            ctrl._session_cache["old_session_123"] = MagicMock()

            ctrl.set_session_for_chat("chat_abc", "new_session_456")

        assert ctrl._routing.chats["chat_abc"] == _make_routing_entry(
            "new_session_456", is_single_chat=True
        )
        # Old session should be evicted from cache
        assert "old_session_123" not in ctrl._session_cache

    def test_create_new_session(self, tmp_path: Path) -> None:
        """create_new_session should generate a new session_id and bind to chat."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        config = _make_mock_running_config()
        routing_file = tmp_path / "im_routing.json"

        mock_session = _make_mock_session("9999999999999", config)

        with patch(
            "siada.session.session_manager.RunningSessionManager.create_session",
            return_value=mock_session,
        ), patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            # Set up old routing
            ctrl._routing.chats["chat_abc"] = _make_routing_entry(
                "old_session", is_single_chat=True
            )
            ctrl._session_cache["old_session"] = MagicMock()

            session = ctrl.create_new_session("chat_abc", config)

        assert session is mock_session
        # Routing should point to a new session (not the old one)
        new_id = ctrl._routing.chats["chat_abc"]["session_id"]
        assert new_id != "old_session"
        assert ctrl._routing.chats["chat_abc"]["is_single_chat"] is True
        # Old session should be evicted
        assert "old_session" not in ctrl._session_cache
        # New session should be cached
        assert new_id in ctrl._session_cache

    def test_clear_session(self, tmp_path: Path) -> None:
        """clear_session should remove routing entry and cache."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        routing_file = tmp_path / "im_routing.json"

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl._routing.chats["chat_abc"] = _make_routing_entry("session_123")
            ctrl._session_cache["session_123"] = MagicMock()

            ctrl.clear_session("chat_abc")

        assert "chat_abc" not in ctrl._routing.chats
        assert "session_123" not in ctrl._session_cache

    def test_clear_session_noop_for_unknown_chat(self, tmp_path: Path) -> None:
        """clear_session should not raise for unknown chat_id."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        routing_file = tmp_path / "im_routing.json"

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl.clear_session("nonexistent_chat")

        assert "nonexistent_chat" not in ctrl._routing.chats

    def test_routing_persistence_save_and_load(self, tmp_path: Path) -> None:
        """Routing table should persist to disk and reload correctly."""
        routing_file = tmp_path / "im_routing.json"

        # First controller: save routing
        ctrl1 = _ConcreteImController(workspace_path=str(tmp_path))
        with patch.object(
            ctrl1, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl1._routing.chats = {
                "chat_a": _make_routing_entry("session_1", is_single_chat=True),
                "chat_b": _make_routing_entry("session_2", is_single_chat=False),
            }
            ctrl1._persist_routing()

        assert routing_file.exists()
        data = json.loads(routing_file.read_text(encoding="utf-8"))
        assert data == {
            "chats": {
                "chat_a": _make_routing_entry("session_1", is_single_chat=True),
                "chat_b": _make_routing_entry("session_2", is_single_chat=False),
            },
            "open_ids": {},
        }

        # Second controller: load routing
        ctrl2 = _ConcreteImController(workspace_path=str(tmp_path))
        with patch.object(
            ctrl2, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl2._load_routing()

        assert ctrl2._routing.chats == {
            "chat_a": _make_routing_entry("session_1", is_single_chat=True),
            "chat_b": _make_routing_entry("session_2", is_single_chat=False),
        }

    def test_load_routing_supports_legacy_string_format(self, tmp_path: Path) -> None:
        """_load_routing should normalize legacy chat_id -> session_id payloads."""
        routing_file = tmp_path / "im_routing.json"
        routing_file.write_text(
            json.dumps({"chat_legacy": "session_legacy"}),
            encoding="utf-8",
        )

        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl._load_routing()

        assert ctrl._routing.chats == {
            "chat_legacy": _make_routing_entry("session_legacy", is_single_chat=False)
        }

    def test_load_routing_tolerates_missing_file(self, tmp_path: Path) -> None:
        """_load_routing should silently skip if file doesn't exist."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        routing_file = tmp_path / "nonexistent" / "im_routing.json"

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl._load_routing()

        assert ctrl._routing.chats == {}

    def test_load_routing_tolerates_corrupt_file(self, tmp_path: Path) -> None:
        """_load_routing should handle malformed JSON gracefully."""
        routing_file = tmp_path / "im_routing.json"
        routing_file.write_text("not valid json {{{", encoding="utf-8")

        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl._load_routing()

        # Should not crash; routing stays empty
        assert ctrl._routing.chats == {}

    def test_legacy_migration(self, tmp_path: Path) -> None:
        """_migrate_legacy_sessions should pick up lark_* directories."""
        # Create fake sessions directory with legacy dirs
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "lark_direct_ou_abc123_oc_chat001").mkdir()
        (sessions_dir / "lark_relay_ou_def456_oc_chat002").mkdir()
        # Non-legacy session should be ignored
        (sessions_dir / "1700000000000").mkdir()
        # Non-directory file should be ignored
        (sessions_dir / "lark_direct_ou_ghi_oc_chat003").touch()  # file, not dir

        routing_file = tmp_path / "im_routing.json"

        ctrl = _ConcreteImController(workspace_path=str(tmp_path))

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ), patch(
            "siada.utils.DirectoryUtils.get_global_sessions_dir",
            return_value=str(sessions_dir),
        ):
            ctrl._migrate_legacy_sessions()

        # split("_", 3) yields ["lark", "direct", "ou", "<rest>"] so
        # parts[3] is everything after the 3rd underscore
        assert "abc123_oc_chat001" in ctrl._routing.chats
        assert ctrl._routing.chats["abc123_oc_chat001"] == _make_routing_entry(
            "lark_direct_ou_abc123_oc_chat001", is_single_chat=True
        )
        assert "def456_oc_chat002" in ctrl._routing.chats
        assert ctrl._routing.chats["def456_oc_chat002"] == _make_routing_entry(
            "lark_relay_ou_def456_oc_chat002", is_single_chat=True
        )
        # Non-legacy session should not appear
        assert "1700000000000" not in ctrl._routing.chats

    def test_legacy_migration_skips_already_routed(self, tmp_path: Path) -> None:
        """_migrate_legacy_sessions should not overwrite existing routing entries."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "lark_direct_ou_abc_oc_chat001").mkdir()

        routing_file = tmp_path / "im_routing.json"

        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        # Pre-populate routing for this chat (parts[3] from split("_", 3))
        ctrl._routing.chats["abc_oc_chat001"] = _make_routing_entry(
            "existing_session_id", is_single_chat=False
        )

        with patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ), patch(
            "siada.utils.DirectoryUtils.get_global_sessions_dir",
            return_value=str(sessions_dir),
        ):
            ctrl._migrate_legacy_sessions()

        # Should NOT overwrite existing entry
        assert ctrl._routing.chats["abc_oc_chat001"] == _make_routing_entry(
            "existing_session_id", is_single_chat=False
        )

    def test_resolve_session_generates_timestamp_id(self, tmp_path: Path) -> None:
        """New session IDs should be timestamp-based (all digits, 13 chars)."""
        ctrl = _ConcreteImController(workspace_path=str(tmp_path))
        config = _make_mock_running_config()
        routing_file = tmp_path / "im_routing.json"

        mock_session = _make_mock_session("dummy", config)

        with patch(
            "siada.session.session_manager.RunningSessionManager.create_session",
            return_value=mock_session,
        ), patch.object(
            ctrl, "_get_routing_file_path", return_value=routing_file
        ):
            ctrl.resolve_session("chat_new", config)

        session_id = ctrl._routing.chats["chat_new"]["session_id"]
        assert session_id.isdigit()
        assert len(session_id) == 13


def test_resolve_drain_chat_id_prefers_single_chat_routes() -> None:
    """IPC drain should prefer routes marked as single chat."""
    with patch.object(LarkController, "_load_routing"), patch.object(
        LarkController, "_migrate_legacy_sessions"
    ):
        controller = LarkController({"lark": {"mode": "direct"}})

    controller._active_sessions = {
        "group_chat": MagicMock(),
        "single_chat": MagicMock(),
    }
    controller._routing.chats = {
        "group_chat": _make_routing_entry("session_group", is_single_chat=False),
        "single_chat": _make_routing_entry("session_single", is_single_chat=True),
    }

    assert controller._resolve_drain_chat_id() == "single_chat"
