import logging
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger(__name__)

_user_model_settings: Optional[List['ModelBaseConfig']] = None

@dataclass
class ModelBaseConfig:
    """
    Represents the configuration for a specific language model.
    """
    model_name: str
    context_window: int
    max_tokens: Optional[int] = None
    supports_images: bool = False
    supports_prompt_cache: bool = False

    parallel_tool_calls: Optional[bool] = None

    supports_extra_params: Optional[List[str]] = None

    # Default thinking token budget for models that support thinking.
    # When set, thinking is enabled by default without needing --thinking-tokens flag.
    # Use -1 for adaptive thinking mode (e.g., Claude 4.6+), positive int for budget mode.
    default_thinking_tokens: Optional[int] = None

    # Default reasoning effort level for models that support reasoning_effort.
    # Valid values: "low", "medium", "high". When set, reasoning is enabled by default.
    default_reasoning_effort: Optional[str] = None

    # Optional pricing overrides (CNY per million tokens). Only meaningful for
    # user-defined models (provider == "default"); when set, they take priority
    # over the built-in MODEL_PRICING table in siada.models.model_pricing.
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_write_price: Optional[float] = None
    cache_read_price: Optional[float] = None

# Simple list of all model configurations
MODEL_SETTING: List[ModelBaseConfig] = [
    ModelBaseConfig(
        model_name="claude-sonnet-5",
        max_tokens=8192 * 4,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=-1,  # -1 means adaptive thinking mode
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4.6",
        max_tokens=8192 * 4,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=-1,  # -1 means adaptive thinking mode
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4.5",
        max_tokens=8192 * 4,
        context_window=200_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="gpt-5.6-terra",
        max_tokens=32768 * 2,
        context_window=272_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"]
        # default_reasoning_effort="medium",
    ),
    ModelBaseConfig(
        model_name="gpt-5.6-luna",
        max_tokens=32768 * 2,
        context_window=272_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"]
        # default_reasoning_effort="medium",
    ),
    ModelBaseConfig(
        model_name="gpt-5.4",
        max_tokens=32768 * 2,
        context_window=272_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"]
        # default_reasoning_effort="medium",
    ),
    ModelBaseConfig(
        model_name="gpt-5.2",
        max_tokens=8192,
        context_window=272_000,
        supports_images=True,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
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
        model_name="gemini-3.1-pro-preview",
        max_tokens=8192,
        context_window=200_000,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    ),
    ModelBaseConfig(
        model_name="kivy-deepseek-v4-pro",
        max_tokens=384_000,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="kivy-deepseek-v4-flash",
        max_tokens=384_000,
        context_window=1_000_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="kivy-kimi-k2.6",
        max_tokens=8192,
        context_window=229_376,
        parallel_tool_calls=False,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="bailian-kimi-k3",
        # max_tokens=131_072,
        context_window=348_576,
        parallel_tool_calls=False,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="kivy-glm-5.2",
        max_tokens=8192*8,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="lpai-glm-5.2",
        max_tokens=8192,
        context_window=300_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="kivy-qwen-3.7-max",
        max_tokens=8192,
        context_window=131_072,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    ),
    ModelBaseConfig(
        model_name="baidu-deepseek-v4-pro",
        max_tokens=384_000,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["thinking_tokens"],
        default_thinking_tokens=1024,
    )
    # ModelBaseConfig(
    #     model_name="gpt-5-codex",
    #     max_tokens=32_768,
    #     context_window=200_000,
    #     supports_images=True,
    #     parallel_tool_calls=True,
    # ),
    # ModelBaseConfig(
    #     model_name="gpt-5.1-codex",
    #     max_tokens=32_768,
    #     context_window=200_000,
    #     supports_images=True,
    #     parallel_tool_calls=True,
    # ),
    # ModelBaseConfig(
    #     model_name="gpt-5.2-codex",
    #     max_tokens=32_768,
    #     context_window=200_000,
    #     supports_images=True,
    #     parallel_tool_calls=True,
    # ),
    # ModelBaseConfig(
    #     model_name="gpt-5.3-codex",
    #     max_tokens=32_768,
    #     context_window=400_000,
    #     supports_images=True,
    #     parallel_tool_calls=True,
    # ),
    # ModelBaseConfig(
    #     model_name="codex-mini-latest",
    #     max_tokens=32_768,
    #     context_window=200_000,
    #     parallel_tool_calls=True,
    # ),
]

def is_claude_model(model_name: str) -> bool:
    return "claude" in model_name.lower()

def is_gemini_model(model_name: str) -> bool:
    return "gemini" in model_name.lower()

def is_glm_model(model_name: str) -> bool:
    return "glm" in model_name.lower()

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
    Get the current model settings list.
    Returns user-defined settings if available, otherwise returns default settings.
    
    Returns:
        List of ModelBaseConfig
    """
    if _user_model_settings is not None:
        return _user_model_settings
    return MODEL_SETTING


def get_model_config(model_name: str) -> Optional[ModelBaseConfig]:
    """
    Retrieves the configuration for a given model name.
    
    Args:
        model_name: The name of the model to retrieve.
        
    Returns:
        A ModelSettings instance if the model is found, otherwise None.
    """
    # Check if model_name is None or empty
    if not model_name:
        raise ValueError("Model name cannot be None or empty")

    # Get the appropriate model settings list
    model_settings = get_model_settings()
    
    # Only exact match
    for model_config in model_settings:
        if model_config.model_name == model_name:
            return model_config
            
    return None
