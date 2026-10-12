"""Model-name predicates shared by prompts and tool registration."""

import re
from typing import Optional

from siada.models.model_base_config import is_glm_5_2_or_newer
from siada.services.skills.models import SkillUsageProfile


_GPT_MAIN_VERSION_PATTERN = re.compile(r"(?:^|[^a-z0-9])gpt[-_]?([0-9]+)(?:[^0-9]|$)")


def _gpt_main_version(model_name: Optional[str]) -> int | None:
    """Extract a numbered GPT generation from a provider-qualified name."""
    if not model_name:
        return None
    match = _GPT_MAIN_VERSION_PATTERN.search(str(model_name).lower())
    return int(match.group(1)) if match else None


def is_gpt5_model(model_name: str) -> bool:
    return _gpt_main_version(model_name) == 5


def is_gpt5_or_newer_model(model_name: str | None) -> bool:
    version = _gpt_main_version(model_name)
    return version is not None and version >= 5


def is_astra_model(model_name: Optional[str]) -> bool:
    """Only a token-bounded Astra alias without a conflicting GPT major is GPT-6."""
    if not model_name:
        return False
    version = _gpt_main_version(model_name)
    if version not in (None, 6):
        return False
    tokens = re.split(r"[-_.\s/]+", str(model_name).lower())
    return "astra" in tokens


def is_gpt6_model(model_name: Optional[str]) -> bool:
    return _gpt_main_version(model_name) == 6 or is_astra_model(model_name)


_GPT6_MINOR_REVISION_PATTERN = re.compile(r"gpt[-_]?6\.(\d+)")


def uses_gpt6_scannable_writing_style(model_name: Optional[str]) -> bool:
    """GPT-6 Sol and Luna use the first-read writing style.

    Codex ships those models with instructions that minimize cognitive load,
    while Astra and later numbered Sol revisions (6.1+) keep the
    connected-prose template. Siada mirrors that split so terminal answers
    stay scannable on the models users reported as hard to read.
    """
    if not is_gpt6_model(model_name):
        return False
    lowered = str(model_name).lower()
    tokens = set(re.split(r"[-_.\s/]+", lowered))
    if not tokens & {"sol", "luna"}:
        return False
    return _GPT6_MINOR_REVISION_PATTERN.search(lowered) is None


def uses_native_patch_file_tools(model_name: str | None) -> bool:
    """GPT-5+ and the Astra alias use native read/patch tools."""
    return is_gpt6_model(model_name) or is_gpt5_or_newer_model(model_name)


_KIMI_MAIN_VERSION_PATTERN = re.compile(
    r"(?:(?:^|[^a-z0-9])kimi[-_/]|(?:^|/))"
    r"k([0-9]+)(?:\.[0-9]+)*(?=$|[^a-z0-9.])"
)


def is_kimi_k3_or_newer_model(model_name: str | None) -> bool:
    """Recognize K3+ names, including bare and slash-qualified K aliases."""
    if not model_name or _gpt_main_version(model_name) is not None:
        return False
    match = _KIMI_MAIN_VERSION_PATTERN.search(str(model_name).lower())
    return match is not None and int(match.group(1)) >= 3


def is_glm_profile_model(model_name: Optional[str]) -> bool:
    return bool(model_name) and is_glm_5_2_or_newer(str(model_name))


def uses_glm_prompt_profile(model_name: Optional[str]) -> bool:
    return is_glm_profile_model(model_name)


def uses_glm_repeated_tool_reminder(model_name: Optional[str]) -> bool:
    return is_glm_profile_model(model_name)


def resolve_skill_usage_profile(model_name: Optional[str]) -> SkillUsageProfile:
    return SkillUsageProfile.GPT6 if is_gpt6_model(model_name) else SkillUsageProfile.STRICT
