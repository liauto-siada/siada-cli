"""Shared token threshold for automatic context compaction."""

COMPACTION_HEADROOM_TOKENS = 60_000


def get_compaction_token_threshold(context_window: int) -> int:
    """Trigger with at most 60k tokens remaining, including small windows."""
    return max(0, context_window - COMPACTION_HEADROOM_TOKENS)