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

MODELS_DEV_URL = "https://models.dev/api.json"
_CACHE_MAX_AGE = 86400  # 24 hours

# provider_id (our internal) → (models.dev provider id, base_url, api_key_hint)
_PROVIDER_MAP = [
    ('kimi',    'moonshotai-cn', 'https://api.moonshot.cn/v1',                              'Enter API key like sk-...'),
    ('glm',     'zhipuai',       'https://open.bigmodel.cn/api/paas/v4',                    'Enter API key from zhipuai.cn'),
    ('minimax', 'minimax',       'https://api.minimax.chat/v1',                             'Enter API key from minimax.io'),
    ('openai',  'openai',        'https://api.openai.com/v1',                               'Enter API key like sk-...'),
    ('claude',  'anthropic',     'https://api.anthropic.com',                               'Enter API key like sk-ant-...'),
    ('gemini',  'google',        'https://generativelanguage.googleapis.com/v1beta/openai', 'Enter API key like AIza...'),
]

# Override provider display names (models.dev names differ from our UX labels)
_PROVIDER_DISPLAY_NAMES = {
    'kimi':    'Kimi (Moonshot AI)',
    'glm':     'GLM (ZhipuAI)',
    'minimax': 'MiniMax',
    'openai':  'OpenAI',
    'claude':  'Claude (Anthropic)',
    'gemini':  'Gemini (Google)',
}


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
            if mdata.get('experimental'):
                continue
            ctx = mdata.get('limit', {}).get('context', 128_000) // 1000
            models.append({
                'id': mid,
                'name': mdata.get('name', mid),
                'context': ctx,
                '_date': mdata.get('release_date', '0000-00-00'),
            })
        models.sort(key=lambda m: m['_date'], reverse=True)
        for m in models:
            del m['_date']
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


def get_provider_model_configs(provider_id: str, selected_model: str, base_url: str = '') -> list:
    """Return a ModelBaseConfig list for the given provider from the cache.
    Matches by provider_id first, then by base_url. Falls back to a single-entry
    list using selected_model if no cache data is found."""
    from siada.models.model_base_config import ModelBaseConfig
    providers = get_providers_for_ui()
    matched = None
    for p in providers:
        if p.get('id') == provider_id:
            matched = p
            break
    if not matched and base_url:
        normalized = base_url.rstrip('/')
        for p in providers:
            if p.get('baseUrl', '').rstrip('/') == normalized:
                matched = p
                break
    if matched:
        models = matched.get('models', [])
        if models:
            return [
                ModelBaseConfig(
                    model_name=m['id'],
                    context_window=m.get('context', 128) * 1000,
                    max_tokens=8192,
                    parallel_tool_calls=True,
                )
                for m in models
            ]
    if selected_model:
        return [ModelBaseConfig(
            model_name=selected_model,
            context_window=128_000,
            max_tokens=8192,
            parallel_tool_calls=True,
        )]
    return []
