"""Curated anonymous Kilo Gateway models for the free trial."""

FREE_TRIAL_PROVIDER_ID = "kilo-free"
FREE_TRIAL_BASE_URL = "https://api.kilo.ai/api/gateway"
FREE_TRIAL_MODELS = (
    ("poolside/laguna-s-2.1:free", "Poolside Laguna S 2.1"),
    ("cohere/north-mini-code:free", "Cohere North Mini Code"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super 120B"),
    ("poolside/laguna-xs-2.1:free", "Poolside Laguna XS 2.1"),
    ("nvidia/nemotron-3-ultra-550b-a55b:free", "Nemotron 3 Ultra 550B"),
    ("nvidia/nemotron-3.5-super-vl:free", "Nemotron 3.5 Super VL"),
    ("nvidia/nemotron-3.5-lightning:free", "Nemotron 3.5 Lightning"),
    ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "Nemotron 3 Nano Omni"),
    ("minimax/minimax-m3.1-flash:free", "MiniMax M3.1 Flash"),
    ("xingchen-agi/xing4.0-29b-a4b:free", "Xing 4.0"),
    ("dots-studio/dots-3-note-preview:free", "Dots 3 Note Preview"),
    ("liquid/lfm-2.5-2.6b:free", "Liquid LFM 2.5 2.6B"),
)
FREE_TRIAL_MODEL_IDS = frozenset(model for model, _ in FREE_TRIAL_MODELS)


def is_free_trial_endpoint(base_url: str | None) -> bool:
    """Allow anonymous access only to the exact curated HTTPS endpoint."""
    return bool(base_url and base_url.rstrip("/") == FREE_TRIAL_BASE_URL)


def get_free_trial_models_for_ui() -> list[dict]:
    """Return display metadata without claiming unverified context limits."""
    return [{"id": model, "name": name, "context": 0} for model, name in FREE_TRIAL_MODELS]