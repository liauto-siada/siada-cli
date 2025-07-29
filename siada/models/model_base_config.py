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

# Simple list of all model configurations
MODEL_SETTING: List[ModelBaseConfig] = [
    ModelBaseConfig(
        model_name="claude-sonnet-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4-thinking",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True
    ),
    ModelBaseConfig(
        model_name="claude-3-7-sonnet",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True
    ),
    ModelBaseConfig(
        model_name="claude-3-5-sonnet-20240620",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="gemini-2.5-pro",
        max_tokens=65535,
        context_window=1_048_576,
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="claude-opus-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
    ),
    ModelBaseConfig(
        model_name="deepseek-r1-0528",
        max_tokens=16_384,
        context_window=128_000,
    ),
    ModelBaseConfig(
        model_name="deepseek-v3-0324",
        max_tokens=12_288,
        context_window=128_000,
    ),
    ModelBaseConfig(
        model_name="o1",
        max_tokens=100_000,
        context_window=200_000,
        supports_images=True,
        supports_prompt_cache=True,
    ),
    ModelBaseConfig(
        model_name="gpt-4.1",
        max_tokens=32_768,
        context_window=1_047_576,
        supports_images=True,
        supports_prompt_cache=True,
    ),
    ModelBaseConfig(
        model_name="o1-mini",
        max_tokens=65_536,
        context_window=128_000,
        supports_prompt_cache=True,
    ),
    ModelBaseConfig(
        model_name="o3-mini",
        max_tokens=100_000,
        context_window=200_000,
        supports_prompt_cache=True,
    ),
    ModelBaseConfig(
        model_name="gpt-4o",
        max_tokens=16_384,
        context_window=128_000,
        supports_images=True,
        supports_prompt_cache=True,
    ),
]

def get_model_config(model_name: str) -> Optional[ModelBaseConfig]:
    """
    Retrieves the configuration for a given model name.
    
    Args:
        model_name: The name of the model to retrieve.
        
    Returns:
        A ModelSettings instance if the model is found, otherwise None.
    """
    # Exact match first
    for model_config in MODEL_SETTING:
        if model_config.model_name == model_name:
            return model_config
    
    # Fallback for partial matches
    for model_config in MODEL_SETTING:
        if model_name in model_config.model_name:
            return model_config
            
    return None 