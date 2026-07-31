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
from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger


class MCPConfigLoader:
    """Simplified MCP configuration loader - using industry standard format"""
    
    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> MCPConfig:
        """
        Load MCP configuration from JSON file
        
        Loading strategy:
        1. If explicit config_path is provided, use that file only
        2. If both project and home configs exist, merge them (project config has priority)
        3. If only one config exists (project or home), use that one
        4. If no config exists, return default disabled configuration
        
        Merge strategy (when both exist):
        - mcpServers: merge server definitions, project servers override home servers with same name
        - Other settings: project config overrides home config
        """
        try:
            # Determine configuration file path(s)
            if config_path:
                config_file = Path(config_path).expanduser()
                if not config_file.exists():
                    logger.warning(f"Specified MCP config file not found: {config_file}")
                    return MCPConfig(enabled=False)
                
                logger.debug(f"Loading MCP config from: {config_file}")
                
                # Read and parse JSON configuration
                with open(config_file, 'r', encoding='utf-8') as f:
                    raw_config = json.load(f)
                
                # Environment variable substitution
                resolved_config = cls._resolve_env_variables(raw_config)

                # Inject MCP servers from enabled plugins (lowest priority)
                try:
                    from siada.services.plugins.mcp_integration import inject_plugin_mcp_servers
                    resolved_config = inject_plugin_mcp_servers(resolved_config)
                except Exception as _e:
                    logger.warning(f"Failed to inject plugin MCP servers: {_e}")

                # Convert to configuration object
                return cls._convert_to_mcp_config(resolved_config)
            else:
                # Search for config files and merge if both exist
                config_files = cls._find_config_files()
                if not config_files:
                    logger.debug("MCP config file not found in any location, using default configuration")
                    return MCPConfig(enabled=False)
                
                # Load and merge configurations
                merged_config = cls._load_and_merge_configs(config_files)
                
                # Environment variable substitution
                resolved_config = cls._resolve_env_variables(merged_config)

                # Inject MCP servers from enabled plugins (lowest priority)
                try:
                    from siada.services.plugins.mcp_integration import inject_plugin_mcp_servers
                    resolved_config = inject_plugin_mcp_servers(resolved_config)
                except Exception as _e:
                    logger.warning(f"Failed to inject plugin MCP servers: {_e}")

                # Convert to configuration object
                return cls._convert_to_mcp_config(resolved_config)
            
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return MCPConfig()  # Return default configuration
    
    @classmethod
    def _find_config_files(cls) -> list[Path]:
        """
        Find MCP configuration files in multiple locations
        
        Search locations:
        1. Project root directory (siada_mcp_config.json)
        2. User home directory (~/.siada-cli/mcp_config.json)
        
        Returns:
            List of found config file paths (may contain 0, 1, or 2 paths)
        """
        config_files = []
        
        # 1. Check project root directory
        project_config = Path.cwd() / "siada_mcp_config.json"
        if project_config.exists():
            logger.debug(f"Found MCP config in project root: {project_config}")
            config_files.append(project_config)
        
        # 2. Check user home directory
        home_config = SIADA_HOME / "mcp_config.json"
        if home_config.exists():
            logger.debug(f"Found MCP config in user home: {home_config}")
            config_files.append(home_config)
        
        return config_files
    
    @classmethod
    def _load_and_merge_configs(cls, config_files: list[Path]) -> Dict[str, Any]:
        """
        Load and merge multiple configuration files
        
        Merge strategy:
        - Project config has higher priority than home config
        - For mcpServers: merge server definitions (project servers override home servers with same name)
        - For other settings: project config overrides home config
        
        Args:
            config_files: List of config file paths to load and merge
            
        Returns:
            Merged configuration dictionary
        """
        if not config_files:
            return {}
        
        if len(config_files) == 1:
            # Only one config file, load it directly
            logger.debug(f"Loading MCP config from: {config_files[0]}")
            with open(config_files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Multiple config files - merge them
        # Load home config first (lower priority)
        home_config = {}
        project_config = {}
        
        for config_file in config_files:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                if config_file.name == "siada_mcp_config.json" and config_file.parent == Path.cwd():
                    # Project config
                    project_config = config
                    logger.debug(f"Loading project MCP config from: {config_file}")
                else:
                    # Home config
                    home_config = config
                    logger.debug(f"Loading home MCP config from: {config_file}")
        
        # Merge configurations
        merged = home_config.copy()
        
        # Merge mcpServers
        if "mcpServers" in home_config or "mcpServers" in project_config:
            merged_servers = home_config.get("mcpServers", {}).copy()
            merged_servers.update(project_config.get("mcpServers", {}))
            merged["mcpServers"] = merged_servers
        
        # Override other settings with project config
        for key, value in project_config.items():
            if key != "mcpServers":
                merged[key] = value
        
        logger.debug(f"Merged MCP configs: {len(merged.get('mcpServers', {}))} total servers")
        
        return merged
    
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
            auto_reconnect=config.get("auto_reconnect", True),
            oauth=config.get("oauth")  # OAuth configuration for lark-mcp
        )
