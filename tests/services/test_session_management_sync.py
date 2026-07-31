"""
Unit tests for the refactored api_messages.json sync & rollback logic.

Covers:
  * SessionManager.sync_api_messages  -> file contents & overwrite & OSError.
  * SessionManager.resolve_session_path / resolve_api_messages_file.
  * SlashCommands._manage_session_and_restore rollback behaviour:
      - happy path: file is overwritten, git restore invoked once.
      - git restore fails, api_messages.json existed before -> content restored.
      - git restore fails, api_messages.json did NOT exist before -> file removed.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# NOTE: Pre-import siada.session BEFORE slash_commands is touched (directly
# or via patch("siada.support.slash_commands.*")) to break a circular-import
# chain: slash_commands -> checkpoint_tracker -> session.task_message_state
# -> session/__init__ -> session_models -> checkpoint_tracker (cycle).
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401
import siada.support.slash_commands  # noqa: F401

from siada.services.session_management import SessionManager


# ----- SessionManager static helpers ------------------------------------------------


class TestSessionManagerSyncApiMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.session_path = Path(self.tmp) / "session_abc"
        self.session_id = "session_abc"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_expected_payload(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        SessionManager.sync_api_messages(
            session_path=self.session_path,
            session_id=self.session_id,
            api_messages=messages,
            tokens_count=42,
            last_index=7,
            last_signature="sig-7",
        )

        file_path = self.session_path / "api_messages.json"
        self.assertTrue(file_path.exists())
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["session_id"], self.session_id)
        self.assertEqual(data["tokens_count"], 42)
        self.assertEqual(data["last_index"], 7)
        self.assertEqual(data["last_signature"], "sig-7")
        self.assertEqual(data["api_messages"], messages)

    def test_overwrites_existing_file(self) -> None:
        # Write initial content with a sentinel key.
        SessionManager.sync_api_messages(
            session_path=self.session_path,
            session_id=self.session_id,
            api_messages=[{"role": "user", "content": "first"}],
            tokens_count=1,
            last_index=0,
            last_signature="sig-0",
        )
        file_path = self.session_path / "api_messages.json"
        original = file_path.read_text(encoding="utf-8")
        self.assertIn("first", original)

        # Now overwrite with different payload.
        SessionManager.sync_api_messages(
            session_path=self.session_path,
            session_id=self.session_id,
            api_messages=[{"role": "assistant", "content": "second"}],
            tokens_count=99,
            last_index=5,
            last_signature="sig-5",
        )
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["api_messages"][0]["content"], "second")
        self.assertEqual(data["tokens_count"], 99)
        # Sanity: no leftover of the old content.
        self.assertNotIn("first", file_path.read_text(encoding="utf-8"))

    def test_raises_oserror_on_io_failure(self) -> None:
        # Point session_path at a path that cannot be a directory
        # (existing regular file), forcing parent mkdir / open to blow up.
        blocker = Path(self.tmp) / "blocker"
        blocker.write_text("x", encoding="utf-8")
        bad_path = blocker / "nested" / "session"  # parent is a file, not a dir

        with self.assertRaises(OSError):
            SessionManager.sync_api_messages(
                session_path=bad_path,
                session_id="x",
                api_messages=[],
            )


class TestSessionManagerResolvers(unittest.TestCase):
    def test_resolve_paths(self) -> None:
        with patch(
            "siada.services.session_management.DirectoryUtils.get_global_sessions_dir",
            return_value="/tmp/fake/sessions",
        ):
            sp = SessionManager.resolve_session_path("/ws", "sid")
            fp = SessionManager.resolve_api_messages_file("/ws", "sid")

        self.assertEqual(sp, Path("/tmp/fake/sessions") / "sid")
        self.assertEqual(fp, sp / "api_messages.json")


# ----- SlashCommands._manage_session_and_restore rollback ---------------------------


def _make_slash_commands():
    """Instantiate SlashCommands with a bare MagicMock io; avoids heavy setup."""
    from siada.support.slash_commands import SlashCommands
    return SlashCommands(io=MagicMock(), verbose=False)


def _build_fake_session(workspace: str, session_id: str, git_service: MagicMock) -> MagicMock:
    """Build a minimal session mock accepted by _manage_session_and_restore."""
    session = MagicMock()
    session.session_id = session_id
    session.siada_config.workspace = workspace

    # task_message_state: needs _real_messages, set_real_messages, reset_real_messages
    real_messages = MagicMock()
    real_messages.real_api_history = [{"role": "user", "content": "live"}]
    real_messages.last_index = 3
    real_messages.last_signature = "sig-live"
    session.task_message_state._real_messages = real_messages
    session.task_message_state.set_real_messages = MagicMock()
    session.task_message_state.reset_real_messages = MagicMock()

    # state.openai_session: async get_items / safe_reset_items
    session.state.openai_session = MagicMock()
    session.state.openai_session.get_items = AsyncMock(return_value=["old-item"])
    session.state.openai_session.safe_reset_items = AsyncMock(return_value=None)

    # state.usage (object with total_tokens attr)
    session.state.usage = MagicMock(total_tokens=123)

    # checkpoint_tracker.git_service
    session.checkpoint_tracker.git_service.restore_project_from_snapshot = git_service
    return session


def _build_checkpoint_data() -> MagicMock:
    ck = MagicMock()
    ck.real_api_message = None  # triggers reset_real_messages path
    ck.usage = None
    return ck


class TestManageSessionAndRestoreRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.workspace = self.tmp
        self.session_id = "sid-123"
        self.session_path = Path(self.tmp) / "sessions_dir" / self.session_id
        self.api_file = self.session_path / "api_messages.json"

        # Patch DirectoryUtils so sync/resolve routes to our tmp dir.
        self._patcher = patch(
            "siada.services.session_management.DirectoryUtils.get_global_sessions_dir",
            return_value=str(Path(self.tmp) / "sessions_dir"),
        )
        self._patcher.start()

        # Import slash_commands lazily (avoids circular-import at module level)
        # so the deserialize_usage patch below can resolve the attribute.
        import siada.support.slash_commands  # noqa: F401

        # deserialize_usage is called inside _manage_session_and_restore — stub it out.
        self._deser_patcher = patch(
            "siada.support.slash_commands.deserialize_usage",
            return_value=MagicMock(total_tokens=0),
        )
        self._deser_patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        self._deser_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- happy path ----

    def test_success_writes_file_and_invokes_git(self) -> None:
        git_service = MagicMock(return_value=None)
        session = _build_fake_session(self.workspace, self.session_id, git_service)
        ck = _build_checkpoint_data()

        cmds = _make_slash_commands()
        ok = cmds._manage_session_and_restore(
            session, "target-hash", [{"role": "user", "content": "restored"}], ck
        )

        self.assertTrue(ok)
        git_service.assert_called_once_with("target-hash")

        # File written with the current real messages.
        self.assertTrue(self.api_file.exists())
        data = json.loads(self.api_file.read_text(encoding="utf-8"))
        self.assertEqual(data["api_messages"], [{"role": "user", "content": "live"}])
        self.assertEqual(data["last_index"], 3)
        self.assertEqual(data["last_signature"], "sig-live")

    # ---- rollback: file existed before ----

    def test_rollback_restores_previous_file_when_git_fails(self) -> None:
        # Pre-existing api_messages.json with sentinel content.
        self.api_file.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = b'{"api_messages": [{"role": "user", "content": "ORIGINAL"}]}'
        self.api_file.write_bytes(original_bytes)

        git_service = MagicMock(side_effect=RuntimeError("git boom"))
        session = _build_fake_session(self.workspace, self.session_id, git_service)
        ck = _build_checkpoint_data()

        cmds = _make_slash_commands()
        ok = cmds._manage_session_and_restore(session, "target-hash", [], ck)

        self.assertFalse(ok)
        git_service.assert_called_once_with("target-hash")

        # File must be restored byte-for-byte.
        self.assertTrue(self.api_file.exists())
        self.assertEqual(self.api_file.read_bytes(), original_bytes)

        # In-memory rollback fired.
        session.state.openai_session.safe_reset_items.assert_awaited()
        session.task_message_state.set_real_messages.assert_called()

    # ---- rollback: file did NOT exist before ----

    def test_rollback_deletes_file_when_git_fails_and_no_prior_file(self) -> None:
        # No api_messages.json present before the call.
        self.assertFalse(self.api_file.exists())

        git_service = MagicMock(side_effect=RuntimeError("git boom"))
        session = _build_fake_session(self.workspace, self.session_id, git_service)
        ck = _build_checkpoint_data()

        cmds = _make_slash_commands()
        ok = cmds._manage_session_and_restore(session, "target-hash", [], ck)

        self.assertFalse(ok)
        git_service.assert_called_once_with("target-hash")

        # File should have been written by sync, then removed by rollback.
        self.assertFalse(
            self.api_file.exists(),
            "api_messages.json must be deleted when it did not exist before sync",
        )


if __name__ == "__main__":
    unittest.main()
