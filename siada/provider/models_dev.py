"""
models.dev data fetch and cache module.

Data source: https://models.dev/api.json
Cache path:  ~/.siada-cli/models-dev-cache.json (TTL: 24 hours)

Flow:
  1. Prefer local cache (< 24h: use directly; > 24h: use stale data and
     trigger a background refresh).
  2. No cache: return empty list and trigger background refresh
     (frontend falls back to its bundled snapshot).
  3. Background refresh result takes effect on the next call.
"""

from typing import List, Optional

MODELS_DEV_URL = "https://models.dev/api.json"
_CACHE_MAX_AGE = 86400  # 24 hours

# provider_id (our internal) → (models.dev provider id, base_url, api_key_hint)
_PROVIDER_MAP = [
    ('kimi',    'moonshotai-cn', 'https://api.moonshot.cn/v1',                              'Enter API key like sk-...'),
    ('deepseek', 'deepseek',     'https://api.deepseek.com/v1',                             'Enter API key from platform.deepseek.com'),
    ('glm',     'zhipuai',       'https://open.bigmodel.cn/api/paas/v4',                    'Enter API key from zhipuai.cn'),
    ('minimax', 'minimax',       'https://api.minimax.chat/v1',                             'Enter API key from minimax.io'),
    ('openai',  'openai',        'https://api.openai.com/v1',                               'Enter API key like sk-...'),
    ('claude',  'anthropic',     'https://api.anthropic.com',                               'Enter API key like sk-ant-...'),
    ('gemini',  'google',        'https://generativelanguage.googleapis.com/v1beta/openai', 'Enter API key like AIza...'),
]

# Override provider display names (models.dev names differ from our UX labels)
_PROVIDER_DISPLAY_NAMES = {
    'kimi':    'Kimi (Moonshot AI)',
    'deepseek': 'DeepSeek',
    'glm':     'GLM (ZhipuAI)',
    'minimax': 'MiniMax',
    'openai':  'OpenAI',
    'claude':  'Claude (Anthropic)',
    'gemini':  'Gemini (Google)',
}

# Keep older caches usable when they have no tool-capable DeepSeek entries.
# Official API names and limits: https://api-docs.deepseek.com/quick_start/pricing
_DEEPSEEK_MODELS_SNAPSHOT = [
    {'id': 'deepseek-flash', 'name': 'DeepSeek Flash', 'context': 1000},
    {'id': 'deepseek-v4-pro', 'name': 'DeepSeek V4 Pro', 'context': 1000},
]


def _get_cache_path():
    from siada.foundation.constants import SIADA_HOME
    return SIADA_HOME / 'models-dev-cache.json'


def _load_cache():
    """Load models.json from cache. Returns raw dict or None."""
    try:
        import json
        import time
        p = _get_cache_path()
        if not p.exists():
            return None
        age = time.time() - p.stat().st_mtime
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        if age > _CACHE_MAX_AGE:
            # Stale but usable — trigger background refresh for next run
            refresh_cache_bg()
        return data
    except Exception:
        return None


def _save_cache(data: dict) -> None:
    try:
        import json
        p = _get_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def _fetch() -> dict | None:
    """Fetch models.dev/api.json with a short timeout."""
    try:
        import json
        import urllib.request
        req = urllib.request.Request(
            MODELS_DEV_URL,
            headers={'User-Agent': 'siada-cli/1.6.0'},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            # Sanity check: must be a dict with known provider keys
            if not isinstance(data, dict) or 'anthropic' not in data:
                return None
            return data
    except Exception:
        return None


def _image_capability(mdata: dict) -> Optional[bool]:
    """models.dev's declaration of image input support for one model entry.

    models.dev lists the accepted input kinds under ``modalities.input`` and
    also carries an ``attachment`` boolean; ``modalities`` is preferred
    because ``attachment`` also covers non-image files. Returns ``None`` when
    the entry declares neither, so "unknown" stays UNDECLARED instead of
    becoming an explicit denial.
    """
    modalities = (mdata.get('modalities') or {}).get('input')
    if isinstance(modalities, list):
        return 'image' in modalities
    attachment = mdata.get('attachment')
    if isinstance(attachment, bool):
        return attachment
    return None


def _curate(raw: dict) -> list:
    """Extract and curate provider/model data from raw models.dev JSON."""
    result = []
    for our_id, dev_id, base_url, hint in _PROVIDER_MAP:
        pdata = raw.get(dev_id, {})
        models_raw = pdata.get('models', {})
        models = []
        for mid, mdata in models_raw.items():
            if not mdata.get('tool_call'):
                continue
            if mdata.get('status') == 'deprecated':
                continue
            # models.dev's `experimental` is NOT a boolean flag: for the newest
            # models it is an object describing feature modes / per-mode pricing
            # (e.g. {"modes": {"fast": ..., "pro": ..., "ultrafast": ...}}). A
            # non-empty dict is truthy, so a plain truthiness check dropped every
            # released model that carried one (gpt-6.1-sol, gpt-6-sol, gpt-6-luna,
            # gpt-6-astra and all gpt-5.x). Only an explicit boolean True means
            # "experimental".
            if mdata.get('experimental') is True:
                continue
            ctx = mdata.get('limit', {}).get('context', 128_000) // 1000
            models.append({
                'id': mid,
                'name': mdata.get('name', mid),
                'context': ctx,
                # True/False when models.dev declares it, None when undeclared.
                # Carried through so _build() can keep the tri-state instead
                # of turning "unknown" into an explicit image denial.
                'image': _image_capability(mdata),
                '_date': mdata.get('release_date', '0000-00-00'),
            })
        models.sort(key=lambda m: m['_date'], reverse=True)
        for m in models:
            del m['_date']
        if our_id == 'deepseek' and not models:
            models = [dict(model) for model in _DEEPSEEK_MODELS_SNAPSHOT]
        result.append({
            'id': our_id,
            'name': _PROVIDER_DISPLAY_NAMES.get(our_id, pdata.get('name', our_id)),
            'baseUrl': base_url,
            'apiKeyHint': hint,
            'models': models[:8],
        })
    # Always include custom provider at the end
    result.append({
        'id': 'custom',
        'name': 'Custom Provider',
        'baseUrl': '',
        'apiKeyHint': 'your API key',
        'models': [],
    })
    return result


def refresh_cache_bg() -> None:
    """Refresh the models.dev cache in background (non-blocking)."""
    import threading
    def _worker():
        try:
            data = _fetch()
            if data:
                _save_cache(data)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


def get_providers_for_ui() -> list:
    """
    Return curated provider/model list for the login UI.
    Uses local cache when available; otherwise returns empty list (frontend
    falls back to its own bundled snapshot) and triggers a background refresh.
    """
    data = _load_cache()
    if data:
        return _curate(data)
    # No cache — refresh in background, frontend will use its snapshot this time
    refresh_cache_bg()
    return []


# Vendor prefixes the internal gateway puts in front of the catalogue name,
# e.g. the gateway model id "azure-gpt-6_1-sol" is models.dev's "gpt-6.1-sol"
# served by the azure provider. Only applied after the exact name misses, so
# a name that is itself a catalogue entry is never rewritten.
_GATEWAY_NAME_PREFIXES = (
    'azure-', 'openai-', 'kivy-', 'lpai-',
    'baidu-', 'bailian-', 'moonshot-', 'zhipu-', 'zai-',
)


def _catalogue_name_candidates(model_name: str) -> List[str]:
    """Best-effort catalogue lookups for a gateway model id.

    Gateway ids and catalogue names differ in two ways: the internal gateway
    prefixes the vendor onto the catalogue name ("azure-gpt-6_1-sol" vs
    "gpt-6.1-sol"), and it writes ``_`` where the catalogue uses ``.``
    ("gpt-6_1-sol" vs "gpt-6.1-sol").

    Only that single transformation is attempted, and only after the exact
    name misses, so a name that is itself a catalogue entry is never
    rewritten. A "vendor/name" spelling is deliberately left alone: it is a
    different namespace (a user-defined id), never a catalogue name — the
    contract asserted by tests/models/test_glm_capability_defaults.py.
    """
    candidates: List[str] = []

    def _add(value: str) -> None:
        value = value.strip()
        if not value:
            return
        for variant in (value, value.replace('_', '.')):
            if variant not in candidates:
                candidates.append(variant)

    model_name = str(model_name or '').strip()
    _add(model_name)

    lowered = model_name.lower()
    prefix = next((p for p in _GATEWAY_NAME_PREFIXES if lowered.startswith(p)), None)
    if prefix is not None:
        _add(model_name[len(prefix):])
    return candidates


def _find_builtin_model(model_name: str, builtin_by_name: dict):
    """Built-in ``MODEL_SETTING`` entry for a model, tolerating gateway ids.

    An exact name wins; otherwise the gateway-style variants are tried (see
    :func:`_catalogue_name_candidates`), so an id such as
    ``azure-gpt-6_1-sol`` still inherits the capabilities declared for
    ``gpt-6.1-sol`` instead of being treated as an unknown text-only model.
    Returns ``None`` when no catalogue name resolves.
    """
    for candidate in _catalogue_name_candidates(model_name):
        builtin = builtin_by_name.get(candidate)
        if builtin is not None:
            return builtin
    return None


def get_provider_model_configs(provider_id: str, selected_model: str, base_url: str = '') -> list:
    """Return a ModelBaseConfig list for the given provider from the cache.
    Matches by provider_id first, then by base_url. Falls back to a single-entry
    list using selected_model if no cache data is found."""
    from siada.models.model_base_config import MODEL_SETTING, ModelBaseConfig
    from siada.provider.free_trial import FREE_TRIAL_PROVIDER_ID, FREE_TRIAL_MODELS

    if provider_id == FREE_TRIAL_PROVIDER_ID:
        # Use a conservative local admission budget until gateway limits are
        # verified; the UI does not advertise these as upstream context limits.
        return [
            ModelBaseConfig(model_name=model, context_window=32_000, max_tokens=8192)
            for model, _ in FREE_TRIAL_MODELS
        ]
    builtin_by_name = {m.model_name: m for m in MODEL_SETTING}

    def _build(
        model_name: str,
        context_window: int,
        max_tokens: int,
        image: Optional[bool] = None,
    ) -> ModelBaseConfig:
        # Capability fields (supports_extra_params, default_reasoning_effort,
        # thinking, images, etc.) are not present in the models.dev cache, so
        # inherit them from the built-in MODEL_SETTING when the model is known.
        # The lookup tolerates gateway-style ids (see _find_builtin_model).
        # Unknown names get None = capabilities UNDECLARED (not "unsupported"):
        # the gateway determines reasoning behavior unless the user configures
        # it explicitly, and callers must not treat None as a denial (see
        # model_base_config.supports_extra_param / supports_image_input).
        builtin = _find_builtin_model(model_name, builtin_by_name)
        return ModelBaseConfig(
            model_name=model_name,
            context_window=context_window,
            max_tokens=max_tokens,
            parallel_tool_calls=True,
            supports_images=(
                builtin.supports_images if builtin is not None else image
            ),
            supports_vision_bridge=builtin.supports_vision_bridge if builtin else False,
            supports_prompt_cache=builtin.supports_prompt_cache if builtin else False,
            supports_extra_params=builtin.supports_extra_params if builtin else None,
            default_thinking_tokens=builtin.default_thinking_tokens if builtin else None,
            default_reasoning_effort=builtin.default_reasoning_effort if builtin else None,
        )

    providers = [] if provider_id == "custom" else get_providers_for_ui()
    matched = None
    for p in providers:
        if p.get('id') == provider_id:
            matched = p
            break
    if provider_id != "custom" and not matched and base_url:
        normalized = base_url.rstrip('/')
        for p in providers:
            if p.get('baseUrl', '').rstrip('/') == normalized:
                matched = p
                break
    if provider_id != "custom" and not matched and (
        provider_id == 'deepseek'
        or base_url.rstrip('/') == 'https://api.deepseek.com/v1'
    ):
        matched = next(p for p in _curate({}) if p['id'] == 'deepseek')
    if matched:
        models = matched.get('models', [])
        if models:
            return [
                _build(m['id'], m.get('context', 128) * 1000, 8192, m.get('image'))
                for m in models
            ]
    if selected_model:
        # No provider catalogue entry: the id may still be a known gateway
        # model with a vendor prefix (e.g. "azure-gpt-6_1-sol" for
        # "gpt-6.1-sol"), which _find_builtin_model resolves. Image support
        # stays tri-state: None = undeclared for ids nothing can resolve.
        return [_build(selected_model, 128_000, 8192)]
    return []
