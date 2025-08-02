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
    ModelBaseConfig(
        model_name="claude-opus-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=["thinking_tokens"],
    ),
    ModelBaseConfig(
        model_name="claude-sonnet-4",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=["thinking_tokens"],
    ),
    ModelBaseConfig(
        model_name="claude-3.7-sonnet",
        max_tokens=8192,
        context_window=200_000,
        supports_images=True,
        supports_extra_params=["thinking_tokens"],
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
    )
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