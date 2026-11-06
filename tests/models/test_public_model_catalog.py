"""Guards on the public built-in model catalog and its price table.

The built-in catalog (``MODEL_SETTING``) and the price table
(``MODEL_PRICING``) ship inside the open-source package, so they are a public
statement about which models exist and roughly what they cost. These tests keep
that statement honest and self-consistent:

* every catalog name is a bare vendor model id -- no provider-qualified
  spellings and no internal-only deployment aliases;
* catalog and price-table entries are unique, and the fallback default model
  exists and is priced;
* user pricing from ``~/.siada-cli/models.json`` always wins over the built-in
  table (the documented lookup contract);
* a model nobody priced has NO price: lookups return ``None`` and the cost
  helpers return 0.0 instead of inventing a number.

Everything here is offline and deterministic -- no vendor call and no network.
"""

from __future__ import annotations

import re
import sys

import pytest

from siada.models import model_pricing as model_pricing_module
from siada.models.model_base_config import (
    DEFAULT_MODEL_NAME,
    MODEL_SETTING,
    ModelBaseConfig,
    set_user_model_settings,
)
from siada.models.model_pricing import (
    MODEL_PRICING,
    USD_TO_CNY,
    calculate_token_cost,
    calculate_token_cost_breakdown,
    get_model_pricing,
)

# A shipped catalog name is a bare vendor model id: lowercase, no path or
# provider qualifier, no version/registry decoration.
_BARE_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Substrings that would only appear in an internal deployment alias or an
# internal module/provider name, never in a vendor's published model id.
_INTERNAL_MARKERS = ("li-", "li_", "internal", "siada", "private", "staging", "canary")

# Price-table keys that were removed because no vendor publishes a model with
# that exact id (they were convenience spellings only). Users who talk to an
# endpoint that accepts them can still price them via models.json.
NON_VENDOR_SPELLINGS = (
    "claude-sonnet-4.6",  # Anthropic ids use dashes: claude-sonnet-4-6
    "qwen-3.8-max",  # Alibaba ids use qwen3.8-max
    "qwen-3.8-flash",
    "qwen-3.7-max",
    "qwen-3.7-plus",
)

UNKNOWN_MODEL = "definitely-not-a-real-model-xyz"


@pytest.fixture
def user_model_settings():
    """Reset the process-wide user model settings around a test.

    ``set_user_model_settings`` mutates module-level state, so every test that
    reads or writes it must start from -- and leave behind -- a clean slate.
    """
    set_user_model_settings(None)
    yield set_user_model_settings
    set_user_model_settings(None)


def _catalog_names() -> list[str]:
    return [config.model_name for config in MODEL_SETTING]


class TestCatalogHygiene:
    def test_catalog_names_are_bare_vendor_ids(self):
        for name in _catalog_names():
            assert "/" not in name, f"{name!r} is provider-qualified"
            assert ":" not in name, f"{name!r} carries an endpoint qualifier"
            assert _BARE_MODEL_ID.match(name), f"{name!r} is not a bare model id"

    def test_catalog_names_carry_no_internal_aliases(self):
        for name in _catalog_names():
            lowered = name.lower()
            for marker in _INTERNAL_MARKERS:
                assert marker not in lowered, f"{name!r} looks internal ({marker})"

    def test_catalog_names_are_unique(self):
        names = _catalog_names()
        assert names, "the built-in catalog must not be empty"
        duplicates = sorted({name for name in names if names.count(name) > 1})
        assert duplicates == []

    def test_catalog_entries_are_usable(self):
        for config in MODEL_SETTING:
            assert config.context_window > 0
            assert config.max_tokens is None or config.max_tokens > 0

    def test_default_model_is_in_the_catalog(self):
        assert DEFAULT_MODEL_NAME in _catalog_names()

    @pytest.mark.parametrize("model_name", ("gpt-6-astra", "gpt-6-luna", "gpt-6-sol"))
    def test_openai_context_window_is_distinct_from_the_pricing_threshold(self, model_name):
        config = next(item for item in MODEL_SETTING if item.model_name == model_name)
        assert config.context_window == 1_050_000
        assert get_model_pricing(model_name).tiers[0].context_window == 272_000

    def test_default_model_is_priced(self):
        assert get_model_pricing(DEFAULT_MODEL_NAME) is not None


class TestPriceTableHygiene:
    def test_pricing_keys_are_bare_vendor_ids_without_internal_aliases(self):
        for key in MODEL_PRICING:
            assert _BARE_MODEL_ID.match(key), f"{key!r} is not a bare model id"
            for marker in _INTERNAL_MARKERS:
                assert marker not in key.lower(), f"{key!r} looks internal ({marker})"

    def test_pricing_entry_name_matches_its_key(self):
        for key, pricing in MODEL_PRICING.items():
            assert pricing.model_name == key

    def test_prices_are_non_negative(self):
        for key, pricing in MODEL_PRICING.items():
            tiers = pricing.tiers or []
            for tier in tiers:
                assert min(
                    tier.input_price,
                    tier.output_price,
                    tier.cache_write_price,
                    tier.cache_read_price,
                ) >= 0, f"{key} has a negative tier price"
            assert min(
                pricing.input_price,
                pricing.output_price,
                pricing.cache_write_price,
                pricing.cache_read_price,
            ) >= 0, f"{key} has a negative price"

    @pytest.mark.parametrize("spelling", NON_VENDOR_SPELLINGS)
    def test_non_vendor_spellings_are_not_priced(self, spelling, user_model_settings):
        assert spelling not in MODEL_PRICING
        assert get_model_pricing(spelling) is None

    def test_usd_prices_are_converted_with_the_fixed_estimate_rate(self):
        assert USD_TO_CNY == 7.0

        # Claude Sonnet 5 is published at $2 in / $10 out per MTok, with a
        # $2.50 5-minute cache write and a $0.20 cache hit.
        sonnet = get_model_pricing("claude-sonnet-5")
        assert sonnet.input_price == pytest.approx(2.0 * USD_TO_CNY)
        assert sonnet.output_price == pytest.approx(10.0 * USD_TO_CNY)
        assert sonnet.cache_write_price == pytest.approx(2.5 * USD_TO_CNY)
        assert sonnet.cache_read_price == pytest.approx(0.20 * USD_TO_CNY)

        # gpt-6-astra is published in two bands: short context (prompts up to
        # 272K input tokens) at $10 in / $1 cached in / $12.50 cache write /
        # $50 out per MTok, and long context above 272K at $20 / $2 / $25 / $75.
        astra = get_model_pricing("gpt-6-astra")
        short, long = astra.tiers
        assert short.input_price == pytest.approx(10.0 * USD_TO_CNY)
        assert short.output_price == pytest.approx(50.0 * USD_TO_CNY)
        assert short.cache_write_price == pytest.approx(12.5 * USD_TO_CNY)
        assert short.cache_read_price == pytest.approx(1.0 * USD_TO_CNY)
        assert long.input_price == pytest.approx(20.0 * USD_TO_CNY)
        assert long.output_price == pytest.approx(75.0 * USD_TO_CNY)
        assert long.cache_write_price == pytest.approx(25.0 * USD_TO_CNY)
        assert long.cache_read_price == pytest.approx(2.0 * USD_TO_CNY)

    def test_cny_published_prices_are_used_as_published(self):
        # Kimi K3 is published in CNY: 20 in / 100 out per MTok, a 20 five
        # minute cache write and a 2 cache hit.
        kimi = get_model_pricing("kimi-k3")
        assert kimi.input_price == pytest.approx(20.0)
        assert kimi.output_price == pytest.approx(100.0)
        assert kimi.cache_write_price == pytest.approx(20.0)
        assert kimi.cache_read_price == pytest.approx(2.0)

    def test_deepseek_flash_official_and_legacy_names_share_the_price(self):
        """The vendor publishes this model as "deepseek-flash"; the legacy
        "deepseek-v4-flash" is still accepted for it and billed at the same
        Flash price, so both lookups must agree."""
        official = get_model_pricing("deepseek-flash")
        legacy = get_model_pricing("deepseek-v4-flash")
        assert official is not None
        assert legacy is not None
        for field in ("input_price", "output_price", "cache_read_price"):
            assert getattr(official, field) == pytest.approx(getattr(legacy, field))

    def test_tiered_model_resolves_by_total_input_tokens(self):
        pricing = get_model_pricing("qwen3.7-plus")
        assert [tier.input_price for tier in pricing.tiers] == [2.0, 6.0]
        assert pricing.select_tier(100_000).input_price == 2.0
        assert pricing.select_tier(300_000).input_price == 6.0

    @pytest.mark.parametrize(
        "model_name, short_band, long_band",
        [
            # Bands are (input, output, cache write, cache read) in CNY per
            # MTok. Short context covers prompts up to and including 272K
            # input tokens; 272_001 crosses into the long-context band.
            ("gpt-6-astra", (70.0, 350.0, 87.5, 7.0), (140.0, 525.0, 175.0, 14.0)),
            ("gpt-6-luna", (0.7, 3.5, 0.875, 0.07), (1.4, 5.25, 1.75, 0.14)),
            ("gpt-6-sol", (14.0, 70.0, 17.5, 1.4), (28.0, 105.0, 35.0, 2.8)),
            ("gpt-5.6-sol", (28.0, 140.0, 35.0, 2.8), (56.0, 210.0, 70.0, 5.6)),
        ],
    )
    def test_openai_context_bands_split_at_272k_input_tokens(
        self, model_name, short_band, long_band
    ):
        pricing = get_model_pricing(model_name)
        assert [tier.context_window for tier in pricing.tiers] == [272_000, sys.maxsize]

        for tokens, expected in ((272_000, short_band), (272_001, long_band)):
            band = pricing.select_tier(tokens)
            assert (
                band.input_price,
                band.output_price,
                band.cache_write_price,
                band.cache_read_price,
            ) == expected, f"{model_name} @ {tokens} input tokens"

    def test_public_pricing_helpers_do_not_reference_internal_providers(self):
        """These docstrings are user-facing; internal names must stay out."""
        documented = "\n".join(
            text or ""
            for text in (
                model_pricing_module.__doc__,
                get_model_pricing.__doc__,
                calculate_token_cost.__doc__,
                calculate_token_cost_breakdown.__doc__,
            )
        ).lower()
        for marker in ("li provider", "li_provider", "siada.internal", "siada_internal"):
            assert marker not in documented


class TestUserPricingOverride:
    def test_user_pricing_wins_over_the_builtin_table(self, user_model_settings):
        user_model_settings([
            ModelBaseConfig(
                model_name="claude-sonnet-5",
                context_window=200_000,
                input_price=1.0,
                output_price=2.0,
                cache_write_price=0.5,
                cache_read_price=0.25,
            )
        ])

        pricing = get_model_pricing("claude-sonnet-5")
        assert pricing is not None
        assert pricing.input_price == 1.0
        assert pricing.output_price == 2.0
        # ... and the cost helpers use the user's numbers, not the built-ins.
        assert calculate_token_cost("claude-sonnet-5", 1_000_000, 1_000_000) == 3.0
        assert calculate_token_cost_breakdown(
            "claude-sonnet-5", 0, 0, cache_read_tokens=1_000_000
        )["cache_read_cost"] == 0.25

    def test_user_pricing_wins_for_the_fallback_name(self, user_model_settings):
        user_model_settings([
            ModelBaseConfig(
                model_name="my-self-hosted-model",
                context_window=32_000,
                input_price=3.0,
                output_price=0.0,
            )
        ])

        assert get_model_pricing("unknown-primary-name") is None
        pricing = get_model_pricing("unknown-primary-name", "my-self-hosted-model")
        assert pricing is not None
        assert pricing.input_price == 3.0

    def test_user_entry_without_a_price_falls_back_to_the_builtin_table(
        self, user_model_settings
    ):
        """Only an explicit user price may shadow the built-in estimate."""
        user_model_settings([
            ModelBaseConfig(model_name="kimi-k3", context_window=1_048_576)
        ])

        pricing = get_model_pricing("kimi-k3")
        assert pricing is not None
        assert pricing.input_price == pytest.approx(20.0)


class TestUnknownModelHasNoPrice:
    def test_pricing_lookup_returns_none(self, user_model_settings):
        assert get_model_pricing(UNKNOWN_MODEL) is None
        assert get_model_pricing(UNKNOWN_MODEL, "another-unknown-model") is None

    def test_retired_gemini_id_is_off_the_catalog_and_unpriced(
        self, user_model_settings
    ):
        """gemini-3.5-flash was removed: the vendor deprecates the ID and no
        published price for it could be confirmed, so the lookup must report
        "unknown" instead of a guessed rate."""
        assert "gemini-3.5-flash" not in _catalog_names()
        assert get_model_pricing("gemini-3.5-flash") is None
        assert calculate_token_cost("gemini-3.5-flash", 1_000_000, 1_000_000) == 0.0

    def test_cost_helpers_report_zero(self, user_model_settings):
        assert calculate_token_cost(UNKNOWN_MODEL, 1_000_000, 1_000_000) == 0.0
        assert calculate_token_cost_breakdown(
            UNKNOWN_MODEL,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_write_tokens=1_000_000,
            cache_read_tokens=1_000_000,
        ) == {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_write_cost": 0.0,
            "cache_read_cost": 0.0,
            "total_cost": 0.0,
        }