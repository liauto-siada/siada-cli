import os
import importlib
from typing import Dict, Any, Tuple
from siada.provider.llm_client import LLMClient
import inspect

CLIENT_DIR = os.path.dirname(__file__)
client_map: Dict[str, LLMClient] = {}

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
        p_type (provider_type | None): The name of the provider, e.g., 'li', 'openrouter'. 
                                     If None, defaults to the first available client.

    Returns:
        LLMClient: The corresponding LLM client instance.

    Raises:
        ValueError: If the client name is not supported.
    """
    if p_type and p_type in client_map:
        return client_map[p_type]

    raise ValueError("No LLM clients found or registered.")


def build_chat_complete_kwargs(context: Any, default_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build chat completion kwargs by merging context parameters with defaults.
    
    Args:
        context: Context object that may contain override parameters
        default_kwargs: Default parameters for chat completion
        
    Returns:
        Dict[str, Any]: Merged kwargs with context overrides taking precedence
    """
    # Start with default kwargs
    complete_kwargs = default_kwargs.copy()
    
    # Override with context parameters if available
    if context and hasattr(context, 'model') and context.model:
        complete_kwargs['model'] = context.model
    
    if context and hasattr(context, 'temperature') and context.temperature is not None:
        complete_kwargs['temperature'] = context.temperature
    
    if context and hasattr(context, 'stream') and context.stream is not None:
        complete_kwargs['stream'] = context.stream
    
    # Add any other context parameters that might be relevant
    if context:
        # Check for additional parameters that might be set on context
        for param in ['max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty']:
            if hasattr(context, param) and getattr(context, param) is not None:
                complete_kwargs[param] = getattr(context, param)
    
    return complete_kwargs


def get_client_with_kwargs(context: Any, default_kwargs: Dict[str, Any]) -> Tuple[LLMClient, Dict[str, Any]]:
    """
    Get LLM client and build complete kwargs with context overrides.
    
    Args:
        context: Context object containing provider info and optional parameter overrides
        default_kwargs: Default parameters for chat completion
        
    Returns:
        Tuple[LLMClient, Dict[str, Any]]: Client instance and merged kwargs
    """
    # Get provider from context
    provider = None
    if context and hasattr(context, 'provider'):
        provider = context.provider
    
    # Get the client
    client = get_client(provider)
    
    # Build complete kwargs with context overrides
    complete_kwargs = build_chat_complete_kwargs(context, default_kwargs)
    
    return client, complete_kwargs
