from dataclasses import dataclass
from typing import Optional, List

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
        model_name="kimi-k2",
        max_tokens=8192,
        context_window=131_072,
    ),
]

def is_gemini_model(model_name: str) -> bool:
    return model_name.startswith("gemini-")

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
        
    # Only exact match
    for model_config in MODEL_SETTING:
        if model_config.model_name == model_name:
            return model_config
            
    return None
