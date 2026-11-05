"""Shared token threshold for automatic context compaction."""

COMPACTION_HEADROOM_TOKENS = 60_000
COMPACTION_FIXED_HEADROOM_MAX_WINDOW = 500_000


def get_compaction_threshold_rule(context_window: int) -> str:
    """Name the shared policy for content-free decision diagnostics."""
    return "fixed_60k" if context_window <= COMPACTION_FIXED_HEADROOM_MAX_WINDOW else "window_75_percent"


def get_compaction_token_threshold(context_window: int) -> int:
    """Reserve 60k through 500k; above 500k trigger at 75% utilization."""
    if context_window > COMPACTION_FIXED_HEADROOM_MAX_WINDOW:
        # Round upward so an integer count cannot trigger before 75% usage.
        return (context_window * 3 + 3) // 4
    return max(0, context_window - COMPACTION_HEADROOM_TOKENS)
