"""
Unit tests for SubTaskAgent's opt-in ``include_run_subtask`` tool inclusion
(recursive sub-agent mode) and the matching prompt hint.
"""
import unittest

from siada.agent_hub.coder.sub_task_agent import (
    SubTaskAgent,
    _build_default_tools,
)


class TestBuildDefaultTools(unittest.TestCase):
    def test_run_subtask_excluded_by_default(self):
        tools = _build_default_tools()
        names = {getattr(t, "name", None) for t in tools}
        self.assertNotIn("run_subtask", names)

    def test_run_subtask_included_when_requested(self):
        tools = _build_default_tools(include_run_subtask=True)
        names = {getattr(t, "name", None) for t in tools}
        self.assertIn("run_subtask", names)


class TestSubTaskAgentIncludeRunSubtask(unittest.TestCase):
    def test_default_agent_has_no_run_subtask_tool(self):
        agent = SubTaskAgent()
        names = {getattr(t, "name", None) for t in agent.tools}
        self.assertNotIn("run_subtask", names)
        self.assertFalse(agent.include_run_subtask)

    def test_recursive_agent_has_run_subtask_tool(self):
        agent = SubTaskAgent(include_run_subtask=True)
        names = {getattr(t, "name", None) for t in agent.tools}
        self.assertIn("run_subtask", names)
        self.assertTrue(agent.include_run_subtask)

    def test_fork_tools_verbatim_ignores_include_run_subtask(self):
        # When fork_tools is explicitly supplied, it wins verbatim over
        # _build_default_tools -- include_run_subtask only affects the
        # non-fork path's tool construction and the prompt hint flag.
        agent = SubTaskAgent(fork_tools=["already_has_run_subtask"], include_run_subtask=True)
        self.assertEqual(agent.tools, ["already_has_run_subtask"])
        self.assertTrue(agent.include_run_subtask)


if __name__ == "__main__":
    unittest.main(verbosity=2)
