"""
Sub Agent Registry Service

This module provides functionality to automatically register sub agents with a backend service
when the A2A API server starts. It discovers agents by scanning the agents directory and
reading their agent.json configuration files.
"""

import json
import os
import socket
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

import requests

from siada.foundation.logging import logger


def generate_agent_configs_from_templates(agents_dir: str, host: str, port: int) -> List[str]:
    """
    Generate agent.json config files from template files.

    Scans the agents directory for all agent.json.template files,
    replaces the placeholders ({{HOST}} and {{PORT}}), and writes
    the corresponding agent.json files.

    Args:
        agents_dir: Path to the agents directory
        host: Host IP address
        port: Service port number

    Returns:
        List[str]: Paths of successfully generated agent.json files

    Raises:
        FileNotFoundError: When a template file does not exist
        json.JSONDecodeError: When a template file is not valid JSON
    """
    agents_path = Path(agents_dir)
    generated_files = []
    
    if not agents_path.exists():
        logger.warning(f"Agents directory not found: {agents_dir}")
        return generated_files
    
    # Iterate over all subdirectories to find agent.json.template
    for item in agents_path.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            template_path = item / "agent.json.template"
            output_path = item / "agent.json"
            
            if template_path.exists():
                try:
                    # Read template file
                    with open(template_path, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    
                    # Replace placeholders
                    config_content = template_content.replace('{{HOST}}', host)
                    config_content = config_content.replace('{{PORT}}', str(port))
                    
                    # Validate that generated content is valid JSON
                    json.loads(config_content)
                    
                    # Write generated config file
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(config_content)
                    
                    generated_files.append(str(output_path))
                    logger.info(f"Generated {output_path} from template (host={host}, port={port})")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in template {template_path}: {e}")
                except Exception as e:
                    logger.error(f"Failed to generate config from {template_path}: {e}")
            else:
                # If no template file but agent.json exists, give a warning
                if output_path.exists():
                    logger.warning(
                        f"No template found for {item.name}, using existing agent.json. "
                        f"Consider creating {template_path.name} for dynamic configuration."
                    )
                else:
                    logger.warning(f"No template or config found for {item.name}")
    
    return generated_files


@dataclass
class SubAgentInfo:
    """Sub Agent information"""
    name: str
    description: str
    config_path: str
    agent_dir: str


def discover_sub_agents(agents_dir: str) -> List[SubAgentInfo]:
    """
    Scan the agents directory and discover all sub agents that contain an agent.json.

    Args:
        agents_dir: Path to the agents directory

    Returns:
        List[SubAgentInfo]: List of discovered sub agents
    """
    agents_path = Path(agents_dir)
    discovered_agents = []
    
    if not agents_path.exists():
        logger.warning(f"Agents directory not found: {agents_dir}")
        return discovered_agents
    
    # Iterate over all subdirectories to find agent.json
    for item in agents_path.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            agent_json_path = item / "agent.json"
            if agent_json_path.exists():
                try:
                    with open(agent_json_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    agent_info = SubAgentInfo(
                        name=config.get('name', item.name),
                        description=config.get('description', ''),
                        config_path=str(agent_json_path),
                        agent_dir=str(item)
                    )
                    discovered_agents.append(agent_info)
                    logger.debug(f"Discovered sub agent: {agent_info.name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to parse {agent_json_path}: {e}")
    
    return discovered_agents


def get_local_ip() -> str:
    """
    Get the local LAN IP address.

    Returns:
        str: Local IP address, or 127.0.0.1 on failure
    """
    try:
        # Method 1: Get local IP by connecting to an external address (most accurate)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # No actual connection needed, just used to get routing information
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            logger.debug(f"Detected local IP: {local_ip}")
            return local_ip
    except Exception as e:
        logger.debug(f"Method 1 failed to get local IP: {e}")
    
    try:
        # Method 2: Get via hostname
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip and not local_ip.startswith('127.'):
            logger.debug(f"Detected local IP via hostname: {local_ip}")
            return local_ip
    except Exception as e:
        logger.debug(f"Method 2 failed to get local IP: {e}")
    
    # Fall back to localhost
    logger.warning("Could not detect local IP, using 127.0.0.1")
    return "127.0.0.1"


def build_backend_url(config: 'SubAgentRegistryConfig') -> str:
    """
    Build the full backend API URL.

    Two ways to determine the backend_url are supported:
    1. Explicit backend_url from the config file
    2. Auto-selected based on environment using a mapping table

    Environment identifier sources:
    - SIADA_ENV environment variable (global unified env identifier)
    - config.environment from the config file

    Args:
        config: Registry configuration

    Returns:
        str: Full registration API URL
    """
    # Environment to URL mapping table
    ENV_URL_MAPPINGS = {
        'prod': 'agent-manager.inner.chj.cloud',
        'dev': 'agent-manager-dev.inner.chj.cloud',
        'local': 'localhost:8000'
    }
    
    # Get environment identifier (using global SIADA_ENV)
    environment = os.getenv('SIADA_ENV', config.environment).lower()
    
    # Determine backend_url (priority: mapping table > config file)
    if environment in ENV_URL_MAPPINGS:
        # Environment is in mapping table, prefer mapping table value
        backend_url = ENV_URL_MAPPINGS[environment]
        logger.info(f"Using mapped URL for environment '{environment}': {backend_url}")
    elif config.backend_url and config.backend_url.strip():
        # Environment not in mapping table, use config file value
        backend_url = config.backend_url
        logger.info(f"Using backend_url from config: {backend_url}")
    else:
        # Neither found, fall back to prod default value
        backend_url = ENV_URL_MAPPINGS['prod']
        logger.warning(f"No backend_url configured, using default prod: {backend_url}")
    
    # Ensure protocol prefix exists
    if not backend_url.startswith(('http://', 'https://')):
        protocol = 'http' if 'localhost' in backend_url or '127.0.0.1' in backend_url else 'https'
        backend_url = f"{protocol}://{backend_url}"
    
    # Remove trailing slash and append fixed path directly
    backend_url = backend_url.rstrip('/')
    full_url = f"{backend_url}/api/sub-agents/register"
    
    logger.debug(f"Backend registration URL: {full_url}")
    return full_url


def register_single_agent(
    agent: SubAgentInfo,
    server_ip: str,
    server_port: int,
    backend_url: str,
    timeout: int = 10,
    li_user_id: str = "",
    agent_type: str = "custom"
) -> Optional[Dict]:
    """
    Register a single sub agent with the backend.

    Args:
        agent: Sub agent information
        server_ip: Server IP address
        server_port: Server port
        backend_url: Backend registration API URL
        timeout: Request timeout in seconds
        li_user_id: User ID (optional, passed to agent-manager for user association)
        agent_type: Agent type, "builtin" or "custom" (optional)

    Returns:
        Optional[Dict]: Response data on success, None on failure
    """
    payload = {
        "ip": server_ip,
        "port": server_port,
        "agent_name": agent.name,
        "desc": agent.description
    }
    if li_user_id:
        payload["user_id"] = li_user_id
    if agent_type:
        payload["agent_type"] = agent_type
    
    try:
        logger.info(f"Registering {agent.name} to {backend_url}")
        logger.debug(f"Registration payload: {payload}")
        
        response = requests.post(
            backend_url,
            json=payload,
            timeout=timeout,
            headers={'Content-Type': 'application/json'}
        )
        
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"Successfully registered {agent.name}, response: {result}")
        return result
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout registering {agent.name} (timeout: {timeout}s)")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error registering {agent.name}: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error registering {agent.name}: {e}")
        if hasattr(e.response, 'text'):
            logger.debug(f"Response: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error registering {agent.name}: {e}")
        return None


def register_sub_agents(
    agents: List[SubAgentInfo],
    config: 'SubAgentRegistryConfig',
    server_port: int,
    io: 'InputOutput'
) -> Dict[str, bool]:
    """
    Register all sub agents with the backend.

    Args:
        agents: List of sub agents
        config: Registry configuration
        server_port: Server port
        io: InputOutput instance for displaying messages

    Returns:
        Dict[str, bool]: Registration status for each agent {agent_name: success}
    """
    results = {}
    
    if not agents:
        io.print_warning("No sub agents found to register")
        return results
    
    # Get local IP
    server_ip = get_local_ip()
    io.print_info(f"Server IP: {server_ip}")
    io.print_info(f"Server Port: {server_port}")
    
    # Build backend URL
    try:
        backend_url = build_backend_url(config)
        io.print_info(f"Backend URL: {backend_url}")
    except Exception as e:
        io.print_error(f"Failed to build backend URL: {e}")
        return {agent.name: False for agent in agents}
    
    # Register each agent
    io.print_info(f"Registering {len(agents)} sub agent(s)...")
    
    for agent in agents:
        result = register_single_agent(
            agent=agent,
            server_ip=server_ip,
            server_port=server_port,
            backend_url=backend_url,
            timeout=config.timeout
        )
        
        success = result is not None
        results[agent.name] = success
        
        if success:
            # Try to get sub_agent_id from response
            if isinstance(result, dict):
                data = result.get('data', {})
                agent_id = data.get('sub_agent_id', 'N/A')
                io.print_info(f"  ✓ {agent.name} registered (ID: {agent_id})")
            else:
                io.print_info(f"  ✓ {agent.name} registered")
        else:
            io.print_warning(f"  ⚠ {agent.name} registration failed")
    
    # Show summary
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    if success_count == total_count:
        io.print_info(f"✓ All {total_count} agent(s) registered successfully")
    elif success_count > 0:
        io.print_warning(f"⚠ {success_count}/{total_count} agent(s) registered")
    else:
        io.print_warning(f"⚠ No agents registered successfully")
    
    return results
