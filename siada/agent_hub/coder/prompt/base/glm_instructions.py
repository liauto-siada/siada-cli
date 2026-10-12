"""Compatibility imports for GLM text and profile predicates."""

from ..models.glm.instructions import GLM_INTRO, get_glm_intro
from ..selection.model_features import (
    is_glm_profile_model,
    uses_glm_prompt_profile,
    uses_glm_repeated_tool_reminder,
)
