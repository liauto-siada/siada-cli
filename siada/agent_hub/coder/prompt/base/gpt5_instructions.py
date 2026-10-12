"""Compatibility imports for GPT-5 prompt text and model-name predicates."""

from ..models.gpt5.instructions import (
    PERSONALITY_FRIENDLY,
    PERSONALITY_PRAGMATIC,
    get_gpt5_editing_constraints,
    get_gpt5_extra_sections,
    get_gpt5_formatting_section,
    get_gpt5_frontend_section,
    get_gpt5_intro,
)
from ..selection.model_features import (
    _gpt_main_version,
    is_gpt5_model,
    is_gpt5_or_newer_model,
    uses_native_patch_file_tools,
)
