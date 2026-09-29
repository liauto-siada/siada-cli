"""
Model pricing configuration and cost calculation module.

Prices are the model vendors' published list prices, expressed in CNY
(Chinese Yuan) per million tokens (USD list prices are converted at
``USD_TO_CNY``). The cost display and ``calculate_token_cost`` report CNY.
"""
import sys
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class PriceTier:
    """A single pricing tier for tiered ("wholesale") pricing.

    Tiers of a model are kept ascending by context_window; the first tier
    whose context_window >= the request's total input tokens applies to ALL
    tokens of that request (input, output, cache write/read). This is a
    "total volume determines unit price" model, not progressive pricing.
    """
    context_window: int  # upper bound of total input tokens for this tier; sys.maxsize = unbounded
    input_price: float  # CNY per million input tokens
    output_price: float  # CNY per million output tokens
    cache_write_price: float = 0.0  # CNY per million cache write tokens
    cache_read_price: float = 0.0  # CNY per million cache read tokens


@dataclass
class ModelPricing:
    """Model pricing configuration"""
    model_name: str
    input_price: float = 0.0  # CNY per million input tokens
    output_price: float = 0.0  # CNY per million output tokens
    cache_write_price: float = 0.0  # CNY per million cache write tokens
    cache_read_price: float = 0.0  # CNY per million cache read tokens
    # Optional tiered pricing. When set, the flat prices above are ignored
    # and the effective prices are resolved via select_tier().
    tiers: Optional[List[PriceTier]] = None

    def select_tier(self, total_input_tokens: int) -> "ModelPricing":
        """Resolve the effective flat pricing for the given total input tokens.

        Picks the first tier whose context_window >= total_input_tokens; if
        the usage exceeds every tier, the last (most expensive) tier applies.
        Non-tiered models are returned unchanged.
        """
        if not self.tiers:
            return self
        chosen = self.tiers[-1]
        for tier in self.tiers:
            if tier.context_window >= total_input_tokens:
                chosen = tier
                break
        return ModelPricing(
            model_name=self.model_name,
            input_price=chosen.input_price,
            output_price=chosen.output_price,
            cache_write_price=chosen.cache_write_price,
            cache_read_price=chosen.cache_read_price,
        )


# Model pricing configuration dictionary.
#
# Prices are in CNY per million tokens and come from each model vendor's
# PUBLISHED list price. Vendors that publish in USD (OpenAI, Anthropic,
# Google) are converted at USD_TO_CNY below; vendors that publish in CNY
# (DeepSeek, Zhipu AI, Moonshot AI, Alibaba) are used as published, at the
# peak (non-discounted) rate where the vendor has off-peak pricing.
# Cache write prices are the vendor's 5-minute cache-write rate; vendors that
# do not publish a cache-write price leave it at 0.
MODEL_PRICING: Dict[str, ModelPricing] = {
    "claude-opus-5-5": ModelPricing(
        model_name="claude-opus-5-5",
        input_price=28.0,
        output_price=140.0,
        cache_write_price=35.0,
        cache_read_price=1.4,
    ),
    "claude-opus-5": ModelPricing(
        model_name="claude-opus-5",
        input_price=35.0,
        output_price=175.0,
        cache_write_price=43.75,
        cache_read_price=3.5,
    ),
    "claude-sonnet-5": ModelPricing(
        model_name="claude-sonnet-5",
        input_price=14.0,
        output_price=70.0,
        cache_write_price=17.5,
        cache_read_price=1.4,
    ),
    "claude-sonnet-4-6": ModelPricing(
        model_name="claude-sonnet-4-6",
        input_price=21.0,
        output_price=105.0,
        cache_write_price=26.25,
        cache_read_price=2.1,
    ),
    # Same model under its dotted spelling (used by user-defined models.json).
    "claude-sonnet-4.6": ModelPricing(
        model_name="claude-sonnet-4.6",
        input_price=21.0,
        output_price=105.0,
        cache_write_price=26.25,
        cache_read_price=2.1,
    ),
    # Prompts over 200k input tokens are billed at the higher tier for all
    # tokens of the request.
    "claude-sonnet-4-5": ModelPricing(
        model_name="claude-sonnet-4-5",
        tiers=[
            PriceTier(context_window=200_000, input_price=21.0, output_price=105.0,
                      cache_write_price=26.25, cache_read_price=2.1),
            PriceTier(context_window=sys.maxsize, input_price=42.0, output_price=157.5,
                      cache_write_price=52.5, cache_read_price=4.2),
        ],
    ),
    "gpt-5.1": ModelPricing(
        model_name="gpt-5.1",
        input_price=8.75,
        output_price=70.0,
        cache_read_price=0.875,
    ),
    "gpt-5.2": ModelPricing(
        model_name="gpt-5.2",
        input_price=12.25,
        output_price=98.0,
        cache_read_price=1.225,
    ),
    "gpt-5.4": ModelPricing(
        model_name="gpt-5.4",
        input_price=17.5,
        output_price=105.0,
        cache_read_price=1.75,
    ),
    "gpt-5.6-terra": ModelPricing(
        model_name="gpt-5.6-terra",
        input_price=14.0,
        output_price=84.0,
        cache_write_price=17.5,
        cache_read_price=1.4,
    ),
    "gpt-5.6-sol": ModelPricing(
        model_name="gpt-5.6-sol",
        input_price=28.0,
        output_price=140.0,
        cache_write_price=35.0,
        cache_read_price=2.8,
    ),
    "gpt-5.6-luna": ModelPricing(
        model_name="gpt-5.6-luna",
        input_price=1.4,
        output_price=8.4,
        cache_write_price=1.75,
        cache_read_price=0.14,
    ),
    "gpt-6-astra": ModelPricing(
        model_name="gpt-6-astra",
        input_price=70.0,
        output_price=350.0,
        cache_write_price=87.5,
        cache_read_price=7.0,
    ),
    "gpt-6-sol": ModelPricing(
        model_name="gpt-6-sol",
        input_price=14.0,
        output_price=70.0,
        cache_write_price=17.5,
        cache_read_price=1.4,
    ),
    "gpt-6-luna": ModelPricing(
        model_name="gpt-6-luna",
        input_price=0.7,
        output_price=3.5,
        cache_write_price=0.875,
        cache_read_price=0.07,
    ),
    "gemini-3.5-flash": ModelPricing(
        model_name="gemini-3.5-flash",
        input_price=10.5,
        output_price=63.0,
        cache_read_price=1.05,
    ),
    # Prompts over 200k input tokens are billed at the higher tier.
    "gemini-3.1-pro-preview": ModelPricing(
        model_name="gemini-3.1-pro-preview",
        tiers=[
            PriceTier(context_window=200_000, input_price=14.0, output_price=84.0,
                      cache_read_price=1.4),
            PriceTier(context_window=sys.maxsize, input_price=28.0, output_price=126.0,
                      cache_read_price=2.8),
        ],
    ),
    # DeepSeek prices are published in CNY; the peak (non-discounted) rate is
    # used here (off-peak, 00:30-08:30 Beijing time, is 50% lower).
    "deepseek-v4-pro": ModelPricing(
        model_name="deepseek-v4-pro",
        input_price=9.0,
        output_price=27.0,
        cache_read_price=0.3,
    ),
    "deepseek-v4-pro-0813": ModelPricing(
        model_name="deepseek-v4-pro-0813",
        input_price=9.0,
        output_price=27.0,
        cache_read_price=0.3,
    ),
    # DeepSeek Flash (the V4-Flash / V4.1-Flash line); the vendor serves it
    # under "deepseek-flash" and keeps the dated/older aliases below.
    "deepseek-v4.1-flash": ModelPricing(
        model_name="deepseek-v4.1-flash",
        input_price=2.0,
        output_price=8.0,
        cache_read_price=0.04,
    ),
    "deepseek-flash": ModelPricing(
        model_name="deepseek-flash",
        input_price=2.0,
        output_price=8.0,
        cache_read_price=0.04,
    ),
    "deepseek-v4-flash": ModelPricing(
        model_name="deepseek-v4-flash",
        input_price=2.0,
        output_price=8.0,
        cache_read_price=0.04,
    ),
    # Zhipu AI (GLM) publishes in CNY.
    "glm-5.1": ModelPricing(
        model_name="glm-5.1",
        input_price=8.0,
        output_price=28.0,
        cache_read_price=2.0,
    ),
    "glm-5.2": ModelPricing(
        model_name="glm-5.2",
        input_price=8.0,
        output_price=28.0,
        cache_read_price=2.0,
    ),
    "glm-5.3": ModelPricing(
        model_name="glm-5.3",
        input_price=8.0,
        output_price=28.0,
        cache_read_price=2.0,
    ),
    "glm-5.3-flash": ModelPricing(
        model_name="glm-5.3-flash",
        input_price=0.8,
        output_price=2.8,
        cache_read_price=0.23,
    ),
    # Moonshot AI (Kimi) publishes in CNY; the cache-write price is its
    # 5-minute cache rate.
    "kimi-k3": ModelPricing(
        model_name="kimi-k3",
        input_price=20.0,
        output_price=100.0,
        cache_write_price=20.0,
        cache_read_price=2.0,
    ),
    "kimi-k2.6": ModelPricing(
        model_name="kimi-k2.6",
        input_price=6.5,
        output_price=27.0,
        cache_read_price=1.1,
    ),
    # Alibaba (Qwen) publishes in CNY. DashScope keeps its own spelling
    # ("qwen3.8-max"); the dashed spellings below are lookups only.
    "qwen3.8-max": ModelPricing(
        model_name="qwen3.8-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
        cache_read_price=1.5,
    ),
    "qwen-3.8-max": ModelPricing(
        model_name="qwen-3.8-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
        cache_read_price=1.5,
    ),
    "qwen3.8-flash": ModelPricing(
        model_name="qwen3.8-flash",
        input_price=0.8,
        output_price=2.7,
        cache_write_price=1.25,
        cache_read_price=0.1,
    ),
    "qwen-3.8-flash": ModelPricing(
        model_name="qwen-3.8-flash",
        input_price=0.8,
        output_price=2.7,
        cache_write_price=1.25,
        cache_read_price=0.1,
    ),
    "qwen3.7-max": ModelPricing(
        model_name="qwen3.7-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
        cache_read_price=1.2,
    ),
    "qwen-3.7-max": ModelPricing(
        model_name="qwen-3.7-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
        cache_read_price=1.2,
    ),
    # Prompts over 256k input tokens are billed at the higher tier.
    "qwen3.7-plus": ModelPricing(
        model_name="qwen3.7-plus",
        tiers=[
            PriceTier(context_window=256_000, input_price=2.0, output_price=8.0,
                      cache_write_price=2.5, cache_read_price=0.4),
            PriceTier(context_window=sys.maxsize, input_price=6.0, output_price=24.0,
                      cache_write_price=7.5, cache_read_price=1.2),
        ],
    ),
    "qwen-3.7-plus": ModelPricing(
        model_name="qwen-3.7-plus",
        tiers=[
            PriceTier(context_window=256_000, input_price=2.0, output_price=8.0,
                      cache_write_price=2.5, cache_read_price=0.4),
            PriceTier(context_window=sys.maxsize, input_price=6.0, output_price=24.0,
                      cache_write_price=7.5, cache_read_price=1.2),
        ],
    ),
}

# Vendors that publish their list price in USD are converted with this fixed
# rate, so the table above stays in a single currency (CNY per million tokens,
# matching the cost display).
USD_TO_CNY = 7.0


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

    # Tiered pricing: select the tier by total input tokens (input + cache
    # write), then bill all token kinds at that tier's prices.
    pricing = pricing.select_tier(input_tokens + cache_write_tokens)

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

    # Tiered pricing: select the tier by total input tokens (input + cache
    # write), then bill all token kinds at that tier's prices.
    pricing = pricing.select_tier(input_tokens + cache_write_tokens)

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
