"""
Unit tests for on-disk sub-agent conversation persistence
(siada.tools.agent.subagent_persistence).
"""
import json
import tempfile
import unittest
from pathlib import Path

from siada.tools.agent import subagent_persistence


class TestSubagentPersistence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root_dir = self._tmp.name
        self.root_session_id = "sess-abc123"

    def tearDown(self):
        self._tmp.cleanup()

    def _base_dir(self) -> Path:
        return subagent_persistence.subagents_dir(self.root_dir, self.root_session_id)

    def _index(self) -> dict:
        with open(self._base_dir() / "index.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def test_record_start_creates_running_entry_and_log_file(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_1", parent_id=None, depth=1,
            title="Fix bug", instruction="Fix the bug in foo.py",
        )
        data = self._index()
        entry = data["agents"]["sa_1"]
        self.assertEqual(entry["status"], "running")
        self.assertEqual(entry["depth"], 1)
        self.assertIsNone(entry["parent_id"])
        self.assertEqual(entry["title"], "Fix bug")
        self.assertTrue((self._base_dir() / "sa_1.log").exists())
        log_text = (self._base_dir() / "sa_1.log").read_text(encoding="utf-8")
        self.assertIn("Fix the bug in foo.py", log_text)

    def test_append_log_adds_readable_entries(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_1", parent_id=None, depth=1,
            title="t", instruction="do X",
        )
        subagent_persistence.append_log(
            self.root_dir, self.root_session_id, "sa_1",
            "tool_call", "edit(file.py)", tool_name="edit",
        )
        subagent_persistence.append_log(
            self.root_dir, self.root_session_id, "sa_1",
            "tool_output", "OK",
        )
        log_text = (self._base_dir() / "sa_1.log").read_text(encoding="utf-8")
        self.assertIn("TOOL CALL", log_text)
        self.assertIn("edit(file.py)", log_text)
        self.assertIn("TOOL OUTPUT", log_text)
        self.assertIn("OK", log_text)

    def test_record_finish_marks_completed_and_stores_summary(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_1", parent_id=None, depth=1,
            title="t", instruction="do X",
        )
        subagent_persistence.record_finish(
            self.root_dir, self.root_session_id, "sa_1", "completed", "Did X successfully."
        )
        entry = self._index()["agents"]["sa_1"]
        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["summary"], "Did X successfully.")
        self.assertIsNotNone(entry["finished_at"])

    def test_record_finish_marks_failed(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_1", parent_id=None, depth=1,
            title="t", instruction="do X",
        )
        subagent_persistence.record_finish(
            self.root_dir, self.root_session_id, "sa_1", "failed", "RuntimeError: boom"
        )
        entry = self._index()["agents"]["sa_1"]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("boom", entry["summary"])

    def test_scan_unfinished_returns_only_running_entries(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_running", parent_id=None, depth=1,
            title="still going", instruction="long task",
        )
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_done", parent_id=None, depth=1,
            title="finished", instruction="short task",
        )
        subagent_persistence.record_finish(
            self.root_dir, self.root_session_id, "sa_done", "completed", "done"
        )

        unfinished = subagent_persistence.scan_unfinished(self.root_dir, self.root_session_id)
        ids = {e["id"] for e in unfinished}
        self.assertEqual(ids, {"sa_running"})

    def test_scan_unfinished_empty_when_no_index_file(self):
        unfinished = subagent_persistence.scan_unfinished(self.root_dir, "no-such-session")
        self.assertEqual(unfinished, [])

    def test_scan_unfinished_from_session_path_matches_scan_unfinished(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_running", parent_id=None, depth=1,
            title="still going", instruction="long task",
        )
        from siada.utils import DirectoryUtils
        session_path = Path(DirectoryUtils.get_global_sessions_dir(self.root_dir)) / self.root_session_id

        unfinished = subagent_persistence.scan_unfinished_from_session_path(session_path)
        ids = {e["id"] for e in unfinished}
        self.assertEqual(ids, {"sa_running"})

    def test_nested_sub_sub_agent_records_parent_id_and_depth(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_parent", parent_id=None, depth=1,
            title="parent", instruction="parent task",
        )
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_child", parent_id="sa_parent", depth=2,
            title="child", instruction="child task",
        )
        data = self._index()
        self.assertEqual(data["agents"]["sa_child"]["parent_id"], "sa_parent")
        self.assertEqual(data["agents"]["sa_child"]["depth"], 2)

    def test_read_log_tail_returns_recent_content(self):
        subagent_persistence.record_start(
            self.root_dir, self.root_session_id,
            agent_id="sa_1", parent_id=None, depth=1,
            title="t", instruction="do X",
        )
        subagent_persistence.append_log(
            self.root_dir, self.root_session_id, "sa_1", "message", "final summary text",
        )
        tail = subagent_persistence.read_log_tail(self.root_dir, self.root_session_id, "sa_1")
        self.assertIn("final summary text", tail)

    def test_read_log_tail_missing_file_returns_empty_string(self):
        tail = subagent_persistence.read_log_tail(self.root_dir, self.root_session_id, "no-such-agent")
        self.assertEqual(tail, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
