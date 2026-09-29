"""
Unit tests for the sub-agent recursion guard (siada.tools.agent.subagent_guard).
"""
import unittest

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.agent.subagent_guard import (
    DISABLED_FOR_SUBAGENT,
    is_blocked_for_subagent,
    rejection_message_for,
)


class TestSubagentGuard(unittest.TestCase):
    def test_run_subtask_is_on_disabled_list(self):
        self.assertIn("run_subtask", DISABLED_FOR_SUBAGENT)

    def test_blocked_when_is_subagent_true_and_tool_disabled(self):
        ctx = CodeAgentContext(is_subagent=True)
        self.assertTrue(is_blocked_for_subagent("run_subtask", ctx))

    def test_not_blocked_when_is_subagent_false(self):
        ctx = CodeAgentContext(is_subagent=False)
        self.assertFalse(is_blocked_for_subagent("run_subtask", ctx))

    def test_not_blocked_when_tool_not_on_disabled_list(self):
        ctx = CodeAgentContext(is_subagent=True)
        self.assertFalse(is_blocked_for_subagent("edit_file", ctx))

    def test_not_blocked_when_context_is_none(self):
        # Direct-call test paths (agent_context=None) must not be blocked.
        self.assertFalse(is_blocked_for_subagent("run_subtask", None))

    def test_rejection_message_mentions_tool_name(self):
        msg = rejection_message_for("run_subtask")
        self.assertIn("run_subtask", msg)

    # ---- allow_recursive_subagents=True: depth-aware behaviour ----

    def test_recursive_mode_depth_1_subagent_is_not_blocked(self):
        # A depth-1 sub-agent must be ALLOWED to call run_subtask when
        # recursion is enabled, so it can spawn its own depth-2 sub-sub-agent.
        ctx = CodeAgentContext(
            is_subagent=True, allow_recursive_subagents=True, subagent_depth=1,
        )
        self.assertFalse(is_blocked_for_subagent("run_subtask", ctx))

    def test_recursive_mode_depth_2_subagent_is_blocked(self):
        # A depth-2 sub-sub-agent is at the nesting cap and must be BLOCKED.
        ctx = CodeAgentContext(
            is_subagent=True, allow_recursive_subagents=True, subagent_depth=2,
        )
        self.assertTrue(is_blocked_for_subagent("run_subtask", ctx))

    def test_recursive_mode_off_still_blocks_regardless_of_depth(self):
        # allow_recursive_subagents defaults to False -- legacy behaviour
        # (always blocked for any sub-agent) must be preserved exactly, even
        # if subagent_depth happens to be 1.
        ctx = CodeAgentContext(
            is_subagent=True, allow_recursive_subagents=False, subagent_depth=1,
        )
        self.assertTrue(is_blocked_for_subagent("run_subtask", ctx))


if __name__ == "__main__":
    unittest.main(verbosity=2)
