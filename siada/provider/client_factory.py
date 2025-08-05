import os
import importlib
from typing import Dict
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
client_type = str


def get_client(c_type: client_type | None = None) -> LLMClient:
    """
    Retrieves the LLM client instance based on the client name.

    Args:
        c_type (client_type | None): The name of the client, e.g., 'li', 'openrouter'. 
                                     If None, defaults to the first available client.

    Returns:
        LLMClient: The corresponding LLM client instance.

    Raises:
        ValueError: If the client name is not supported.
    """
    if c_type and c_type in client_map:
        return client_map[c_type]

    raise ValueError("No LLM clients found or registered.")
