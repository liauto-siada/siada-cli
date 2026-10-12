"""Compatibility imports; system-prompt assembly lives in assembly.builder."""

from ..assembly.builder import (
    MEMORY_SECTION_TITLE,
    _get_language_instruction,
    build_system_prompt,
    render_system_prompt,
    wrap_user_memory,
)
from ..selection.profiles import resolve_prompt_profile
