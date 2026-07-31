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
    "claude-sonnet-5": ModelPricing(
        model_name="claude-sonnet-5",
        input_price=14.5,
        output_price=72.5,
        cache_write_price=18.1,
        cache_read_price=1.5,
    ),
    "claude-sonnet-4-6": ModelPricing(
        model_name="claude-sonnet-4-6",
        input_price=21.7,
        output_price=108.5,
        cache_write_price=27.1,
        cache_read_price=2.2,
    ),
    "claude-sonnet-4-5": ModelPricing(
        model_name="claude-sonnet-4-5",
        # Base tier (<=200k context). >200k context tier is priced higher
        # (43.4/162.8/54.3/4.3) but tiered pricing isn't modeled here.
        input_price=21.7,
        output_price=108.5,
        cache_write_price=27.1,
        cache_read_price=2.2,
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
    "gpt-5.6-terra": ModelPricing(
        model_name="gpt-5.6-terra",
        input_price=16.4,
        output_price=98.3,
        cache_write_price=20.5,
        cache_read_price=1.6,
    ),
    "gpt-5.6-sol": ModelPricing(
        model_name="gpt-5.6-sol",
        input_price=32.8,
        output_price=196.7,
        cache_write_price=41.0,
        cache_read_price=3.3,
    ),
    "gpt-5.6-luna": ModelPricing(
        model_name="gpt-5.6-luna",
        input_price=6.6,
        output_price=39.3,
        cache_write_price=8.2,
        cache_read_price=0.7,
    ),
    "gpt-5.4": ModelPricing(
        model_name="gpt-5.4",
        input_price=18.1,
        output_price=108.6,
        cache_read_price=1.8,
    ),
    "gemini-3.5-flash": ModelPricing(
        model_name="gemini-3.5-flash",
        input_price=10.9,
        output_price=65.2,
        cache_read_price=1.1,
    ),
    "gemini-3.1-pro-preview": ModelPricing(
        model_name="gemini-3.1-pro-preview",
        input_price=14.9,
        output_price=89.6,
        cache_read_price=1,
    ),
    "kivy-deepseek-v4-pro": ModelPricing(
        model_name="kivy-deepseek-v4-pro",
        input_price=12,
        output_price=24,
        cache_read_price=1.2,
    ),
    "kivy-deepseek-v4-flash": ModelPricing(
        model_name="kivy-deepseek-v4-flash",
        input_price=1.0,
        output_price=2.0,
        cache_read_price=0.1,
    ),
    "kivy-kimi-k2.6": ModelPricing(
        model_name="kivy-kimi-k2.6",
        input_price=7,
        output_price=28,
        cache_read_price=1.4,
    ),
    "bailian-kimi-k3": ModelPricing(
        model_name="bailian-kimi-k3",
        input_price=20,
        output_price=100,
        cache_read_price=2.0,
    ),
    "kivy-glm-5.1": ModelPricing(
        model_name="kivy-glm-5.1",
        input_price=7,
        output_price=28,
        cache_read_price=1.4,
    ),
    "kivy-glm-5.2": ModelPricing(
        model_name="kivy-glm-5.2",
        input_price=8,
        output_price=28,
        cache_read_price=1.6,
    ),
    "kivy-qwen-3.7-max": ModelPricing(
        model_name="kivy-qwen-3.7-max",
        input_price=4.8,
        output_price=19.2,
        cache_read_price=0.7,
    ),
    "baidu-deepseek-v4-pro": ModelPricing(
        model_name="baidu-deepseek-v4-pro",
        input_price=8.8,
        output_price=17.6,
        cache_read_price=0.8,
    ),
}


def _get_user_defined_pricing(model_name: str) -> Optional[ModelPricing]:
    """
    Look up pricing from user-defined model settings (~/.siada-cli/models.json),
    which lets users configure cost for self-hosted / custom models that aren't
    in the built-in MODEL_PRICING table above.

    Only returns a result if the user has explicitly set `input_price` for the
    model; otherwise returns None so callers fall back to the built-in table.
    """
    try:
        from siada.models.model_base_config import get_model_config
        model_config = get_model_config(model_name)
    except Exception:
        return None

    if not model_config or model_config.input_price is None:
        return None

    return ModelPricing(
        model_name=model_name,
        input_price=model_config.input_price or 0.0,
        output_price=model_config.output_price or 0.0,
        cache_write_price=model_config.cache_write_price or 0.0,
        cache_read_price=model_config.cache_read_price or 0.0,
    )


def get_model_pricing(model_name: str, fallback_model_name: Optional[str] = None) -> Optional[ModelPricing]:
    """
    Get pricing configuration for a specific model.

    Lookup order:
    1. User-defined pricing from ~/.siada-cli/models.json (matched against model_name)
    2. Built-in MODEL_PRICING table (matched against model_name)
    3. Same two steps against fallback_model_name (e.g. a provider-converted alias)

    Args:
        model_name: The name of the model
        fallback_model_name: An alternate name to try if model_name has no pricing
            (e.g. the "li provider" converted name)

    Returns:
        ModelPricing if found, None otherwise
    """
    pricing = _get_user_defined_pricing(model_name) or MODEL_PRICING.get(model_name)
    if pricing:
        return pricing

    if fallback_model_name and fallback_model_name != model_name:
        return _get_user_defined_pricing(fallback_model_name) or MODEL_PRICING.get(fallback_model_name)

    return None


def calculate_token_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    fallback_model_name: Optional[str] = None,
) -> float:
    """
    Calculate the total cost for token usage based on model pricing.
    
    Args:
        model_name: The name of the model
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_write_tokens: Number of cache write tokens (default: 0)
        cache_read_tokens: Number of cache read tokens (default: 0)
        fallback_model_name: An alternate name to try if model_name has no pricing
    
    Returns:
        Total cost in CNY, rounded to 4 decimal places. Returns 0.0 if model pricing not configured.
    """
    # Get model pricing
    pricing = get_model_pricing(model_name, fallback_model_name)
    
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


def calculate_token_cost_breakdown(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    fallback_model_name: Optional[str] = None,
) -> dict:
    """
    Calculate detailed cost breakdown for token usage based on model pricing.

    Returns a dict with input_cost, output_cost, cache_write_cost, cache_read_cost,
    and total_cost. All values in CNY, rounded to 4 decimal places.
    Returns all zeros if model pricing not configured.
    """
    pricing = get_model_pricing(model_name, fallback_model_name)

    if not pricing:
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_write_cost": 0.0,
            "cache_read_cost": 0.0,
            "total_cost": 0.0,
        }

    input_cost = round((input_tokens / 1_000_000) * pricing.input_price, 4) if input_tokens > 0 else 0.0
    output_cost = round((output_tokens / 1_000_000) * pricing.output_price, 4) if output_tokens > 0 else 0.0
    cache_write_cost = round((cache_write_tokens / 1_000_000) * pricing.cache_write_price, 4) if cache_write_tokens > 0 else 0.0
    cache_read_cost = round((cache_read_tokens / 1_000_000) * pricing.cache_read_price, 4) if cache_read_tokens > 0 else 0.0
    total_cost = round(input_cost + output_cost + cache_write_cost + cache_read_cost, 4)

    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "cache_write_cost": cache_write_cost,
        "cache_read_cost": cache_read_cost,
        "total_cost": total_cost,
    }
