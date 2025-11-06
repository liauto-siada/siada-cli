from dataclasses import dataclass
from typing import Optional, List

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

    supports_extra_params: Optional[List[str]] = None

# Simple list of all model configurations
MODEL_SETTING: List[ModelBaseConfig] = [
    # ModelBaseConfig(
    #     model_name="o3-pro",
    #     max_tokens=8192,
    #     context_window=200_000,
    #     supports_images=True,
    #     supports_extra_params=["reasoning_effort"],
    # ),
    ModelBaseConfig(
        model_name="claude-opus-4.1",
        max_tokens=8192,
        context_window=200_000,
        supports_extra_params=[],
    ),
    ModelBaseConfig(
        model_name="gpt-5",
        max_tokens=8192,
        context_window=400_000,
        supports_images=True,
        supports_extra_params=["reasoning_effort"],
    ),
    ModelBaseConfig(
        model_name="gpt-5-mini",
        max_tokens=8192,
        context_window=400_000,
        supports_images=True,
        supports_extra_params=["reasoning_effort"],
    ),
    ModelBaseConfig(
        model_name="gpt-4.1",
        max_tokens=8192,
        context_window=1_047_576,
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="claude-opus-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=[],
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=[],
    ),

    ModelBaseConfig(
        model_name="claude-sonnet-4.5",
        max_tokens=8192*4,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=[],
    ),

    ModelBaseConfig(
        model_name="claude-3.7-sonnet",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=[],
    ),
    ModelBaseConfig(
        model_name="gemini-2.5-pro",
        max_tokens=8192,
        context_window=1_048_576,
        supports_extra_params=["thinking_tokens"],
    ),
    ModelBaseConfig(
        model_name="deepseek-v3-0324",
        max_tokens=8192,
        context_window=128_000,
    ),
    ModelBaseConfig(
        model_name="deepseek-v3.1",
        max_tokens=8192,
        context_window=163_840,
        supports_extra_params=[],
    ),
    ModelBaseConfig(
        model_name="kimi-k2",
        max_tokens=8192,
        context_window=131_072,
    ),
]

def is_claude_model(model_name: str) -> bool:
    return model_name.startswith("claude")

def is_gemini_model(model_name: str) -> bool:
    return model_name.startswith("gemini-")

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
