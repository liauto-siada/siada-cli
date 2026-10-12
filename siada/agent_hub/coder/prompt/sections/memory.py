"""Combined-memory framing for system prompts."""

# Outer section title wrapping the whole combined-memory snapshot at the
# system-prompt injection point. Kept here — next to the main injection
# path — so side agents can reuse the exact
# same framing via ``wrap_user_memory`` instead of inventing ad-hoc
# prefixes like "User Memory:".
MEMORY_SECTION_TITLE = "Combined Memory"


def wrap_user_memory(user_memory: str) -> str:
    """Wrap the combined-memory snapshot in a titled ``====`` section.

    ``combined_memory`` is session-stable (built once at session start and
    rebuilt only after context compaction), so adding this wrapper does
    not hurt prompt-prefix caching stability.

    Args:
        user_memory: Assembled combined-memory content.

    Returns:
        The memory content wrapped in a ``====`` bounded section titled
        ``Combined Memory``.
    """
    return f"====\n# {MEMORY_SECTION_TITLE}\n\n{user_memory.strip()}\n===="
