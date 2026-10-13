"""
Tests for the sub-agent in-memory session + two cooperating compaction hooks.

Covers:
1. InMemorySession - get/add/pop/clear and logical-run input admission.
2. session_input_callback - seeds new_items into the session and returns the
   combined history + new list without performing compaction.
3. call_model_input_filter - reads the session as the source of truth, compacts
   only above the token threshold, writes the compacted list back, preserves
   instructions, falls back to model_data.input when the session is empty, and
   degrades gracefully (returns the effective input unchanged) on errors.
4. Debug dump mode - SIADA_SUBAGENT_DUMP / DEBUG toggling, JSONL snapshots,
   filter dump points, and crash-safety.
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agents.run_config import CallModelData, ModelInputData

import siada.tools.agent.sub_agent_compaction_filter as mod
from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionError,
    CompactionResult,
)
from siada.tools.agent.sub_agent_compaction_filter import (
    InMemorySession,
    make_sub_agent_compaction_filter,
    make_sub_agent_session_input_callback,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(role: str, text: str) -> dict:
    """Build a minimal Responses-API style message item."""
    return {"role": role, "content": text}


def _make_model_run_config(model_name: str = "claude-sonnet-4.6",
                           context_window: int = 200_000) -> MagicMock:
    """Return a lightweight ModelRunConfig stand-in for the filter."""
    cfg = MagicMock()
    cfg.model_name = model_name
    cfg.context_window = context_window
    return cfg


def _make_call_model_data(input_items: list, instructions: str | None) -> CallModelData:
    """Build a CallModelData wrapping the given model input."""
    return CallModelData(
        model_data=ModelInputData(input=list(input_items), instructions=instructions),
        agent=MagicMock(),
        context=MagicMock(),
    )


# ---------------------------------------------------------------------------
# Part 1 - InMemorySession
# ---------------------------------------------------------------------------

class TestInMemorySession(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    def test_add_and_get_items(self):
        session = InMemorySession()
        items = [_msg("user", "a"), _msg("assistant", "b")]

        self._run(session.add_items(items))
        got = self._run(session.get_items())

        self.assertEqual(got, items)
        # get_items returns a copy, not the internal list
        self.assertIsNot(got, session._items)

    def test_get_items_with_limit(self):
        session = InMemorySession()
        items = [_msg("user", str(i)) for i in range(5)]
        self._run(session.add_items(items))

        got = self._run(session.get_items(limit=2))
        self.assertEqual(got, items[-2:])

    def test_add_items_preserves_identical_messages(self):
        session = InMemorySession()
        dup = _msg("user", "same")

        self._run(session.add_items([dup]))
        self._run(session.add_items([dup]))

        self.assertEqual(self._run(session.get_items()), [dup, dup])

    def test_pop_item_removes_and_allows_readd(self):
        session = InMemorySession()
        a = _msg("user", "a")
        self._run(session.add_items([a]))

        popped = self._run(session.pop_item())
        self.assertEqual(popped, a)
        self.assertEqual(self._run(session.get_items()), [])

        # A popped item can be appended again.
        self._run(session.add_items([a]))
        self.assertEqual(self._run(session.get_items()), [a])

    def test_pop_item_on_empty_returns_none(self):
        session = InMemorySession()
        self.assertIsNone(self._run(session.pop_item()))

    def test_clear_session_resets_items_and_admissions(self):
        session = InMemorySession()
        a = _msg("user", "a")
        self._run(session.add_items([a]))

        self._run(session.clear_session())
        self.assertEqual(self._run(session.get_items()), [])

        # A full reset allows the same item to be added again.
        self._run(session.add_items([a]))
        self.assertEqual(self._run(session.get_items()), [a])

    def test_unique_session_ids(self):
        self.assertNotEqual(InMemorySession().session_id, InMemorySession().session_id)

    def test_admission_guard_survives_compaction_and_consumes_only_input(self):
        session = InMemorySession()
        new = [_msg("user", "a"), _msg("user", "b")]
        summary = [_msg("user", "summary")] * 2
        output = [_msg("assistant", "result")] * 2
        self._run(session.admit_input("run", new))
        self._run(session.replace_context_items(summary))
        self._run(session.add_items(output))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self._run(session.add_items(new[:1]))
        self.assertEqual(self._run(session.get_items()), summary + output)
        self._run(session.add_items(new + output))
        self.assertEqual(self._run(session.get_items()), summary + output * 2)
        self._run(session.add_items(new))
        self.assertEqual(self._run(session.get_items()), summary + output * 2 + new)

    def test_admission_matches_native_input_and_detaches_nested_items(self):
        session = InMemorySession()
        native = {"role": "user", "content": [{"type": "input_text", "text": "task"}]}
        decorated = {**native, "_agents_tool_title": "Title",
                     "_agents_tool_description": "Description"}
        self._run(session.admit_input("run", [decorated]))
        self._run(session.add_items([native]))
        native["content"][0]["text"] = "mutated"
        returned = self._run(session.get_items())
        self.assertEqual(returned[0]["content"][0]["text"], "task")
        returned[0]["content"][0]["text"] = "mutated again"
        self.assertEqual(self._run(session.get_items())[0]["content"][0]["text"], "task")

    def test_replacement_failure_keeps_admission_and_context(self):
        session = InMemorySession()
        new = [_msg("user", "task")]
        self._run(session.admit_input("run", new))
        with patch.object(mod.copy, "deepcopy", side_effect=RuntimeError("copy failed")):
            with self.assertRaisesRegex(RuntimeError, "copy failed"):
                self._run(session.replace_context_items([_msg("user", "summary")]))
        self._run(session.add_items(new))
        self.assertEqual(self._run(session.get_items()), new)


# ---------------------------------------------------------------------------
# Part 2 - session_input_callback
# ---------------------------------------------------------------------------

class TestSessionInputCallback(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    def test_seeds_new_items_into_session(self):
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)

        history = [_msg("user", "h1")]
        new = [_msg("user", "n1")]

        result = self._run(callback(history, new))

        # New input is persisted into the session.
        self.assertEqual(self._run(session.get_items()), new)
        # Callback returns the combined list for the framework's bookkeeping.
        self.assertEqual(result, history + new)

    def test_does_not_persist_history(self):
        """Only new_items are seeded; history is already in the session upstream."""
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)

        history = [_msg("user", "h1"), _msg("assistant", "h2")]
        new = [_msg("user", "n1")]

        self._run(callback(history, new))

        self.assertEqual(self._run(session.get_items()), new)

    def test_reseeding_same_input_is_idempotent(self):
        """Retries that re-seed identical new_items must not duplicate them."""
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)

        new = [_msg("user", "n1")]
        self._run(callback([], new))
        self._run(callback([], new))

        self.assertEqual(self._run(session.get_items()), new)

    def test_new_run_requires_confirmed_input_and_preserves_repeats(self):
        session = InMemorySession()
        new = [_msg("user", "task")]
        first = make_sub_agent_session_input_callback(session)
        second = make_sub_agent_session_input_callback(session)
        self._run(first([], new))
        with self.assertRaisesRegex(ValueError, "awaiting SDK persistence"):
            self._run(second(new, new))
        with self.assertRaisesRegex(ValueError, "different input"):
            self._run(first(new, [_msg("user", "changed")]))
        self._run(session.add_items(new))
        self._run(second(new, new))
        self._run(session.add_items(new))
        self.assertEqual(self._run(session.get_items()), new * 2)

    def test_retry_after_replacement_does_not_readmit_input(self):
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)
        new = [_msg("user", "task")]
        summary = [_msg("user", "summary")]
        self._run(callback([], new))
        self._run(session.replace_context_items(summary))
        self._run(session.add_items(new))
        self._run(callback(summary, new))
        self._run(session.add_items(new))
        self.assertEqual(self._run(session.get_items()), summary)

    def test_empty_admission_preserves_duplicate_outputs(self):
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)
        self._run(callback([], []))
        outputs = [_msg("assistant", "result")] * 2
        self._run(session.add_items(outputs))
        self.assertEqual(self._run(session.get_items()), outputs)


# ---------------------------------------------------------------------------
# Part 3 - call_model_input_filter
# ---------------------------------------------------------------------------

class TestCompactionFilter(unittest.TestCase):

    def _run(self, coro):
        return asyncio.run(coro)

    def test_below_threshold_returns_session_items_unchanged(self):
        session = InMemorySession()
        items = [_msg("user", "a"), _msg("assistant", "b")]
        self._run(session.add_items(items))

        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=[_msg("user", "stale")],
                                     instructions="sys-prompt")

        with patch.object(mod, "calculate_tokens", return_value=100), \
             patch.object(mod._STRATEGY, "should_compact", return_value=False), \
             patch.object(mod._STRATEGY, "compact", new=AsyncMock()) as mock_compact:
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        # Session is authoritative: returns session items, not model_data.input.
        self.assertEqual(result.input, items)
        self.assertEqual(result.instructions, "sys-prompt")
        mock_compact.assert_not_called()
        # Session unchanged.
        self.assertEqual(self._run(session.get_items()), items)

    def test_above_threshold_compacts_and_writes_back(self):
        session = InMemorySession()
        items = [_msg("user", str(i)) for i in range(10)]
        self._run(session.add_items(items))

        compacted = [_msg("user", "summary"), _msg("user", "9")]
        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=items, instructions="sys")

        with patch.object(mod, "calculate_tokens", return_value=999_999), \
             patch.object(mod._STRATEGY, "should_compact", return_value=True), \
             patch.object(
                 mod._STRATEGY, "compact",
                 new=AsyncMock(
                     return_value=CompactionResult(messages=compacted, compacted=True)
                 ),
             ) as mock_compact:
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        mock_compact.assert_awaited_once()
        # compact() is invoked with (model_run_config, effective_input).
        args, _ = mock_compact.call_args
        self.assertIs(args[0], cfg)
        self.assertEqual(args[1], items)

        # Returned input is the compacted list; instructions preserved.
        self.assertEqual(result.input, compacted)
        self.assertEqual(result.instructions, "sys")
        # Session now holds the compacted baseline.
        self.assertEqual(self._run(session.get_items()), compacted)

    def test_empty_session_falls_back_to_model_data_input(self):
        session = InMemorySession()  # empty
        fallback = [_msg("user", "from-model-data")]
        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=fallback, instructions="sys")

        with patch.object(mod, "calculate_tokens", return_value=10) as mock_tokens, \
             patch.object(mod._STRATEGY, "should_compact", return_value=False):
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        # Token counting and the returned input both use the model_data fallback.
        self.assertEqual(mock_tokens.call_args[0][1], fallback)
        self.assertEqual(result.input, fallback)

    def test_compaction_error_returns_effective_input(self):
        session = InMemorySession()
        items = [_msg("user", "a"), _msg("assistant", "b")]
        self._run(session.add_items(items))

        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=items, instructions="sys")

        with patch.object(mod, "calculate_tokens", return_value=999_999), \
             patch.object(mod._STRATEGY, "should_compact", return_value=True), \
             patch.object(mod._STRATEGY, "compact",
                          new=AsyncMock(side_effect=CompactionError("boom"))):
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        # On CompactionError, the original effective input is returned untouched.
        self.assertEqual(result.input, items)
        self.assertEqual(result.instructions, "sys")
        # Session is NOT cleared/rewritten on failure.
        self.assertEqual(self._run(session.get_items()), items)

    def test_unexpected_error_returns_effective_input(self):
        session = InMemorySession()
        items = [_msg("user", "a")]
        self._run(session.add_items(items))

        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=items, instructions=None)

        with patch.object(mod, "calculate_tokens", return_value=999_999), \
             patch.object(mod._STRATEGY, "should_compact", return_value=True), \
             patch.object(mod._STRATEGY, "compact",
                          new=AsyncMock(side_effect=RuntimeError("unexpected"))):
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        self.assertEqual(result.input, items)
        self.assertIsNone(result.instructions)
        self.assertEqual(self._run(session.get_items()), items)


# ---------------------------------------------------------------------------
# Part 4 - Two hooks cooperating across a (simulated) run
# ---------------------------------------------------------------------------

class TestHooksCooperation(unittest.TestCase):
    """Simulate the framework call order: callback seeds new input, then the
    filter reads the session as the up-to-date context."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_callback_seed_visible_to_filter(self):
        session = InMemorySession()
        callback = make_sub_agent_session_input_callback(session)
        cfg = _make_model_run_config()

        history = [_msg("user", "old")]
        new = [_msg("user", "new-turn")]

        # 1) Framework calls the session_input_callback at run start.
        self._run(callback(history, new))

        # 2) Filter runs before the model call and reads the session.
        data = _make_call_model_data(input_items=[], instructions="sys")
        with patch.object(mod, "calculate_tokens", return_value=10), \
             patch.object(mod._STRATEGY, "should_compact", return_value=False):
            flt = make_sub_agent_compaction_filter(cfg, session)
            result = self._run(flt(data))

        # The filter sees exactly what the callback seeded (the new input).
        self.assertEqual(result.input, new)


# ---------------------------------------------------------------------------
# Part 5 - Debug dump mode
# ---------------------------------------------------------------------------

class TestDebugDump(unittest.TestCase):
    """Cover the SIADA_SUBAGENT_DUMP / DEBUG dump toggling and JSONL output."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _read_dump_records(self, dump_dir: Path, session_id: str) -> list:
        """Parse the JSONL dump file for *session_id* into a list of records."""
        path = dump_dir / mod._DUMP_SUBDIR / f"{session_id}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    # -- toggling -----------------------------------------------------------

    def test_is_dump_enabled_explicit_env_truthy(self):
        for val in ("1", "true", "True", "yes", "on"):
            with patch.dict(os.environ, {mod._DUMP_ENV: val}, clear=False):
                self.assertTrue(mod._is_dump_enabled(), f"value={val!r}")

    def test_is_dump_enabled_explicit_env_falsy(self):
        # Explicit falsy value disables even when DEBUG is truthy.
        with patch.dict(os.environ, {mod._DUMP_ENV: "0", "DEBUG": "true"}, clear=False):
            self.assertFalse(mod._is_dump_enabled())

    def test_is_dump_enabled_falls_back_to_debug(self):
        env = {k: v for k, v in os.environ.items() if k != mod._DUMP_ENV}
        env["DEBUG"] = "true"
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(mod._is_dump_enabled())
        env["DEBUG"] = "false"
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(mod._is_dump_enabled())

    # -- no-op when disabled ------------------------------------------------

    def test_dump_items_noop_when_disabled(self):
        session = InMemorySession()
        self._run(session.add_items([_msg("user", "a")]))
        with patch.dict(os.environ, {mod._DUMP_ENV: "0"}, clear=False):
            result = self._run(session.dump_items("label"))
        self.assertIsNone(result)

    # -- writes JSONL when enabled ------------------------------------------

    def test_dump_items_writes_jsonl_when_enabled(self):
        session = InMemorySession()
        items = [_msg("user", "hello"), _msg("assistant", "world")]
        self._run(session.add_items(items))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {mod._DUMP_ENV: "1"}, clear=False), \
                 patch.object(mod, "get_log_directory", return_value=tmp):
                path = self._run(session.dump_items("filter-entry"))

                self.assertIsNotNone(path)
                records = self._read_dump_records(Path(tmp), session.session_id)

            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertEqual(rec["label"], "filter-entry")
            self.assertEqual(rec["session_id"], session.session_id)
            self.assertEqual(rec["item_count"], 2)
            self.assertEqual(rec["items"], items)
            self.assertIn("timestamp", rec)

    def test_dump_appends_multiple_snapshots(self):
        session = InMemorySession()
        self._run(session.add_items([_msg("user", "a")]))

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {mod._DUMP_ENV: "1"}, clear=False), \
                 patch.object(mod, "get_log_directory", return_value=tmp):
                self._run(session.dump_items("first"))
                self._run(session.add_items([_msg("assistant", "b")]))
                self._run(session.dump_items("second"))

                records = self._read_dump_records(Path(tmp), session.session_id)

            self.assertEqual([r["label"] for r in records], ["first", "second"])
            self.assertEqual([r["item_count"] for r in records], [1, 2])

    # -- crash safety -------------------------------------------------------

    def test_dump_never_raises_on_write_failure(self):
        session = InMemorySession()
        self._run(session.add_items([_msg("user", "a")]))

        with patch.dict(os.environ, {mod._DUMP_ENV: "1"}, clear=False), \
             patch.object(mod, "_dump_file_path", side_effect=OSError("disk full")):
            # Must swallow the error and return None, never propagate.
            result = self._run(session.dump_items("boom"))
        self.assertIsNone(result)

    # -- filter dump points -------------------------------------------------

    def test_filter_dumps_entry_and_compaction_points(self):
        session = InMemorySession()
        items = [_msg("user", str(i)) for i in range(6)]
        self._run(session.add_items(items))

        compacted = [_msg("user", "summary"), _msg("user", "5")]
        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=items, instructions="sys")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {mod._DUMP_ENV: "1"}, clear=False), \
                 patch.object(mod, "get_log_directory", return_value=tmp), \
                 patch.object(mod, "calculate_tokens", return_value=999_999), \
                 patch.object(mod._STRATEGY, "should_compact", return_value=True), \
                 patch.object(
                     mod._STRATEGY, "compact",
                     new=AsyncMock(
                         return_value=CompactionResult(messages=compacted, compacted=True)
                     ),
                 ):
                flt = make_sub_agent_compaction_filter(cfg, session)
                self._run(flt(data))

                records = self._read_dump_records(Path(tmp), session.session_id)

            labels = [r["label"] for r in records]
            # filter-entry (metadata only), before-compaction (full items),
            # then after-compaction (full items).
            self.assertIn("filter-entry", labels)
            self.assertIn("before-compaction", labels)
            self.assertIn("after-compaction", labels)

            # filter-entry is lightweight: records item_count but omits items.
            entry = [r for r in records if r["label"] == "filter-entry"][0]
            self.assertEqual(entry["item_count"], len(items))
            self.assertNotIn("items", entry)

            # before-compaction records the full pre-compaction context.
            before = [r for r in records if r["label"] == "before-compaction"][0]
            self.assertEqual(before["items"], items)

            # The after-compaction snapshot reflects the compacted session state.
            after = [r for r in records if r["label"] == "after-compaction"][0]
            self.assertEqual(after["items"], compacted)

    def test_filter_does_not_dump_when_disabled(self):
        session = InMemorySession()
        self._run(session.add_items([_msg("user", "a")]))
        cfg = _make_model_run_config()
        data = _make_call_model_data(input_items=[_msg("user", "a")], instructions="sys")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {mod._DUMP_ENV: "0"}, clear=False), \
                 patch.object(mod, "get_log_directory", return_value=tmp), \
                 patch.object(mod, "calculate_tokens", return_value=10), \
                 patch.object(mod._STRATEGY, "should_compact", return_value=False):
                flt = make_sub_agent_compaction_filter(cfg, session)
                self._run(flt(data))

                dump_dir = Path(tmp) / mod._DUMP_SUBDIR
                # No dump directory / file should have been created.
                self.assertFalse((dump_dir / f"{session.session_id}.jsonl").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
