"""Deprecated stub kept only to preserve the import surface.

The original ``get_memory_section`` returned a static "Memory Usage
Instructions" block written for an older experience-model + events-feed
system that no longer exists. The text was unrelated to the current
``memory`` and ``fact_store`` tools and just consumed system-prompt
tokens.

The block is no longer assembled into ``combined_memory`` (see
``SiadaRunner._build_combined_memory``). Memory guidance now ships via
``_MEMORY_GUIDANCE`` (inline tool) and ``_HOLOGRAPHIC_GUIDANCE_TEMPLATE``
(structured fact tool) when the corresponding store/provider is active.

We keep this function as an empty-string stub instead of deleting the
module so that any third-party / vendored caller that still imports it
keeps working without a hard ImportError.
"""


def get_memory_section() -> str:
    """Return empty string. Retained only to avoid breaking older imports.

    Intentionally returns an empty string so callers that still
    ``memory_parts.append(get_memory_section())`` produce no extra
    tokens in the system prompt.

    Returns:
        Empty string.
    """
    return ""
