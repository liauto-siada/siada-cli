"""
Model pricing configuration and cost calculation module.
All pricing is in CNY (Chinese Yuan) per million tokens.
"""
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class ModelPricing:
    """Model pricing configuration"""
    model_name: str
    input_price: float = 0.0  # CNY per million input tokens
    output_price: float = 0.0  # CNY per million output tokens
    cache_write_price: float = 0.0  # CNY per million cache write tokens
    cache_read_price: float = 0.0  # CNY per million cache read tokens


# Model pricing configuration dictionary
# Prices are in CNY per million tokens
MODEL_PRICING: Dict[str, ModelPricing] = {
    "claude-sonnet-4-6": ModelPricing(
        model_name="claude-sonnet-4-6",
        input_price=22.7,
        output_price=113.4,
        cache_write_price=28.4,
        cache_read_price=2.3,
    ),
    "claude-sonnet-4-5": ModelPricing(
        model_name="claude-sonnet-4-5",
        input_price=21.4,
        output_price=107.1,
        cache_write_price=26.8,
        cache_read_price=2.1,
    ),
    "gpt-5.2": ModelPricing(
        model_name="gpt-5.2",
        input_price=12.3,
        output_price=98.8,
        cache_read_price=1.2,
    ),
    "gpt-5.1": ModelPricing(
        model_name="gpt-5.1",
        input_price=8.9,
        output_price=71.1,
        cache_read_price=0.9,
    ),
    "gpt-5.4": ModelPricing(
        model_name="gpt-5.4",
        input_price=18.1,
        output_price=108.6,
        cache_read_price=1.8,
    ),
    "gemini-3.1-pro-preview": ModelPricing(
        model_name="gemini-3.1-pro-preview",
        input_price=14.9,
        output_price=89.6,
        cache_read_price=1,
    ),
    "deepseek-v3.2": ModelPricing(
        model_name="deepseek-v3.2",
        input_price=2,
        output_price=3,
    ),
    "minimax-m2.5": ModelPricing(
        model_name="minimax-m2.5",
        input_price=2.2,
        output_price=8.8,
        cache_read_price=0.2,
    ),
    "kimi-k2.5": ModelPricing(
        model_name="kimi-k2.5",
        input_price=4.8,
        output_price=19.2,
    ),
    "glm-5": ModelPricing(
        model_name="glm-5",
        input_price=7,
        output_price=28,
        cache_read_price=1.4,
    ),
}


def get_model_pricing(model_name: str) -> Optional[ModelPricing]:
    """
    Get pricing configuration for a specific model.
    
    Args:
        model_name: The name of the model
    
    Returns:
        ModelPricing if found, None otherwise
    """
    return MODEL_PRICING.get(model_name)


def calculate_token_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0
) -> float:
    """
    Calculate the total cost for token usage based on model pricing.
    
    Args:
        model_name: The name of the model
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_write_tokens: Number of cache write tokens (default: 0)
        cache_read_tokens: Number of cache read tokens (default: 0)
    
    Returns:
        Total cost in CNY, rounded to 4 decimal places. Returns 0.0 if model pricing not configured.
    """
    # Get model pricing
    pricing = get_model_pricing(model_name)
    
    # If pricing not found, return 0.0
    if not pricing:
        return 0.0
    
    total_cost = 0.0
    
    # Calculate input tokens cost
    if input_tokens > 0:
        total_cost += (input_tokens / 1_000_000) * pricing.input_price
    
    # Calculate output tokens cost
    if output_tokens > 0:
        total_cost += (output_tokens / 1_000_000) * pricing.output_price
    
    # Calculate cache write tokens cost
    if cache_write_tokens > 0:
        total_cost += (cache_write_tokens / 1_000_000) * pricing.cache_write_price
    
    # Calculate cache read tokens cost
    if cache_read_tokens > 0:
        total_cost += (cache_read_tokens / 1_000_000) * pricing.cache_read_price
    
    # Round to 4 decimal places
    return round(total_cost, 4)
