import logging
import re
from dataclasses import dataclass
from typing import Optional, List


logger = logging.getLogger(__name__)
_user_model_settings: Optional[List['ModelBaseConfig']] = None
VALID_REASONING_EFFORTS = ("low", "medium", "high")
CLAUDE_EXTRA_EFFORTS = ("xhigh", "max")
GPT_EXTENDED_REASONING_EFFORTS = ("low", "medium", "high", "max")


@dataclass
class ModelBaseConfig:
    """Configuration for a language model, including user-supplied metadata."""

    model_name: str
    context_window: int
    max_tokens: Optional[int] = None
    # None means undeclared capabilities; only False explicitly rejects images.
    supports_images: Optional[bool] = False
    supports_vision_bridge: bool = False
    supports_prompt_cache: bool = False
    parallel_tool_calls: Optional[bool] = None
    supports_extra_params: Optional[List[str]] = None
    default_thinking_tokens: Optional[int] = None
    default_reasoning_effort: Optional[str] = None
    effort_choices: Optional[List[str]] = None
    # User prices override the built-in estimates (CNY per million tokens).
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_write_price: Optional[float] = None
    cache_read_price: Optional[float] = None
    note: Optional[str] = None
    # The first image-capable flagged model supplies the vision bridge engine.
    is_vision_engine_model: bool = False

    def __post_init__(self) -> None:
        if self.effort_choices is not None:
            known = {"low", "medium", "high", "xhigh", "max"}
            if (
                not isinstance(self.effort_choices, list)
                or not self.effort_choices
                or any(not isinstance(e, str) or e not in known for e in self.effort_choices)
            ):
                raise ValueError("effort_choices must be a non-empty list of known effort levels")
            self.effort_choices = list(dict.fromkeys(self.effort_choices))


DEFAULT_MODEL_NAME = "claude-sonnet-5"

# Public model IDs and conservative client defaults. User metadata from
# models.json or the selected API provider takes precedence over this catalog.
MODEL_SETTING: List[ModelBaseConfig] = [
    ModelBaseConfig(
        model_name="claude-opus-5-5",
        max_tokens=65536,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4-6",
        max_tokens=32768,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_thinking_tokens=-1,
        default_reasoning_effort="high",
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-5",
        max_tokens=81920,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_thinking_tokens=-1,
        default_reasoning_effort="high",
    ),
    ModelBaseConfig(
        model_name="deepseek-v4-pro",
        max_tokens=384_000,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="high",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="deepseek-v4-pro-0813",
        max_tokens=384_000,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
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
        model_name="gemini-4-argon",
        max_tokens=32768,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="medium",
    ),
    ModelBaseConfig(
        model_name="gpt-6.1-sol",
        max_tokens=65536,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="glm-5.2",
        max_tokens=65536,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="glm-5.3",
        max_tokens=65536,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="glm-5.3-flash",
        max_tokens=65536,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="gpt-6-astra",
        max_tokens=65536,
        context_window=1_050_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="gpt-6-luna",
        max_tokens=65536,
        context_window=1_050_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="gpt-6-sol",
        max_tokens=65536,
        context_window=1_050_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="kimi-k3",
        context_window=1_048_576,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="max",
    ),
    ModelBaseConfig(
        model_name="qwen3.7-max",
        max_tokens=32768,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
        supports_vision_bridge=True,
    ),
    ModelBaseConfig(
        model_name="qwen3.7-plus",
        max_tokens=32768,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
    ),
    ModelBaseConfig(
        model_name="qwen3.8-flash",
        max_tokens=32768,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
    ),
    ModelBaseConfig(
        model_name="qwen3.8-max",
        max_tokens=32768,
        context_window=1_000_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens", "reasoning_effort"],
        default_reasoning_effort="xhigh",
    ),
]


def is_claude_model(model_name: str) -> bool:
    return "claude" in model_name.lower()


_CLAUDE_MAJOR_VERSION_PATTERN = re.compile(
    r"claude-(?:[a-z]+-(\d+)|(\d+)-[a-z]+)", re.IGNORECASE
)
_CLAUDE_MAJOR_MINOR_VERSION_PATTERN = re.compile(
    r"claude-(?:[a-z]+-(\d+)[.-](\d)|(\d+)[.-](\d)-[a-z]+)", re.IGNORECASE
)


def is_claude_5_or_newer(model_name: str) -> bool:
    """Recognize numbered Claude generations, including provider-qualified IDs."""
    if not model_name:
        return False
    match = _CLAUDE_MAJOR_VERSION_PATTERN.search(model_name.lower())
    if not match:
        return False
    return int(match.group(1) or match.group(2)) >= 5


def is_claude_4_6_or_newer(model_name: str) -> bool:
    """Recognize models supporting Claude adaptive thinking."""
    if not model_name:
        return False
    match = _CLAUDE_MAJOR_MINOR_VERSION_PATTERN.search(model_name.lower())
    if match:
        major = int(match.group(1) or match.group(3))
        minor = int(match.group(2) or match.group(4))
        return (major, minor) >= (4, 6)
    return is_claude_5_or_newer(model_name)


_KIMI_MAJOR_VERSION_PATTERN = re.compile(r"kimi-k(\d+)", re.IGNORECASE)


def is_kimi_k3_or_newer(model_name: str) -> bool:
    """Recognize the Kimi generation with the low/high/max effort ladder."""
    if not model_name:
        return False
    match = _KIMI_MAJOR_VERSION_PATTERN.search(model_name.lower())
    return bool(match and int(match.group(1)) >= 3)


_GPT_MAJOR_VERSION_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])gpt[-_]?(\d+)(?:[^0-9]|$)", re.IGNORECASE
)


def _gpt_major_version(model_name: str) -> Optional[int]:
    match = _GPT_MAJOR_VERSION_PATTERN.search(model_name.lower())
    return int(match.group(1)) if match else None


def _is_astra_alias(model_name: str) -> bool:
    return "astra" in re.split(r"[-_.\s/]+", model_name.lower())


def is_gpt_5_or_newer(model_name: str) -> bool:
    """Recognize GPT-5+ and Astra's unnumbered alias."""
    if not model_name:
        return False
    version = _gpt_major_version(model_name)
    return version >= 5 if version is not None else _is_astra_alias(model_name)


def get_valid_reasoning_efforts(
    model_name: str, model_default: Optional[str] = None,
    effort_choices: Optional[List[str]] = None,
) -> List[str]:
    """Return the explicit allowlist, or infer the model family's effort ladder."""
    if effort_choices is None:
        config = get_model_config(model_name)
        effort_choices = config.effort_choices if config else None
    if effort_choices is not None:
        return list(effort_choices)
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


def supports_extra_param(
    supports: Optional[List[str]], param: str,
) -> Optional[bool]:
    """Return None for undeclared capabilities, rather than an explicit denial."""
    return None if supports is None else param in supports


def supports_image_input(supports: Optional[bool]) -> Optional[bool]:
    """Return None for undeclared native image capabilities."""
    return None if supports is None else bool(supports)


_EFFORT_STRENGTH = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}


def coerce_reasoning_effort(
    model_name: str, effort: str, model_default: Optional[str] = None,
    effort_choices: Optional[List[str]] = None,
) -> str:
    """Map effort to the nearest supported strength, preferring stronger ties."""
    valid = get_valid_reasoning_efforts(model_name, model_default, effort_choices)
    if effort in valid:
        return effort
    strength = _EFFORT_STRENGTH.get(effort)
    if strength is None:
        if model_default in valid:
            return model_default
        return "high" if "high" in valid else valid[-1]
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
    return best or (model_default if model_default in valid else valid[-1])


def is_gemini_model(model_name: str) -> bool:
    return "gemini" in model_name.lower()


def is_glm_model(model_name: str) -> bool:
    return "glm" in model_name.lower()


def is_deepseek_model(model_name: str) -> bool:
    return "deepseek" in model_name.lower()


def is_qwen_model(model_name: str) -> bool:
    return "qwen" in model_name.lower()


_GLM_VERSION_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])glm[-_]?(\d+)(?:\.(\d+))?(?![0-9])", re.IGNORECASE
)


def get_glm_version(model_name: Optional[str]) -> Optional[tuple[int, int]]:
    """Return the GLM major/minor generation; an omitted minor means zero."""
    if not model_name:
        return None
    match = _GLM_VERSION_PATTERN.search(str(model_name).lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def _glm_version_at_least(model_name: str, major: int, minor: int) -> bool:
    version = get_glm_version(model_name)
    return version is not None and version >= (major, minor)


def is_glm_5_2_or_newer(model_name: str) -> bool:
    return _glm_version_at_least(model_name, 5, 2)


def is_glm_5_3_or_newer(model_name: str) -> bool:
    return _glm_version_at_least(model_name, 5, 3)


def set_user_model_settings(user_models: List[ModelBaseConfig]) -> None:
    """Install the user's authoritative in-memory model catalog."""
    global _user_model_settings
    _user_model_settings = user_models


def get_model_settings() -> List[ModelBaseConfig]:
    """Prefer user models over the built-in public catalog."""
    return _user_model_settings if _user_model_settings is not None else MODEL_SETTING


def get_model_config(model_name: str) -> Optional[ModelBaseConfig]:
    """Find an exact name in the active local catalog."""
    if not model_name:
        raise ValueError("Model name cannot be None or empty")
    for model_config in get_model_settings():
        if model_config.model_name == model_name:
            return model_config
    return None