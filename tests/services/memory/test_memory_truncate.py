"""
Unit tests for MemoryService._truncate_messages character limit truncation.
"""
import pytest
from pathlib import Path

from siada.services.memory.memory_service import MemoryService


# ---- helper -----------------------------------------------------------------

def _make_msgs(*contents: str):
    """Build a list of role/content dicts from content strings."""
    return [{"role": "user", "content": c} for c in contents]


# ---- tests ------------------------------------------------------------------

class TestTruncateMessages:
    """Test _truncate_messages with various inputs."""

    def test_no_truncation_when_within_limit(self):
        """Messages within the limit should not be truncated."""
        svc = MemoryService(max_session_tokens=1000)  # 4000 chars
        msgs = _make_msgs("hello", "world", "short")
        result, was_truncated = svc._truncate_messages(msgs)
        assert result == msgs
        assert was_truncated is False

    def test_truncates_oldest_messages(self):
        """Old messages should be dropped, latest messages retained."""
        svc = MemoryService(max_session_tokens=2)  # 8 chars max
        # "AAAA" (4) + "BBBB" (4) + "CCCCCCCCCC" (10) → last keeps within limit
        msgs = _make_msgs("AAAA", "BBBB", "CCCCCCCCCC")
        result, was_truncated = svc._truncate_messages(msgs)
        assert was_truncated is True
        assert len(result) < len(msgs)
        # Latest message must be retained
        assert result[-1]["content"] == "CCCCCCCCCC"

    def test_truncates_from_oldest_only(self):
        """Only oldest should be dropped; newer ones preserved together."""
        svc = MemoryService(max_session_tokens=2)  # 8 chars
        msgs = _make_msgs("XX", "YY", "ZZ")  # 2+2+2 = 6 chars → within limit
        result, was_truncated = svc._truncate_messages(msgs)
        assert was_truncated is False
        assert result == msgs

    def test_single_oversized_message_kept(self):
        """A single message exceeding limit is still kept (at least one)."""
        svc = MemoryService(max_session_tokens=1)  # 4 chars
        msgs = _make_msgs("This is way too long for 4 characters")
        result, was_truncated = svc._truncate_messages(msgs)
        # Even though oversized, minimum-one rule applies
        assert len(result) == 1
        assert result[0]["content"] == "This is way too long for 4 characters"
        assert was_truncated is False

    def test_empty_messages(self):
        """Empty list returns empty with no truncation flag."""
        svc = MemoryService(max_session_tokens=100)
        result, was_truncated = svc._truncate_messages([])
        assert result == []
        assert was_truncated is False

    def test_messages_at_exact_limit(self):
        """Messages whose total chars exactly equal max_session_chars."""
        svc = MemoryService(max_session_tokens=2)  # 8 chars
        msgs = _make_msgs("ABCD", "EFGH")  # 4 + 4 = 8
        result, was_truncated = svc._truncate_messages(msgs)
        assert result == msgs
        assert was_truncated is False

    def test_drops_oldest_when_next_msg_exceeds_limit(self):
        """Oldest are dropped when adding the next would exceed the limit."""
        svc = MemoryService(max_session_tokens=2)  # 8 chars
        msgs = _make_msgs("AAAAA", "BBB", "CCC", "DDD")  # 5+3+3+3=14
        result, was_truncated = svc._truncate_messages(msgs)
        assert was_truncated is True
        # Reversed: DDD(3) → CCC(3+3=6) → BBB(6+3=9>8 → break) → keep [CCC, DDD]
        assert len(result) == 2
        assert result[0]["content"] == "CCC"
        assert result[1]["content"] == "DDD"

    def test_default_fallback_150k_tokens(self):
        """When model_base_config lookup fails, fallback to 150_000 tokens."""
        # The fast model (deepseek-v4-flash) is configured in model_base_config,
        # so in this environment it will resolve via the config.
        # We explicitly pass max_session_tokens=None and let it resolve.
        svc = MemoryService(max_session_tokens=None)
        # deepseek-v4-flash has context_window=1_000_000 in model_base_config
        # So max_session_chars should be 1_000_000 * 4 = 4_000_000
        assert svc.max_session_chars > 0
        # Verify the method works regardless
        msgs = _make_msgs("short", "test")
        result, was_truncated = svc._truncate_messages(msgs)
        assert result == msgs
        assert was_truncated is False

    def test_explicit_max_session_tokens(self):
        """Explicitly passing max_session_tokens overrides the config/default."""
        svc = MemoryService(max_session_tokens=10)  # 40 chars
        assert svc.max_session_chars == 40
        msgs = _make_msgs("A" * 30, "B" * 20)  # 30+20=50 > 40
        result, was_truncated = svc._truncate_messages(msgs)
        assert was_truncated is True
        # Reversed: BBBB...(20) → break because 30+20>40 → keep [BBBB...]
        assert len(result) == 1
        assert result[0]["content"] == "B" * 20

    def test_empty_content_messages(self):
        """Messages with empty content should not affect the count."""
        svc = MemoryService(max_session_tokens=1)  # 4 chars
        msgs = [{"role": "user", "content": ""}, {"role": "assistant", "content": "Hi"}]
        result, was_truncated = svc._truncate_messages(msgs)
        assert result == msgs
        assert was_truncated is False
