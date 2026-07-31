"""
Tests for ConversationTurn._has_active_goal, used to suppress the generic
per-turn "waiting for input" system notification while a /goal task is
still being auto-retried by the verifier loop.
"""
from types import SimpleNamespace
from unittest.mock import patch

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn


def _make_turn(workspace="/ws"):
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(workspace=workspace)
    return turn


def _context_cache_with(workspace, goal):
    context = SimpleNamespace(goal=goal)
    return {("agent", workspace): context}


class TestHasActiveGoal:
    def test_false_when_no_context_for_workspace(self):
        turn = _make_turn("/ws")
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
            assert turn._has_active_goal() is False

    def test_false_when_context_has_no_goal(self):
        turn = _make_turn("/ws")
        fake_cache = _context_cache_with("/ws", None)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            assert turn._has_active_goal() is False

    def test_true_when_goal_active(self):
        turn = _make_turn("/ws")
        goal = SimpleNamespace(status="active")
        fake_cache = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            assert turn._has_active_goal() is True

    def test_false_when_goal_complete(self):
        turn = _make_turn("/ws")
        goal = SimpleNamespace(status="complete")
        fake_cache = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            assert turn._has_active_goal() is False

    def test_false_when_goal_blocked(self):
        turn = _make_turn("/ws")
        goal = SimpleNamespace(status="blocked")
        fake_cache = _context_cache_with("/ws", goal)
        with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
            assert turn._has_active_goal() is False

    def test_false_on_lookup_error(self):
        """Any unexpected error resolving context must fail safe (False),
        never block/crash the notification path."""
        turn = _make_turn("/ws")

        class _BoomDict(dict):
            def items(self):
                raise RuntimeError("boom")

        with patch("siada.services.siada_runner.SiadaRunner._context_cache", _BoomDict()):
            assert turn._has_active_goal() is False
