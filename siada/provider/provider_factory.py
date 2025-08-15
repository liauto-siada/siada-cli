import os
import importlib
from typing import Dict, Type
from agents import ModelProvider
import inspect

PROVIDER_DIR = os.path.dirname(__file__)
provider_map: Dict[str, ModelProvider] = {}

def _discover_providers():
    """
    Dynamically discovers and registers all ModelProvider implementations.
    """
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

_discover_providers()

# The provider keys are determined dynamically, so we use `str` for type hinting.
provider_type = str


def get_provider(p_type: provider_type | None = None) -> ModelProvider:
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
    if p_type and p_type in provider_map:
        return provider_map[p_type]

    raise ValueError("No model providers found or registered.")
