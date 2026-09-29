"""
Unit tests for the recursive sub-agent depth + concurrency policy
(siada.tools.agent.subagent_recursion).
"""
import unittest
import uuid

from siada.tools.agent.subagent_recursion import (
    MAX_CONCURRENT_AGENTS,
    MAX_NESTING_DEPTH,
    alive_count,
    check_can_spawn,
    register_alive,
    release_alive,
)


class TestDepthCap(unittest.TestCase):
    def test_main_agent_spawning_a_subagent_is_allowed(self):
        decision = check_can_spawn(parent_depth=0, root_session_id=None)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.child_depth, 1)

    def test_subagent_spawning_a_sub_subagent_is_allowed(self):
        decision = check_can_spawn(parent_depth=1, root_session_id=None)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.child_depth, 2)

    def test_sub_subagent_spawning_further_is_rejected(self):
        decision = check_can_spawn(parent_depth=MAX_NESTING_DEPTH, root_session_id=None)
        self.assertFalse(decision.allowed)
        self.assertIn("Nesting depth", decision.reason)

    def test_max_nesting_depth_is_two(self):
        self.assertEqual(MAX_NESTING_DEPTH, 2)


class TestConcurrencyCap(unittest.TestCase):
    def setUp(self):
        self.session_id = f"test-session-{uuid.uuid4().hex[:8]}"

    def test_alive_count_starts_at_zero(self):
        self.assertEqual(alive_count(self.session_id), 0)

    def test_register_and_release_round_trip(self):
        register_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 1)
        register_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 2)
        release_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 1)
        release_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 0)

    def test_release_below_zero_is_a_noop_floor(self):
        release_alive(self.session_id)
        release_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 0)

    def test_spawn_rejected_once_cap_reached(self):
        # The cap counts: 1 (main agent) + currently-alive non-main agents +
        # 1 (the new agent about to be spawned) <= MAX_CONCURRENT_AGENTS.
        # So the largest "currently alive" count that still allows one more
        # spawn is MAX_CONCURRENT_AGENTS - 2 (1 + (MAX-2) + 1 == MAX).
        for _ in range(MAX_CONCURRENT_AGENTS - 2):
            register_alive(self.session_id)

        # main(1) + alive(MAX-2) + new(1) == MAX -> still allowed
        decision = check_can_spawn(parent_depth=0, root_session_id=self.session_id)
        self.assertTrue(decision.allowed)
        register_alive(self.session_id)

        # main(1) + alive(MAX-1) + new(1) == MAX+1 -> rejected
        decision = check_can_spawn(parent_depth=0, root_session_id=self.session_id)
        self.assertFalse(decision.allowed)
        self.assertIn("Maximum concurrent agent count", decision.reason)

        for _ in range(MAX_CONCURRENT_AGENTS - 1):
            release_alive(self.session_id)
        self.assertEqual(alive_count(self.session_id), 0)

    def test_concurrency_check_skipped_when_root_session_id_is_none(self):
        # Fail-open when there's no session to track against (e.g. bare
        # RunContextWrapper in some test paths) -- only the depth check applies.
        decision = check_can_spawn(parent_depth=0, root_session_id=None)
        self.assertTrue(decision.allowed)

    def test_default_max_concurrent_agents_is_twelve(self):
        self.assertEqual(MAX_CONCURRENT_AGENTS, 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
