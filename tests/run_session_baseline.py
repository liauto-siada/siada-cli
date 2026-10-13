#!/usr/bin/env python3
"""Run an explicit offline session baseline in a disposable user environment.

``REGRESSION_TESTS`` lists reviewed public tests. The baseline uses synthetic
sessions and in-memory models, and rejects unexpected network connections.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NEW_TESTS = "tests/session/baseline"
REGRESSION_TESTS = (
    "tests/services/test_file_session.py",
    "tests/services/test_session_management_sync.py",
    "tests/services/goal/test_goal_storage.py",
    "tests/services/goal/test_models.py",
    "tests/tools/todo/test_recovery.py",
    "tests/tools/todo/test_todo_write_tool.py",
    "tests/support/test_resume_goal_state.py",
    "tests/support/test_resume_subagent_state.py",
    "tests/support/test_message_classifier.py",
    "tests/support/test_apply_patch_history_preview.py",
    "tests/support/test_chat_compat_items.py",
    "tests/support/test_effort_model_carry_over.py",
    "tests/session/test_telemetry_history_roles.py",
    "tests/agent_hub/hooks/test_todo_reminder_processor.py",
    "tests/agent_hub/hooks/test_todo_reminder_injection.py",
    "tests/agent_hub/hooks/test_repeated_tool_reminder_processor.py",
    "tests/agent_hub/context_filter/test_compaction_strategy_base.py",
    "tests/agent_hub/context_filter/test_compaction_notifications.py",
    "tests/agent_hub/context_filter/test_compaction_native_patch.py",
    "tests/agent_hub/context_filter/test_turn_prune_compaction_strategy.py",
    "tests/agent_hub/context_filter/test_header_summary_parallel_toolcall_bug.py",
    "tests/agent_hub/context_filter/test_goal_reminder_after_compaction.py",
    "tests/agent_hub/context_filter/test_fix_tool_message_ordering.py",
    "tests/agent_hub/context_filter/test_pending_user_input_filter.py",
    "tests/agent_hub/context_filter/test_pending_user_input_image_guard.py",
    "tests/tools/agent/test_sub_agent_compaction_filter.py",
    "tests/tools/agent/test_sub_agent_compaction_e2e.py",
    "tests/tools/agent/test_sub_agent_notifier.py",
    "tests/tools/agent/test_subagent_async.py",
    "tests/tools/agent/test_subagent_persistence.py",
    "tests/tools/agent/test_subagent_recursion.py",
    "tests/entrypoint/runtime/test_turn_event.py",
)


class OfflineGuard:
    """Fail even when application error handling swallows a network attempt."""

    def __init__(self):
        self.attempts = 0
        self.patch = None

    def pytest_sessionstart(self, session):
        import pytest

        self.patch = pytest.MonkeyPatch()

        def deny(*args, **kwargs):
            self.attempts += 1
            raise RuntimeError("Network connections are prohibited in the session baseline")

        self.patch.setattr(socket.socket, "connect", deny)
        self.patch.setattr(socket.socket, "connect_ex", deny)
        self.patch.setattr(socket, "create_connection", deny)

    def pytest_sessionfinish(self, session, exitstatus):
        if self.patch is not None:
            self.patch.undo()
        if self.attempts:
            import pytest

            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter):
        if self.attempts:
            terminalreporter.write_sep("!", f"Blocked {self.attempts} unexpected network attempts", red=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("new", "full"), default="full")
    parser.add_argument("--list", action="store_true", help="List selected paths without importing project code")
    args, pytest_args = parser.parse_known_args()
    selected = [REPO_ROOT / NEW_TESTS]
    if args.scope == "full":
        selected.extend(REPO_ROOT / path for path in REGRESSION_TESTS)
    if args.list:
        print("\n".join(str(path) for path in selected))
        return 0
    missing = [str(path) for path in selected if not path.exists()]
    if missing:
        parser.error("Baseline paths are missing: " + ", ".join(missing))
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    # Set HOME before project imports: several modules bind SIADA_HOME at import time.
    with tempfile.TemporaryDirectory(prefix="siada-session-baseline-") as sandbox:
        previous = dict(os.environ)
        os.environ.update({
            "HOME": sandbox,
            "SIADA_CLI_LOG_DIR": str(Path(sandbox) / "logs"),
            "XDG_CACHE_HOME": str(Path(sandbox) / "cache"),
            "SIADA_REMOTE_MODEL_CONFIG": "0",
        })
        previous_path = list(sys.path)
        try:
            sys.path.insert(0, str(REPO_ROOT))
            import pytest

            return int(pytest.main(
                [*(str(path) for path in selected), "-q", "--tb=short", "-rx", *pytest_args],
                plugins=[OfflineGuard()],
            ))
        finally:
            sys.path[:] = previous_path
            os.environ.clear()
            os.environ.update(previous)


if __name__ == "__main__":
    raise SystemExit(main())