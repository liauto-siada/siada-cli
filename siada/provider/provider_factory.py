import os
import importlib
from typing import Dict, Optional, Type
import inspect

PROVIDER_DIR = os.path.dirname(__file__)
provider_map: Dict = {}
_providers_discovered = False

# Legacy provider keys that no longer ship their own provider implementation.
# Old sessions/configs may still carry these names; alias them to their
# successor so they keep working.
_LEGACY_PROVIDER_ALIASES = {"openai_agents": "li"}


def _normalize_provider_key(p_type: Optional[str]) -> Optional[str]:
    """Map legacy provider keys to their current equivalent."""
    if p_type in _LEGACY_PROVIDER_ALIASES:
        return _LEGACY_PROVIDER_ALIASES[p_type]
    return p_type


def resolve_provider_by_model(model_name: Optional[str], default_provider: Optional[str] = None) -> Optional[str]:
    """
    Resolve the provider name for a given model.

    Protocol routing (e.g. GPT-5.x models going through the native OpenAI
    Responses API) is handled inside each provider itself — both ``li`` and
    ``default`` route Responses-only models to ``ResponsesModel`` with their
    own transport. This hook remains for provider-level overrides; currently
    no special rules apply and ``default_provider`` is always returned
    (after legacy-key normalization).

    Args:
        model_name: The name of the model (e.g. ``"gpt-5.4"``, ``"claude-sonnet-4.6"``).
        default_provider: The provider the caller would otherwise use.

    Returns:
        ``default_provider`` with legacy keys aliased to their successor.
    """
    return _normalize_provider_key(default_provider)

def _discover_providers():
    """
    Dynamically discovers and registers all ModelProvider implementations.
    Lazy: called on first get_provider() invocation so that importing this module
    does NOT trigger the heavy `from agents import ModelProvider` cold import.
    """
    global _providers_discovered
    if _providers_discovered:
        return
    _providers_discovered = True
    from agents import ModelProvider  # heavy import — deferred until first get_provider() call
    for item in os.listdir(PROVIDER_DIR):
        item_path = os.path.join(PROVIDER_DIR, item)
        if os.path.isdir(item_path):
            provider_key = item
            for file_name in os.listdir(item_path):
                if file_name.endswith("_provider.py"):
                    module_name = f"siada.provider.{provider_key}.{file_name[:-3]}"
                    try:
                        module = importlib.import_module(module_name)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if inspect.isclass(attr) and issubclass(attr, ModelProvider) and attr is not ModelProvider:
                                provider_map[provider_key] = attr()
                    except ImportError as e:
                        print(f"Error importing provider module {module_name}: {e}")

# The provider keys are determined dynamically, so we use `str` for type hinting.
provider_type = str


def get_provider(p_type: provider_type | None = None):
    """
    Retrieves the model provider instance based on the provider name.

    Args:
        p_type (provider_type | None): The name of the provider, e.g., 'li'. 
                                           If None, defaults to the first available provider.

    Returns:
        ModelProvider: The corresponding model provider instance.

    Raises:
        ValueError: If the provider name is not supported.
    """
    _discover_providers()  # lazy init — first call imports agents SDK
    p_type = _normalize_provider_key(p_type)
    if p_type and p_type in provider_map:
        return provider_map[p_type]

    raise ValueError("No model providers found or registered.")
