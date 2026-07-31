"""
Web tools package - stub that re-exports from internal.

This module delegates to siada.internal.tools.web for backward compatibility.
The actual implementations live in siada/internal/tools/web/ (not open-sourced).
"""

from typing import List, Optional

try:
    from siada.internal.tools.web import get_web_tools, web_search, web_fetch
except ImportError:
    web_search = None

    try:
        from siada.tools.web.web_fetch import web_fetch
    except ImportError:
        web_fetch = None

    def get_web_tools() -> List:
        tools = []
        if web_fetch is not None:
            tools.append(web_fetch)
        return tools

__all__ = [
    'web_fetch',
    'web_search',
    'get_web_tools',
    'resolve_web_tools_enabled',
    'resolve_provider_from_context',
]


def resolve_provider_from_context(context) -> Optional[str]:
    """Resolve the effective provider name from an agent context.

    Prefers ``context.provider`` — the resolved provider written per-run by
    ``SiadaRunner._build_run_config``. This reflects model-based routing
    and legacy-key normalization, and is the authoritative value used for the
    actual LLM call.

    Falls back to resolving from the session's ``llm_config``
    (``model_run_config``) when the per-run provider isn't set yet (e.g. before
    the first run), applying the same model-based routing so the result matches
    what the run would use.
    """
    if context is None:
        return None

    provider = getattr(context, "provider", None)
    if provider:
        return provider

    mrc = getattr(context, "model_run_config", None)
    raw_provider = getattr(mrc, "provider", None)
    model_name = getattr(mrc, "model_name", None)
    try:
        from siada.provider.provider_factory import resolve_provider_by_model
        return resolve_provider_by_model(model_name, raw_provider)
    except Exception:
        return raw_provider


# Providers whose web tools are enabled by default in "auto" mode.
_WEB_AUTO_ON_PROVIDERS = frozenset({"li"})


def resolve_web_tools_enabled(provider: Optional[str], explicit: Optional[bool]) -> bool:

    """Resolve whether web tools should be enabled for the given provider.

    Args:
        provider: The active provider name (e.g. ``"li"``, ``"default"``).
        explicit: The user-configured tri-state value:
            - ``None``  ("auto"): default ON for ``li``, OFF otherwise.
            - ``True``:  always enable.
            - ``False``: always disable.

    Returns:
        The final boolean used to gate web_search / web_fetch.
    """
    if explicit is not None:
        return explicit
    return provider in _WEB_AUTO_ON_PROVIDERS

