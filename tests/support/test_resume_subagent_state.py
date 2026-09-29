"""Tests covering sub-agent resume-recovery (recursive sub-agent mode only):

When ``sub_agent.allow_recursive_subagents`` is enabled, every sub-agent /
sub-sub-agent run is persisted to ``<session>/subagents/index.json`` (see
``siada.tools.agent.subagent_persistence``). If the main agent process ends
abnormally (crash / kill) while one or more of those runs are still
in-flight, their index entries are left with ``status == "running"``.

On resume, ``ResumeService.restore_to_running_session`` must:
1. Scan that index for still-"running" entries.
2. Stage a human-readable note describing them onto
   ``running_session.state.pending_subagent_resume_note``.
3. Explicitly clear that field when there's nothing unfinished, so a stale
   note from a previous resume never leaks into the current one.

``SiadaRunner._prepare_context_for_run`` then drains that staged note into
``context.hook_pending_contexts`` exactly once, the same injection channel
used for background ``run_subtask(async=True)`` completion notices, so it
surfaces as a system message before the main agent's next real LLM call.
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import siada.session  # noqa: F401 -- break circular-import chain
import siada.support.checkpoint_tracker  # noqa: F401

from siada.services.session_management import SessionData
from siada.support.resume_service import ResumeService
from siada.tools.agent import subagent_persistence


def _make_running_session() -> MagicMock:
    running_session = MagicMock()
    running_session.state.openai_session = None  # skip the FileSession swap branch
    running_session.state.pending_goal = None
    running_session.state.pending_subagent_resume_note = None
    return running_session


def _make_session_data(session_dir: Path, session_id: str = "sess-123") -> SessionData:
    return SessionData(
        session_id=session_id,
        items=[],
        metadata={},
        api_messages=None,
        api_messages_tokens=None,
        session_path=session_dir,
    )


class TestRestoreToRunningSessionStagesSubagentResumeNote:
    def test_stages_note_when_unfinished_subagent_entry_exists(self):
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            # Write index.json directly at <session_dir>/subagents/index.json,
            # mirroring what subagent_persistence.record_start would have
            # produced for a sub-agent whose run never got to record_finish.
            base_dir = subagent_persistence.subagents_dir_from_session_path(session_dir)
            base_dir.mkdir(parents=True, exist_ok=True)
            import json
            with open(base_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "agents": {
                            "sa_1": {
                                "id": "sa_1",
                                "parent_id": None,
                                "depth": 1,
                                "title": "Investigate flaky test",
                                "instruction": "Find and fix the flaky test in test_foo.py",
                                "status": "running",
                            }
                        }
                    },
                    f,
                )

            running_session = _make_running_session()
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            note = running_session.state.pending_subagent_resume_note
            assert note is not None
            assert "sa_1" in note
            assert "Find and fix the flaky test in test_foo.py" in note

    def test_no_note_when_all_entries_finished(self):
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            base_dir = subagent_persistence.subagents_dir_from_session_path(session_dir)
            base_dir.mkdir(parents=True, exist_ok=True)
            import json
            with open(base_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump(
                    {"agents": {"sa_1": {"id": "sa_1", "status": "completed"}}},
                    f,
                )

            running_session = _make_running_session()
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            assert running_session.state.pending_subagent_resume_note is None

    def test_no_note_when_no_subagents_dir_at_all(self):
        """Non-recursive-mode sessions never write subagents/index.json --
        resuming one must not raise and must leave the note field cleared."""
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)  # no subagents/ subdir at all

            running_session = _make_running_session()
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            assert running_session.state.pending_subagent_resume_note is None

    def test_stale_note_is_cleared_when_nothing_unfinished(self):
        """A stale note from a PREVIOUS resume on the same long-lived
        RunningSession object must never leak into a session that currently
        has nothing unfinished."""
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)

            running_session = _make_running_session()
            running_session.state.pending_subagent_resume_note = "stale leftover note"
            session_data = _make_session_data(session_dir)

            ResumeService.restore_to_running_session(
                MagicMock(session_manager=MagicMock()),
                session_data,
                running_session,
            )

            assert running_session.state.pending_subagent_resume_note is None


class TestSiadaRunnerConsumesSubagentResumeNote:
    async def _prepare(self, running_session, context):
        from siada.services.siada_runner import SiadaRunner
        await SiadaRunner._prepare_context_for_run(context, running_session)

    def test_hook_pending_contexts_receives_note_and_field_is_cleared(self):
        import asyncio
        from siada.foundation.code_agent_context import CodeAgentContext

        running_session = MagicMock()
        running_session.session_id = "sess-123"
        running_session.state.pending_skill_names = []
        running_session.state.pending_todos = None
        running_session.state.pending_goal = None
        running_session.state.pending_subagent_resume_note = "[Sub-agent resume notice] ..."

        context = CodeAgentContext(root_dir="/tmp")
        context.todos = []
        context.goal = None

        async def _run():
            from siada.services.siada_runner import SiadaRunner
            with_patch_checkpoint = SiadaRunner._prepare_checkpoint_with_timeout
            SiadaRunner._prepare_checkpoint_with_timeout = staticmethod(
                lambda *_a, **_k: asyncio.sleep(0)
            )
            try:
                await SiadaRunner._prepare_context_for_run(context, running_session)
            finally:
                SiadaRunner._prepare_checkpoint_with_timeout = with_patch_checkpoint

        asyncio.run(_run())

        assert context.hook_pending_contexts == ["[Sub-agent resume notice] ..."]
        assert running_session.state.pending_subagent_resume_note is None
