from __future__ import annotations

import os
import importlib
import inspect
from typing import TYPE_CHECKING, Dict, Any, Tuple, Optional

from siada.foundation.context import get_context_var, MODEL_PROVIDER_NAME, LLM_CONFIG
from siada.foundation.logging import logger
from siada.provider.llm_client import LLMClient

if TYPE_CHECKING:
    from agents import ModelResponse

CLIENT_DIR = os.path.dirname(__file__)
client_map: Dict[str, LLMClient] = {}

# Provider key this build ships: it talks to the endpoint the user configured
# (custom base URL + API key, or any OpenAI-compatible service).
DEFAULT_PROVIDER_KEY = "default"

# Provider names already reported as unknown, so a stale key in conf.yaml warns
# once instead of on every request.
_unknown_providers_warned: set[str] = set()

def _discover_clients():
    """
    Dynamically discovers and registers all LLMClient implementations.
    """
    for item in os.listdir(CLIENT_DIR):
        item_path = os.path.join(CLIENT_DIR, item)
        if os.path.isdir(item_path):
            client_key = item
            for file_name in os.listdir(item_path):
                if file_name.endswith(".py") and file_name != "__init__.py":
                    module_name = f"siada.provider.{client_key}.{file_name[:-3]}"
                    try:
                        module = importlib.import_module(module_name)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if inspect.isclass(attr) and issubclass(attr, LLMClient) and attr is not LLMClient:
                                client_map[client_key] = attr()
                    except ImportError as e:
                        print(f"Error importing client module {module_name}: {e}")

_discover_clients()

# The client keys are determined dynamically, so we use `str` for type hinting.
provider_type = str


def get_client(p_type: provider_type | None = None) -> LLMClient:
    """
    Retrieves the LLM client instance based on the client name.

    Args:
        p_type (provider_type | None): The name of the provider. This build
            registers ``default``, which talks to the endpoint the user
            configured. An unknown or legacy name (for example a provider key
            left over from another distribution) resolves to that same client
            rather than failing the request; ``None`` behaves the same way.

    Returns:
        LLMClient: The corresponding LLM client instance.

    Raises:
        ValueError: If no LLM client is registered at all.
    """
    if p_type and p_type in client_map:
        return client_map[p_type]

    fallback = client_map.get(DEFAULT_PROVIDER_KEY)
    if fallback is None and len(client_map) == 1:
        # Single-provider build: that provider is the user endpoint by definition.
        fallback = next(iter(client_map.values()))

    if fallback is not None:
        if p_type and p_type not in _unknown_providers_warned:
            _unknown_providers_warned.add(p_type)
            logger.warning(
                "Unknown LLM provider %r; using the '%s' client (user-configured "
                "endpoint) instead.",
                p_type,
                DEFAULT_PROVIDER_KEY if DEFAULT_PROVIDER_KEY in client_map else next(iter(client_map)),
            )
        return fallback

    raise ValueError("No LLM clients found or registered.")


def build_chat_complete_kwargs(default_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build chat completion kwargs by merging context parameters with defaults.
    
    Args:
        default_kwargs: Default parameters for chat completion
        
    Returns:
        Dict[str, Any]: Merged kwargs with context overrides taking precedence
    """
    # Start with default kwargs
    complete_kwargs = default_kwargs.copy()
    
    llm_config = get_context_var(LLM_CONFIG)
    complete_kwargs['model'] = llm_config.model_name


    return complete_kwargs


def get_client_with_kwargs(default_kwargs: Dict[str, Any]) -> Tuple[LLMClient, Dict[str, Any]]:
    """
    Get LLM client and build complete kwargs with context overrides.
    
    Args:
        context: Context object containing provider info and optional parameter overrides
        default_kwargs: Default parameters for chat completion
        
    Returns:
        Tuple[LLMClient, Dict[str, Any]]: Client instance and merged kwargs
    """
    # Get provider from context
    llm_config = get_context_var(LLM_CONFIG)
    provider = llm_config.provider
    
    # Get the client
    client = get_client(provider)
    
    # Build complete kwargs with context overrides
    complete_kwargs = build_chat_complete_kwargs(default_kwargs)
    
    return client, complete_kwargs


async def simple_completion(
    prompt: str,
    *,
    agent_name: Optional[str] = None,
    **kwargs
) -> ModelResponse:
    """
    Simplified LLM completion interface - just pass context and prompt.

    Resolves the active model configuration and makes one wrapped SDK model
    request without Agent/Runner or the legacy client completion transport.

    Args:
        prompt: The user prompt to send to the LLM
        agent_name: Optional override for the AGENT_NAME context variable for
            the duration of this call only. Use this when a non-agent code path
            invokes `simple_completion` and wants the request to show up in
            server-side analytics with a meaningful tag (e.g. "bug_desc_optimizer")
            instead of inheriting whatever the surrounding coroutine had set.
            The previous value is restored automatically, so the override never
            leaks into subsequent work on the same task.
        **kwargs: Optional parameters like temperature, max_tokens, timeout, etc.
                  Will override defaults if provided.

    Returns:
        ModelResponse: The SDK response. Errors propagate to the caller.

    Example:
        # Basic usage
        response = await simple_completion("Generate a slug for: user discussion")

        # With custom parameters
        response = await simple_completion(
            "Analyze this code",
            temperature=0.5,
            max_tokens=500,
            agent_name="code_analysis",
        )
    """
    from siada.provider.one_shot import one_shot_completion

    llm_config = get_context_var(LLM_CONFIG)
    options = dict(kwargs)
    options["model"] = llm_config.model_name
    options["provider"] = llm_config.provider
    return await one_shot_completion(
        prompt,
        agent_name=agent_name,
        **options,
    )
