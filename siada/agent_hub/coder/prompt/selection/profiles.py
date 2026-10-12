"""Select coding prompt content without coupling it to the file-tool protocol.

To add a family, select it here, supply its intro/objective and rules renderers,
and configure optional sections here. The formatter needs no model-specific code.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from siada.services.skills.models import SkillUsageProfile

from ..models.gpt5.instructions import get_gpt5_extra_sections
from .model_features import (
    is_gpt5_model,
    is_gpt6_model,
    is_kimi_k3_or_newer_model,
    uses_glm_prompt_profile,
    uses_native_patch_file_tools,
)


class PromptFamily(Enum):
    DEFAULT = "default"
    GPT5 = "gpt5"
    GPT6 = "gpt6"
    GLM = "glm"
    KIMI_K3 = "kimi_k3"


@dataclass(frozen=True)
class PromptProfile:
    """Instructions and independent tool/skills capabilities for one model.

    Carries the model name that produced it so per-model decisions below the
    family level (such as the GPT-6 writing-style split) never depend on a
    separately threaded name that could disagree with the resolved family.
    """

    model_name: str | None
    family: PromptFamily
    skill_usage_profile: SkillUsageProfile
    native_patch_file_tools: bool
    extra_sections: Callable[[], str] | None


def resolve_prompt_profile(model_name: str | None) -> PromptProfile:
    """Resolve the profile once; later GPT models may have a different tool surface."""
    if is_gpt6_model(model_name):
        family = PromptFamily.GPT6
    elif is_gpt5_model(model_name or ""):
        family = PromptFamily.GPT5
    elif uses_glm_prompt_profile(model_name):
        family = PromptFamily.GLM
    elif is_kimi_k3_or_newer_model(model_name):
        family = PromptFamily.KIMI_K3
    else:
        family = PromptFamily.DEFAULT

    return PromptProfile(
        model_name=model_name,
        family=family,
        skill_usage_profile=(
            SkillUsageProfile.GPT6 if family is PromptFamily.GPT6 else SkillUsageProfile.STRICT
        ),
        native_patch_file_tools=uses_native_patch_file_tools(model_name),
        extra_sections=get_gpt5_extra_sections if family is PromptFamily.GPT5 else None,
    )
