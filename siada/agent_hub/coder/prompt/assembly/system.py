from collections.abc import Callable

from ..models.gpt6.multi_agent import EXPLICIT_REQUEST_ONLY
from ..selection.model_features import is_gpt6_or_newer_model
from ..selection.profiles import PromptFamily, PromptProfile
from .codex import render_codex_system_prompt
from .context import SystemPromptContext
from .deepseek import render_deepseek_system_prompt
from .glm import render_glm_system_prompt
from .kimi import render_kimi_system_prompt
from .legacy import render_legacy_system_prompt


_RENDERERS: dict[PromptFamily, Callable[[PromptProfile, SystemPromptContext], str]] = {
    PromptFamily.DEFAULT: render_legacy_system_prompt,
    PromptFamily.GPT5: render_legacy_system_prompt,
    PromptFamily.GPT6: render_codex_system_prompt,
    PromptFamily.GLM: render_glm_system_prompt,
    PromptFamily.KIMI_K3: render_kimi_system_prompt,
    PromptFamily.DEEPSEEK: render_deepseek_system_prompt,
}


def render_coding_system_prompt(profile: PromptProfile, context: SystemPromptContext) -> str:
    prompt = _RENDERERS[profile.family](profile, context)
    # GLM, Kimi, and DeepSeek historically returned before the GPT delegation suffix.
    if (
        context.subagent_enabled
        and profile.family in (PromptFamily.DEFAULT, PromptFamily.GPT5, PromptFamily.GPT6)
        and is_gpt6_or_newer_model(profile.model_name)
    ):
        separator = "\n" if profile.family is PromptFamily.GPT6 else "\n\n"
        prompt += f"{separator}# Delegation\n\n{EXPLICIT_REQUEST_ONLY}\n"
    return prompt
