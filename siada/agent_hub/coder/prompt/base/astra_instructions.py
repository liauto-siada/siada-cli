"""Compatibility imports for the former Astra-specific prompt module."""

from .gpt6_instructions import PERSONALITY_GPT6, get_gpt6_intro
from .skill_usage_profiles import is_astra_model, is_gpt6_model

PERSONALITY_ASTRA = PERSONALITY_GPT6

__all__ = [
    "get_gpt6_intro",
    "get_astra_intro",
    "is_gpt6_model",
    "is_astra_model",
    "PERSONALITY_GPT6",
    "PERSONALITY_ASTRA",
]


def get_astra_intro(personality: str = "astra") -> str:
    """Preserve the Astra-named API for existing callers."""
    return get_gpt6_intro(personality)
