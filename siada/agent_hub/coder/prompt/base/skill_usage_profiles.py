"""Model-family selection for skills usage instructions."""

import re
from typing import Optional

from siada.services.skills.models import SkillUsageProfile


_GPT_MAIN_VERSION_PATTERN = re.compile(r"(?:^|[^a-z0-9])gpt[-_]?([0-9]+)(?:[^0-9]|$)")


def _gpt_main_version(model_name: Optional[str]) -> int | None:
    """Extract a numbered GPT generation from a provider-qualified name."""
    if not model_name:
        return None
    match = _GPT_MAIN_VERSION_PATTERN.search(str(model_name).lower())
    return int(match.group(1)) if match else None


def is_astra_model(model_name: Optional[str]) -> bool:
    """Whether a name selects the Astra compatibility alias for GPT-6.

    Names are split into tokens instead of searched as arbitrary substrings,
    preventing unrelated names such as ``astral-projection`` from selecting
    GPT-6 prompt behavior. A name that declares another numbered GPT major
    version is governed by that version, even if a provider happens to retain
    ``astra`` in its suffix (for example, ``gpt-7-astra``).
    """
    if not model_name:
        return False
    version = _gpt_main_version(model_name)
    if version not in (None, 6):
        return False
    tokens = re.split(r"[-_.\s/]+", str(model_name).lower())
    return "astra" in tokens


def is_gpt6_model(model_name: Optional[str]) -> bool:
    """Whether a model uses GPT-6's judgement-first prompt profile.

    Astra is one GPT-6 variant and is also accepted as a short model alias.
    Keep the exact-major-version check deliberately narrow: future GPT-7
    models should opt into their own prompt profile explicitly rather than
    inheriting GPT-6 instructions by accident.
    """
    return _gpt_main_version(model_name) == 6 or is_astra_model(model_name)


def resolve_skill_usage_profile(model_name: Optional[str]) -> SkillUsageProfile:
    """Choose the skills catalog profile for a model name."""
    if is_gpt6_model(model_name):
        return SkillUsageProfile.GPT6
    return SkillUsageProfile.STRICT
