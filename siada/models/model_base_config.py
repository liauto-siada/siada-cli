import logging
import re
from dataclasses import dataclass
from typing import Optional, List


logger = logging.getLogger(__name__)

_user_model_settings: Optional[List['ModelBaseConfig']] = None

# Reasoning effort levels accepted by most models that support reasoning_effort.
VALID_REASONING_EFFORTS = ("low", "medium", "high")

# Additional effort levels only Claude models accept (sent via output_config.effort).
CLAUDE_EXTRA_EFFORTS = ("xhigh", "max")

# Reasoning effort ladder of the GPT-5-and-newer family (gpt-5.x, gpt-6-astra):
# the openai-protocol ladder keeps "medium" and extends past "high" with
# "max". Unlike the ladder of the domestic families (low/high/max) it does
# not include "xhigh".
GPT_EXTENDED_REASONING_EFFORTS = ("low", "medium", "high", "max")

@dataclass
class ModelBaseConfig:
    """
    Represents the configuration for a specific language model.
    """
    model_name: str
    context_window: int
    max_tokens: Optional[int] = None
    supports_images: bool = False
    # Bridged vision (modlens-style): the model itself is text-only — the
    # gateway silently drops image parts, so native multimodal input must stay
    # OFF (supports_images=False). Instead, attached images are transcribed
    # into text evidence by a vision-capable engine model (see
    # siada/services/vision_bridge.py) and the evidence is fed to this model.
    supports_vision_bridge: bool = False
    supports_prompt_cache: bool = False

    parallel_tool_calls: Optional[bool] = None

    supports_extra_params: Optional[List[str]] = None

    # Default thinking token budget for models that support thinking.
    # When set, thinking is enabled by default without needing --thinking-tokens flag.
    # Use -1 for adaptive thinking mode (e.g., Claude 4.6+), positive int for budget mode.
    default_thinking_tokens: Optional[int] = None

    # Default reasoning effort level for models that support reasoning_effort.
    # Valid values: "low", "medium", "high" for most models; Claude models
    # additionally support "xhigh" and "max" (sent via output_config.effort).
    # When set, reasoning is enabled by default.
    default_reasoning_effort: Optional[str] = None

    # Optional pricing overrides (CNY per million tokens). Only meaningful for
    # user-defined models (provider == "default"); when set, they take priority
    # over the built-in MODEL_PRICING table in siada.models.model_pricing.
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_write_price: Optional[float] = None
    cache_read_price: Optional[float] = None

    # Optional remark shown next to the model name in model lists/selectors
    # (e.g. "free"). None means no remark.
    note: Optional[str] = None

    # Marks this model as the vision-bridge ENGINE (the image-capable model
    # that transcribes attached images into text evidence for text-only
    # models — see siada/services/vision_bridge.py). The first flagged model
    # in the settings list wins; must also have supports_images=True to be
    # selected.
    is_vision_engine_model: bool = False

# Fallback model when the configured model is not found in the settings
# list. Pinned by name so it does not depend on MODEL_SETTING ordering.
DEFAULT_MODEL_NAME = "claude-sonnet-5"

# Simple list of all model configurations, kept in alphabetical order by
# model_name (this is the display order in model lists/selectors).
MODEL_SETTING: List[ModelBaseConfig] = [
    ModelBaseConfig(
        model_name="claude-opus-5-5",
        max_tokens=32768 * 2,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4-6",
        max_tokens=8192 * 4,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_thinking_tokens=-1,  # -1 means adaptive thinking mode
        # Adaptive thinking effort, sent via output_config.effort.
        default_reasoning_effort="high",
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-5",
        max_tokens=8192 * 10,  # 80k output budget
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_thinking_tokens=-1,  # -1 means adaptive thinking mode
        # Adaptive thinking effort, sent via output_config.effort.
        # Sonnet 5 supports xhigh for the hardest agentic/coding tasks.
        default_reasoning_effort="high",
    ),
    ModelBaseConfig(
        model_name="deepseek-v4-pro",
        max_tokens=384_000,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        # DeepSeek controls thinking intensity by level, not a token budget:
        # {"reasoning_effort": "low|high|max"} (per official docs).
        default_reasoning_effort="high",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="deepseek-v4-pro-0813",
        max_tokens=384_000,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        # DeepSeek controls thinking intensity by level, not a token budget:
        # {"reasoning_effort": "low|high|max"} (per official docs).
        default_reasoning_effort="high",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="deepseek-v4.1-flash",
        max_tokens=384_000,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="max",
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="deepseek-v4-flash",
        max_tokens=384_000,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="high",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="gemini-3.5-flash",
        max_tokens=65535,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="glm-5.2",
        max_tokens=8192 * 8,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="glm-5.3",
        max_tokens=8192 * 8,
        context_window=1_000_000,
        parallel_tool_calls=True,
        # GLM-5.3 (official): always reasons via top-level reasoning_effort
        # (low/high/max, default max) with thinking.type="enabled" explicitly.
        # No thinking_tokens / disable / clear_thinking.
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="glm-5.3-flash",
        max_tokens=8192 * 8,
        context_window=1_000_000,
        parallel_tool_calls=True,
        # GLM-5.3 (official): always reasons via top-level reasoning_effort
        # (low/high/max, default max) with thinking.type="enabled" explicitly.
        # No thinking_tokens / disable / clear_thinking.
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="gpt-6-astra",
        max_tokens=32768 * 2,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="gpt-6-luna",
        max_tokens=32768 * 2,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="gpt-6-sol",
        max_tokens=32768 * 2,
        context_window=272_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="kimi-k3",
        # max_tokens=131_072,
        context_window=600_000,
        supports_images=True,
        # Capability confirmed: the model supports parallel tool calls; the
        # previous False value was a config leftover, not a capability limit.
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        # Kimi K3 always reasons; effort is configured via the top-level
        # reasoning_effort request field. Valid: low/high/max (no "medium").
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="qwen3.7-max",
        max_tokens=8192 * 4,
        context_window=600_000,
        parallel_tool_calls=True,
        # Qwen controls thinking intensity by level (reasoning_effort) instead
        # of a token budget: extra_body={"enable_thinking": True,
        # "reasoning_effort": "low|medium|xhigh"}, default "xhigh".
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="qwen3.7-plus",
        max_tokens=8192 * 4,
        context_window=131_072,
        # Capability confirmed against the provider (model id qwen3.7-plus):
        # the model actually reads images (verified with a synthetic-image
        # probe), so it serves as the vision engine for the deepseek-v4 vision
        # bridge.
        supports_images=True,
        parallel_tool_calls=True,
        # Qwen controls thinking intensity by level (reasoning_effort) instead
        # of a token budget: extra_body={"enable_thinking": True,
        # "reasoning_effort": "low|medium|xhigh"}, default "xhigh".
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
    ),
    ModelBaseConfig(
        model_name="qwen3.8-flash",
        max_tokens=8192 * 4,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="qwen3.8-max",
        max_tokens=8192 * 4,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
        supports_images=True,
    ),
]

# Anthropic prompt-cache default TTL is 5 minutes; OpenAI/DeepSeek implicit
# caches also typically expire on the order of minutes. Used as the universal
# heuristic for "the next request will hit the prompt cache".
PROMPT_CACHE_TTL_SECONDS = 4 * 60 + 30


def is_claude_model(model_name: str) -> bool:
    return "claude" in model_name.lower()

# Matches the major version in Claude model names in either ordering:
# family-first ("claude-sonnet-5", "claude-opus-5.1") or version-first
# ("claude-5-sonnet"). It is matched with re.search (not anchored), so
# provider-prefixed names like "aws-claude-sonnet-5", "bedrock/claude-opus-5"
# or "us.anthropic.claude-sonnet-5-20250929-v1:0" all match as well.
# Older "claude-3-5-sonnet"-style names do not match (their digit group is
# followed by another digit, not a letter family).
_CLAUDE_MAJOR_VERSION_PATTERN = re.compile(
    r"claude-(?:[a-z]+-(\d+)|(\d+)-[a-z]+)", re.IGNORECASE
)


def is_claude_5_or_newer(model_name: str) -> bool:
    """Whether the model is a 5th-generation or newer Claude model
    (e.g. claude-sonnet-5, claude-opus-5, claude-sonnet-5.5).

    Used as the integer-major floor of is_claude_4_6_or_newer(): a 5+ model
    is newer than 4.6 even when its name carries no minor version.
    """
    if not model_name:
        return False
    match = _CLAUDE_MAJOR_VERSION_PATTERN.search(model_name.lower())
    if not match:
        return False
    major = match.group(1) or match.group(2)
    return int(major) >= 5


# Matches "claude-<family>-<major><sep><minor>" and
# "claude-<major><sep><minor>-<family>" in either separator style ("." or
# "-"): claude-sonnet-4.6, claude-sonnet-4-6, claude-4.6-sonnet. The minor
# group is a single digit so date-suffixed names like
# claude-sonnet-4-20250514 do not parse as (4, 20250514). Matched with
# re.search (not anchored), so provider-prefixed variants (aws-claude-sonnet-4-6,
# anthropic/claude-opus-4.6, bedrock/claude-sonnet-4-6,
# us.anthropic.claude-sonnet-4-6-20250929-v1:0) all work. Old-style
# family-last names (claude-3-5-sonnet) parse as (3, 5).
_CLAUDE_MAJOR_MINOR_VERSION_PATTERN = re.compile(
    r"claude-(?:[a-z]+-(\d+)[.-](\d)|(\d+)[.-](\d)-[a-z]+)", re.IGNORECASE
)


def is_claude_4_6_or_newer(model_name: str) -> bool:
    """Whether the model is Claude 4.6 or newer (e.g. claude-sonnet-4.6,
    claude-sonnet-4-6-20250929, claude-sonnet-5) — the first generation
    with adaptive thinking (``thinking: {"type": "adaptive"}``).

    Adaptive thinking is a Claude-exclusive capability; no other model
    family supports it. Provider-prefixed variants (aws-claude-sonnet-4-6,
    anthropic/claude-opus-4.6, bedrock/claude-..., us.anthropic.claude-...)
    are handled by the search-based version pattern.
    """
    if not model_name:
        return False
    match = _CLAUDE_MAJOR_MINOR_VERSION_PATTERN.search(model_name.lower())
    if match:
        major = int(match.group(1) or match.group(3))
        minor = int(match.group(2) or match.group(4))
        return (major, minor) >= (4, 6)
    # Integer-major-only names (claude-sonnet-5, claude-5-sonnet): 5+ is
    # newer than 4.6 anyway.
    return is_claude_5_or_newer(model_name)


# Matches the major version in Kimi model names like "kimi-k3", "kimi-k2.6".
# It is matched with re.search (not anchored), so provider-qualified names
# like "moonshotai/kimi-k3" or "kimi-k2.6" all match as well.
_KIMI_MAJOR_VERSION_PATTERN = re.compile(
    r"kimi-k(\d+)", re.IGNORECASE
)


def is_kimi_k3_or_newer(model_name: str) -> bool:
    """Whether the model is a K3-generation or newer Kimi model
    (e.g. kimi-k3).

    The K3+ generation is what the effort handling keys off: it drives the
    low/high/max reasoning_effort ladder in get_valid_reasoning_efforts()
    (there is no "medium" level for this family).
    """
    if not model_name:
        return False
    match = _KIMI_MAJOR_VERSION_PATTERN.search(model_name.lower())
    if not match:
        return False
    return int(match.group(1)) >= 3


# Matches the numbered GPT generation in names like "gpt-5.6-luna" or
# "gpt-6-astra". It is matched with re.search (not anchored), so
# provider-qualified names ("openai/gpt-5.6-luna", "azure/gpt-5.6-terra")
# match as well. A bare "astra" alias carries no number and is handled
# separately by _is_astra_alias().
_GPT_MAJOR_VERSION_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])gpt[-_]?(\d+)(?:[^0-9]|$)", re.IGNORECASE
)


def _gpt_major_version(model_name: str) -> Optional[int]:
    """Extract the numbered GPT generation from a provider-qualified name."""
    match = _GPT_MAJOR_VERSION_PATTERN.search(model_name.lower())
    return int(match.group(1)) if match else None


def _is_astra_alias(model_name: str) -> bool:
    """Whether the name is Astra's unnumbered short alias (bare "astra").

    Astra is registered as ``gpt-6-astra`` in MODEL_SETTING, but user-defined
    configs may carry the bare short name; token-based matching
    keeps unrelated names (e.g. "astral-projection") out.
    """
    return "astra" in re.split(r"[-_.\s/]+", model_name.lower())


def is_gpt_5_or_newer(model_name: str) -> bool:
    """Whether the model is GPT-5 or a later numbered GPT generation
    (gpt-5.6-luna, gpt-6-astra, ...), including Astra's unnumbered alias.

    These models share one reasoning_effort ladder (low/medium/high/max),
    so they are resolved together instead of depending on the default each
    MODEL_SETTING entry happens to declare.
    """
    if not model_name:
        return False
    version = _gpt_major_version(model_name)
    if version is not None:
        return version >= 5
    return _is_astra_alias(model_name)


def get_valid_reasoning_efforts(
    model_name: str, model_default: Optional[str] = None
) -> List[str]:
    """Valid reasoning effort levels for a model (used by /effort validation).

    Kimi K3+, DeepSeek and GLM-5.3+ support "low"/"high"/"max" (no "medium").
    GLM-5.2 accepts only "high"/"max" ("low" arrives with GLM-5.3). Qwen
    accepts "low"/"medium"/"xhigh" (no "high"). GPT-5-and-newer models
    (gpt-5.x, gpt-6-astra) use the openai-protocol ladder, which keeps
    "medium" and adds "max" beyond "high" — the same set for the whole
    family, independent of the entry's own default. Claude models add
    "xhigh"/"max" to the base low/medium/high. The model's own configured
    default is always a valid choice.
    """
    if is_glm_5_3_or_newer(model_name):
        return ["low", "high", "max"]
    if is_glm_5_2_or_newer(model_name):
        return ["high", "max"]
    if is_kimi_k3_or_newer(model_name) or is_deepseek_model(model_name):
        return ["low", "high", "max"]
    if is_qwen_model(model_name):
        return ["low", "medium", "xhigh"]
    if is_gpt_5_or_newer(model_name):
        return list(GPT_EXTENDED_REASONING_EFFORTS)
    valid = list(VALID_REASONING_EFFORTS)
    if is_claude_model(model_name):
        valid += [e for e in CLAUDE_EXTRA_EFFORTS if e not in valid]
    if model_default and model_default not in valid:
        valid.append(model_default)
    return valid


# Ordinal strength of every known effort level; drives the cross-model
# mapping in coerce_reasoning_effort(). Higher = more thinking.
_EFFORT_STRENGTH = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}


def coerce_reasoning_effort(
    model_name: str, effort: str, model_default: Optional[str] = None
) -> str:
    """Map an effort level onto the levels the target model accepts.

    Used when the user's reasoning-effort intent (set via /effort or
    conf.yaml) must survive a model switch. Same-name levels pass through
    unchanged (low→low, high→high, max→max); levels the target model does
    not accept map to the nearest strength neighbour, ties resolving to the
    STRONGER level:
      * medium→high and xhigh→max on domestic low/high/max models
        (Kimi K3+/DeepSeek/GLM-5.3+) — the default-tier alignment: "medium"
        is the default abroad, "high" is the default at home;
      * low→high on GLM-5.2 (no low before 5.3);
      * high→xhigh and max→xhigh on Qwen (its strong tier is named xhigh);
      * xhigh/max→high on plain low/medium/high models.

    Unknown effort values fall back to the model's default (or "high").
    """
    valid = get_valid_reasoning_efforts(model_name, model_default)
    if effort in valid:
        return effort

    strength = _EFFORT_STRENGTH.get(effort)
    if strength is None:
        return model_default or "high"

    best: Optional[str] = None
    best_dist: Optional[int] = None
    for candidate in valid:
        cand_strength = _EFFORT_STRENGTH.get(candidate)
        if cand_strength is None:
            continue
        dist = abs(cand_strength - strength)
        if (
            best is None
            or dist < best_dist
            or (dist == best_dist and cand_strength > _EFFORT_STRENGTH[best])
        ):
            best, best_dist = candidate, dist
    return best or model_default or "high"


def is_gemini_model(model_name: str) -> bool:
    return "gemini" in model_name.lower()

def is_glm_model(model_name: str) -> bool:
    return "glm" in model_name.lower()


def is_deepseek_model(model_name: str) -> bool:
    return "deepseek" in model_name.lower()


def is_qwen_model(model_name: str) -> bool:
    return "qwen" in model_name.lower()


# Matches major.minor in GLM model names like "glm-5.2"; re.search-based, so
# provider-qualified names like "zhipuai/glm-5.2" match too.
_GLM_VERSION_PATTERN = re.compile(r"glm-(\d+)\.(\d+)", re.IGNORECASE)


def _glm_version_at_least(model_name: str, major: int, minor: int) -> bool:
    if not model_name:
        return False
    match = _GLM_VERSION_PATTERN.search(model_name.lower())
    if not match:
        return False
    return (int(match.group(1)), int(match.group(2))) >= (major, minor)


def is_glm_5_2_or_newer(model_name: str) -> bool:
    """Whether the model is GLM-5.2+ — the first generation supporting the
    reasoning_effort request field."""
    return _glm_version_at_least(model_name, 5, 2)


def is_glm_5_3_or_newer(model_name: str) -> bool:
    """Whether the model is GLM-5.3+ (incl. GLM-5.3-FLASH) — the first
    generation accepting "low" as a reasoning_effort value."""
    return _glm_version_at_least(model_name, 5, 3)


def set_user_model_settings(user_models: List[ModelBaseConfig]) -> None:
    """
    Set user-defined model settings. This will be used when provider is 'default'.
    
    Args:
        user_models: List of user-defined model configurations
    """
    global _user_model_settings
    _user_model_settings = user_models


def get_model_settings() -> List[ModelBaseConfig]:
    """
    Get the current model settings list, by priority:

    1. User-defined settings (models.json / API-key provider models, set via
       set_user_model_settings) — users who bring their own key or model list
       keep full control.
    2. Built-in MODEL_SETTING defaults.

    Returns:
        List of ModelBaseConfig
    """
    if _user_model_settings is not None:
        return _user_model_settings
    return MODEL_SETTING


def get_model_config(model_name: str) -> Optional[ModelBaseConfig]:
    """
    Retrieves the configuration for a given model name.

    The lookup runs against get_model_settings(): user-defined settings
    (models.json / own key) take priority; otherwise the built-in
    MODEL_SETTING list applies.

    Args:
        model_name: The name of the model to retrieve.

    Returns:
        A ModelSettings instance if the model is found, otherwise None.
    """
    # Check if model_name is None or empty
    if not model_name:
        raise ValueError("Model name cannot be None or empty")

    # Get the model settings list (user-defined settings or the built-in defaults)
    model_settings = get_model_settings()

    # Only exact match
    for model_config in model_settings:
        if model_config.model_name == model_name:
            return model_config

    return None
