"""Public rule entry points and model-profile dispatch."""

from typing import Optional

from ...models.default.rules import _get_default_rules_section
from ...models.glm.rules import _get_glm_rules_section
from ...models.gpt5.rules import _get_gpt5_rules_section
from ...models.gpt6.rules import _get_gpt6_rules_section
from ...selection.profiles import PromptFamily, PromptProfile, resolve_prompt_profile


def get_rules_section(cwd: str, os_name: str, home_dir: str, interactive_mode: bool = True,
                      model_name: Optional[str] = None) -> str:
    """
    Get the RULES section content.

    The selected family renderer owns behavioural and tone constraints. Capability
    listings belong to capabilities.py, avoiding duplicate or conflicting rules.

    Args:
        cwd: Current working directory path.
        os_name: Operating system name.
        home_dir: User home directory path.
        interactive_mode: Whether running in interactive mode.
        model_name: Model name, used to tailor rules for GPT-5, GPT-6 and
            GLM-5.2-and-later models.

    Returns:
        str: The RULES section text content.
    """
    return get_rules_for_profile(
        cwd, os_name, home_dir, interactive_mode,
        profile=resolve_prompt_profile(model_name),
    )


def get_rules_for_profile(cwd: str, os_name: str, home_dir: str, interactive_mode: bool,
                          *, profile: PromptProfile) -> str:
    """Render rules for the already-selected coding prompt profile."""
    if profile.family is PromptFamily.GPT6:
        return _get_gpt6_rules_section(cwd, os_name, home_dir, interactive_mode)
    if profile.family is PromptFamily.GPT5:
        return _get_gpt5_rules_section(cwd, os_name, home_dir, interactive_mode)
    if profile.family is PromptFamily.GLM:
        return _get_glm_rules_section(cwd, os_name, home_dir, interactive_mode)
    return _get_default_rules_section(cwd, os_name, home_dir, interactive_mode)
