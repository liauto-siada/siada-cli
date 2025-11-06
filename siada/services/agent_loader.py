"""
Agent loading utilities for dynamically loading agent classes from configuration.
"""
import importlib
import time
from pathlib import Path
from typing import Dict, Type

import yaml
from agents import Agent

from siada.foundation.logging import logger as logging


def load_agent_config() -> Dict[str, Dict]:
    """
    Load Agent configuration from configuration file

    Returns:
        Dict[str, Dict]: Agent configuration dictionary
        
    Raises:
        FileNotFoundError: If agent configuration file does not exist
    """
    # Get the configuration file path in the project root directory
    current_dir = Path(__file__).parent.parent.parent  # Go back to project root directory
    config_path = current_dir / "agent_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Agent configuration file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config.get('agents', {})


def get_agent_class_path(agent_name: str) -> str:
    """
    Get agent class path from configuration
    
    Args:
        agent_name: Agent name (supports case-insensitive matching)
    
    Returns:
        str: Agent class path
        
    Raises:
        ValueError: If agent not found, disabled, or not implemented
        FileNotFoundError: If configuration file does not exist
    """
    # Normalize agent name: convert to lowercase and remove underscores and hyphens
    normalized_name = agent_name.lower().replace('_', '').replace('-', '')
    
    # Load Agent mapping from configuration file
    start_time = time.time()
    agent_configs = load_agent_config()
    elapsed = time.time() - start_time
    logging.info(f"[agent_loader] Agent config loaded (took {elapsed:.3f}s)")

    # Find the corresponding Agent configuration
    agent_config = agent_configs.get(normalized_name)

    if agent_config is None:
        supported_agents = [name for name, config in agent_configs.items() 
                          if config.get('enabled', False) and config.get('class')]
        raise ValueError(
            f"Unsupported agent type: '{agent_name}'. "
            f"Supported agent types: {supported_agents}"
        )

    # Check if Agent is enabled
    if not agent_config.get('enabled', False):
        raise ValueError(f"Agent '{agent_name}' is disabled")

    # Check if Agent class is implemented
    class_path = agent_config.get('class')
    if not class_path:
        raise ValueError(f"Agent '{agent_name}' is not implemented yet")

    logging.info(f"[agent_loader] Agent class path: {class_path}")
    return class_path


def import_agent_class(class_path: str) -> Type[Agent]:
    """
    Dynamically import Agent class

    Args:
        class_path: Complete import path of Agent class, e.g. 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent'

    Returns:
        Type[Agent]: Agent class
        
    Raises:
        ImportError: If unable to import agent class
        AttributeError: If class not found in module
    """
    module_path, class_name = class_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
