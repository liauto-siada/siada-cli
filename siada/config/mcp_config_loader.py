"""
MCP Configuration Loader

Simplified MCP configuration loader using industry standard format, based on Gemini implementation.
Directly supports standard mcpServers configuration format.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
from siada.config.mcp_config import MCPConfig, MCPServerConfig, MCPTransportType
from siada.foundation.logging import logger


class MCPConfigLoader:
    """Simplified MCP configuration loader - using industry standard format"""
    
    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> MCPConfig:
        """
        Load MCP configuration from JSON file
        """
        try:
            # Determine configuration file path
            if config_path:
                config_file = Path(config_path).expanduser()
            else:
                config_file = Path("~/.siada-cli/mcp_config.json").expanduser()
            
            if not config_file.exists():
                logger.debug("MCP config file not found, using default configuration")
                return MCPConfig()
            
            # Read and parse JSON configuration
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)
            
            # Environment variable substitution
            resolved_config = cls._resolve_env_variables(raw_config)
            
            # Convert to configuration object
            return cls._convert_to_mcp_config(resolved_config)
            
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return MCPConfig()  # Return default configuration
    
    @classmethod
    def _resolve_env_variables(cls, obj: Any) -> Any:
        """
        Recursively resolve environment variables (supports ${VAR} and $VAR formats)
        Based on Gemini's resolveEnvVarsInObject implementation
        """
        if isinstance(obj, str):
            # Support both $VAR and ${VAR} formats
            env_var_regex = r'\$(?:(\w+)|{([^}]+)})'
            def replace_env_var(match):
                var_name = match.group(1) or match.group(2)
                env_value = os.getenv(var_name)
                if env_value:
                    return env_value
                logger.warning(f"Environment variable '{var_name}' not found")
                return match.group(0)  # Keep original
            
            return re.sub(env_var_regex, replace_env_var, obj)
        
        elif isinstance(obj, list):
            return [cls._resolve_env_variables(item) for item in obj]
        
        elif isinstance(obj, dict):
            return {key: cls._resolve_env_variables(value) for key, value in obj.items()}
        
        else:
            return obj
    
    @classmethod
    def _convert_to_mcp_config(cls, config: Dict[str, Any]) -> MCPConfig:
        """
        Convert configuration dictionary to MCPConfig object
        Supports standard mcpServers format and backward compatibility
        """
        servers = {}
        
        if "mcpServers" in config:
            mcp_servers = config["mcpServers"]
        else:
            mcp_servers = {}
        
        # Convert each server configuration
        for server_name, server_config in mcp_servers.items():
            try:
                servers[server_name] = cls._create_server_config(server_config)
            except Exception as e:
                logger.error(f"Failed to parse server config for '{server_name}': {e}")
                continue
        
        # Create MCP configuration object
        return MCPConfig(
            enabled=config.get("enabled", True),  # Default enabled
            servers=servers,
            auto_discover=config.get("auto_discover", True),
            global_timeout=config.get("timeout", 60000)
        )
    
    @classmethod
    def _create_server_config(cls, config: Dict[str, Any]) -> MCPServerConfig:
        """
        Create server configuration object
        Supports explicit type field or auto-detection by get_transport_type()
        """
        # Create configuration object with support for explicit type field
        return MCPServerConfig(
            type=config.get("type"),  # Explicit transport type (highest priority)
            command=config.get("command"),
            args=config.get("args"),
            env=config.get("env"),
            cwd=config.get("cwd"),
            url=config.get("url"),
            http_url=config.get("httpUrl"),  # Support standard field mapping
            headers=config.get("headers"),
            enabled=config.get("enabled", True),  # Default enabled for individual servers
            timeout=config.get("timeout", 30000),
            auto_reconnect=config.get("auto_reconnect", True)
        )
