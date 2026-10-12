"""
Model pricing configuration and cost calculation module.

The table below holds ESTIMATES of each model vendor's published list price,
expressed in CNY (Chinese Yuan) per million tokens. Vendors that publish in USD
are converted with the fixed ``USD_TO_CNY`` rate below, which is a snapshot
estimate and NOT a live exchange rate. Vendors change prices, promotions and
the model IDs they serve without notice, so treat every number here as a rough
estimate for local cost display only -- never as an invoice, a real-time feed or
a guarantee of what a provider will bill.

Models without an entry here (user-defined models, models whose vendor does not
publish a public list price) have NO known price: lookups return ``None`` and
the cost helpers return 0.0 rather than inventing a number.
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
# Keys are the vendors' own model IDs. Every key is an ID that the vendor
# publishes on a public pricing/model page; off-list spellings and third-party aliases
# are deliberately NOT registered here, and a model whose public list price
# could not be confirmed has no entry at all (so get_model_pricing returns None
# instead of guessing). Users can price anything else themselves through
# ~/.siada-cli/models.json.
#
# Prices are estimates in CNY per million tokens: USD-denominated vendors
# (Anthropic, OpenAI, Google) are converted at the fixed USD_TO_CNY below, and
# CNY-denominated vendors (DeepSeek, Zhipu AI, Moonshot AI, Alibaba) are used
# as published, at the peak (non-discounted) rate where the vendor has
# off-peak pricing. Cache write prices are the vendor's 5-minute cache-write
# rate where one is published; where a vendor publishes none, the value stays
# at 0 rather than being guessed.
MODEL_PRICING: Dict[str, ModelPricing] = {
    # --- Anthropic (USD list prices, 5-minute prompt-cache TTL) ---
    # Claude 4.6 and newer bill the full 1M-token context window at standard
    # rates (no long-context surcharge), so these entries are flat.
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
    # Deliberately absent: "claude-sonnet-4.6" (Anthropic model IDs use dashes,
    # e.g. claude-sonnet-4-6) and the pre-4.6 long-context models such as
    # claude-sonnet-4-5, whose above-threshold rates the vendor no longer
    # publishes. Those lookups return None rather than a guessed rate.
    #
    # --- OpenAI (USD list prices). The vendor splits these prices into a
    # "short context" band covering prompts up to 272K input tokens and a
    # higher "long context" band above that. The entries that publish both
    # bands carry two tiers split at 272K (short first); the flat entries keep
    # the single rate on record for that model. ---
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
        tiers=[
            PriceTier(context_window=272_000, input_price=28.0, output_price=140.0,
                      cache_write_price=35.0, cache_read_price=2.8),
            PriceTier(context_window=sys.maxsize, input_price=56.0, output_price=210.0,
                      cache_write_price=70.0, cache_read_price=5.6),
        ],
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
        tiers=[
            PriceTier(context_window=272_000, input_price=70.0, output_price=350.0,
                      cache_write_price=87.5, cache_read_price=7.0),
            PriceTier(context_window=sys.maxsize, input_price=140.0, output_price=525.0,
                      cache_write_price=175.0, cache_read_price=14.0),
        ],
    ),
    # https://developers.openai.com/api/docs/models/gpt-6-sol
    # Above 272K input: 2x input/cache rates and 1.5x output for the full request.
    "gpt-6-sol": ModelPricing(
        model_name="gpt-6-sol",
        tiers=[
            PriceTier(context_window=272_000, input_price=14.0, output_price=70.0,
                      cache_write_price=17.5, cache_read_price=1.4),
            PriceTier(context_window=sys.maxsize, input_price=28.0, output_price=105.0,
                      cache_write_price=35.0, cache_read_price=2.8),
        ],
    ),
    "gpt-6-luna": ModelPricing(
        model_name="gpt-6-luna",
        tiers=[
            PriceTier(context_window=272_000, input_price=0.7, output_price=3.5,
                      cache_write_price=0.875, cache_read_price=0.07),
            PriceTier(context_window=sys.maxsize, input_price=1.4, output_price=5.25,
                      cache_write_price=1.75, cache_read_price=0.14),
        ],
    ),
    # --- Google (USD list prices) ---
    # Google bills context caching as cache storage per token-hour and does not
    # publish a cache-write token rate, so cache_write_price stays 0.
    # Deliberately absent: "gemini-3.5-flash" -- the vendor marks that model ID
    # deprecated and routes it to 3.6, and no published price for it could be
    # confirmed, so the lookup returns None instead of a guessed rate.
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
    # --- DeepSeek (CNY list prices) ---
    # The peak (non-discounted) rate is used here; off-peak rates are half of
    # it. "deepseek-v4-pro" and "deepseek-flash" are DeepSeek's own model IDs
    # (their pinned versions are DeepSeek-V4-Pro-0813 and DeepSeek-V4.1-Flash).
    # "deepseek-v4-flash" is the older name DeepSeek still accepts for Flash
    # requests and bills at the Flash price; "deepseek-v4-pro-0813" and
    # "deepseek-v4.1-flash" are the corresponding Alibaba Model Studio IDs,
    # which Alibaba prices identically for the Beijing region.
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
    "deepseek-v4.1-flash": ModelPricing(
        model_name="deepseek-v4.1-flash",
        input_price=2.0,
        output_price=8.0,
        cache_read_price=0.04,
    ),
    # --- Zhipu AI / GLM (CNY list prices) ---
    # GLM-5.1 is priced by prompt length: the first tier applies up to 32K
    # input tokens, the second to everything above.
    "glm-5.1": ModelPricing(
        model_name="glm-5.1",
        tiers=[
            PriceTier(context_window=32_768, input_price=6.0, output_price=24.0,
                      cache_read_price=1.3),
            PriceTier(context_window=sys.maxsize, input_price=8.0, output_price=28.0,
                      cache_read_price=2.0),
        ],
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
    # --- Moonshot AI / Kimi (CNY list prices) ---
    # Kimi K3 publishes cache-write rates for a 5-minute and a 1-hour TTL; the
    # 5-minute rate is used here (the default TTL). The K2 series publishes no
    # cache-write rate, so it stays 0.
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
    # --- Alibaba Model Studio / DashScope (CNY list prices) ---
    # Alibaba bills explicit cache creation at 125% of the input price and a
    # cache hit at 10% of it, except on qwen3.8-max and qwen3.8-flash, whose
    # cache-hit price the vendor does not publish (console-only). That price is
    # therefore left at 0 instead of being guessed. The dashed spellings
    # ("qwen-3.8-max") are not Alibaba model IDs and are not registered.
    "qwen3.8-max": ModelPricing(
        model_name="qwen3.8-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
    ),
    "qwen3.8-flash": ModelPricing(
        model_name="qwen3.8-flash",
        input_price=0.8,
        output_price=2.7,
        cache_write_price=1.0,
    ),
    "qwen3.7-max": ModelPricing(
        model_name="qwen3.7-max",
        input_price=12.0,
        output_price=36.0,
        cache_write_price=15.0,
        cache_read_price=1.2,
    ),
    # Prompts over 256k input tokens are billed at the higher tier. The quoted
    # input/output prices are the vendor's list prices, not the running
    # promotional discount.
    "qwen3.7-plus": ModelPricing(
        model_name="qwen3.7-plus",
        tiers=[
            PriceTier(context_window=256_000, input_price=2.0, output_price=8.0,
                      cache_write_price=2.5, cache_read_price=0.2),
            PriceTier(context_window=sys.maxsize, input_price=6.0, output_price=24.0,
                      cache_write_price=7.5, cache_read_price=0.6),
        ],
    ),
}

# Fixed estimate of the USD/CNY rate, used only to express the USD list prices
# above in the CNY currency the cost display works in. It is a snapshot, NOT a
# live FX rate: real card/settlement rates, and what a vendor actually invoices,
# will differ.
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

    Lookup order (user configuration always wins):
    1. User-defined pricing from ~/.siada-cli/models.json (matched against
       model_name)
    2. Built-in MODEL_PRICING table (matched against model_name)
    3. The same two steps against fallback_model_name (e.g. a provider-converted
       alias of the same model)

    Args:
        model_name: The name of the model
        fallback_model_name: An alternate name to try if model_name has no pricing
            (e.g. the name a provider converts the model to)

    Returns:
        ModelPricing if found, None otherwise. None means the price is unknown --
        callers must not substitute a guessed price.
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
        Estimated total cost in CNY, rounded to 4 decimal places. Returns 0.0 if
        model pricing is unknown.
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
    and total_cost. All values are estimated CNY, rounded to 4 decimal places.
    Returns all zeros if model pricing is unknown.
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
