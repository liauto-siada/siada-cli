"""Lark OAuth Manager"""

import json
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from siada.foundation.logging import logger
from siada.config.mcp_config import MCPConfig
from .lark_oauth_service import LarkOAuthService
from .oauth_utils import get_token_fingerprint


# Error message constants
LARK_AUTH_EXPIRED_ERROR_MESSAGE = "Lark authorization expired"
LARK_AUTH_EXPIRED_SUGGESTION = """
Solution: Lark-mcp tool authorization expired.
Always wait for user confirmation of re-authorization.
Do not resolve independently.
Use ask_followup_question tool and only provide options:
Re-authorized/Give up.
"""


class LarkOAuthManager:
    """Lark OAuth Manager"""
    
    # Default OAuth configuration
    DEFAULT_SCOPES = [
        "offline_access",  # Required for obtaining refresh_token
        "docx:document",
        "docs:doc",
        "docs:document.content:read",
        "docs:document.media:download",
        "wiki:wiki",
        "wiki:node:read",
        "bitable:app",
        "board:whiteboard:node:read",
        "auth:user.id:read",
        "drive:drive",
        "bitable:app",
    ]
    
    # Default redirect URI list (must be configured in Lark developer console)
    DEFAULT_REDIRECT_URIS = [
        "http://localhost:8077/callback",
        "http://localhost:8078/callback",
        "http://localhost:8079/callback",
        "http://localhost:8081/callback",
        "http://localhost:8082/callback",
    ]
    
    def __init__(self, mcp_config: MCPConfig, config_path: Path):
        self.mcp_config = mcp_config
        self.config_path = config_path
    
    def get_oauth_config(self, server_name: str = "lark-mcp") -> Tuple[str, str]:
        """
        Get OAuth configuration (client_id and client_secret)
        
        Args:
            server_name: MCP server name
        
        Returns:
            (client_id, client_secret)
        
        Raises:
            ValueError: If configuration is missing or incomplete
        """
        if server_name not in self.mcp_config.servers:
            raise ValueError(f"Server '{server_name}' not found in MCP config")
        
        server_config = self.mcp_config.servers[server_name]
        
        # Extract -a (client_id) and -s (client_secret) from args
        if not server_config.args:
            raise ValueError(f"No args found in server config for '{server_name}'")
        
        client_id = None
        client_secret = None
        
        args = server_config.args
        for i, arg in enumerate(args):
            if arg == '-a' and i + 1 < len(args):
                client_id = args[i + 1]
            elif arg == '-s' and i + 1 < len(args):
                client_secret = args[i + 1]
        
        if not client_id or not client_secret:
            raise ValueError(
                f"Missing client_id (-a) or client_secret (-s) in server config for '{server_name}'"
            )
        
        return client_id, client_secret
    
    async def start_oauth_flow(
        self,
        server_name: str = "lark-mcp",
        scopes: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Start the OAuth authorization flow
        
        Args:
            server_name: MCP server name
            scopes: Authorization scopes (uses default scopes if None)
        
        Returns:
            Token data
        """
        try:
            # 1. Get OAuth configuration
            client_id, client_secret = self.get_oauth_config(server_name)
            logger.info(f"Starting OAuth flow for {server_name}")
            
            # 2. Use default scopes if not specified
            # Important: offline_access must be included to obtain refresh_token
            if scopes is None:
                scopes = self.DEFAULT_SCOPES
                logger.info(f"Using default scopes: {scopes}")
            
            # 3. Create OAuth service (using default redirect URI list)
            oauth_service = LarkOAuthService(
                client_id, 
                client_secret,
                redirect_uris=self.DEFAULT_REDIRECT_URIS
            )
            
            # 4. Execute authorization flow
            token_data = await oauth_service.start_oauth_flow(scopes)
            
            logger.info(f"Token obtained: {get_token_fingerprint(token_data['access_token'])}")
            
            # 5. Update MCP config file (token stored directly in config file)
            self.update_mcp_config(server_name, token_data)
            
            return token_data
            
        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            raise
    
    def update_mcp_config(
        self,
        server_name: str,
        token_data: Dict[str, Any]
    ) -> None:
        """
        Update MCP config file (store token directly in config file)
        
        Args:
            server_name: MCP server name
            token_data: Token data
        """
        try:
            # Read config file
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if 'mcpServers' not in config or server_name not in config['mcpServers']:
                raise ValueError(f"Server '{server_name}' not found in config file")
            
            server_config = config['mcpServers'][server_name]
            
            # Update -u parameter in args
            args = server_config.get('args', [])
            
            # Remove old -u parameter (if exists)
            new_args = []
            skip_next = False
            for i, arg in enumerate(args):
                if skip_next:
                    skip_next = False
                    continue
                if arg == '-u':
                    skip_next = True
                    continue
                new_args.append(arg)
            
            # Add new -u parameter
            new_args.extend(['-u', token_data['access_token']])
            server_config['args'] = new_args
            
            # Add oauth object (note: client_id and client_secret are not stored here, read from args)
            server_config['oauth'] = {
                'expires_in': token_data.get('expires_in', 7200),
                'refresh_token': token_data.get('refresh_token'),
                'refresh_token_expires_in': token_data.get('refresh_token_expires_in', 604800),
                'token_created_time': token_data['token_created_time']
            }
            
            # Write back to config file
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # Set file permissions to 0600
            os.chmod(self.config_path, 0o600)
            
            logger.info(f"MCP config updated for {server_name}")
            
        except Exception as e:
            logger.error(f"Failed to update MCP config: {e}")
            raise
    
    def should_refresh_token(
        self,
        server_name: str = "lark-mcp",
        buffer_minutes: int = 5
    ) -> bool:
        """
        Check if the token needs to be refreshed
        
        Args:
            server_name: MCP server name
            buffer_minutes: Buffer time in minutes before expiry to trigger refresh
        
        Returns:
            Whether a refresh is needed
        """
        if server_name not in self.mcp_config.servers:
            return False
        
        server_config = self.mcp_config.servers[server_name]
        oauth_data = server_config.oauth
        
        if not oauth_data:
            return False
        
        token_created_time = oauth_data.get('token_created_time', 0)
        expires_in = oauth_data.get('expires_in', 7200)
        
        # Current time (milliseconds)
        current_time = int(time.time() * 1000)
        
        # Token expiry time (milliseconds)
        expiry_time = token_created_time + (expires_in * 1000)
        
        # Buffer time (milliseconds)
        buffer_ms = buffer_minutes * 60 * 1000
        
        # Refresh needed if current time >= expiry time - buffer time
        return current_time >= (expiry_time - buffer_ms)
    
    def is_refresh_token_expired(
        self,
        server_name: str = "lark-mcp"
    ) -> bool:
        """
        Check if the refresh_token has expired
        
        Args:
            server_name: MCP server name
        
        Returns:
            Whether the refresh_token is expired
        """
        if server_name not in self.mcp_config.servers:
            return True
        
        server_config = self.mcp_config.servers[server_name]
        oauth_data = server_config.oauth
        
        if not oauth_data:
            return True
        
        token_created_time = oauth_data.get('token_created_time', 0)
        refresh_token_expires_in = oauth_data.get('refresh_token_expires_in', 604800)
        
        # Current time (milliseconds)
        current_time = int(time.time() * 1000)
        
        # refresh_token expiry time (milliseconds)
        expiry_time = token_created_time + (refresh_token_expires_in * 1000)
        
        return current_time >= expiry_time
    
    async def refresh_access_token(
        self,
        server_name: str = "lark-mcp"
    ) -> Dict[str, Any]:
        """
        Refresh the access token
        
        Args:
            server_name: MCP server name
        
        Returns:
            New token data
        
        Raises:
            RuntimeError: If refresh fails or refresh_token is expired
        """
        try:
            # Check if refresh_token is expired
            if self.is_refresh_token_expired(server_name):
                raise RuntimeError(LARK_AUTH_EXPIRED_ERROR_MESSAGE)
            
            # Get OAuth configuration and current token
            client_id, client_secret = self.get_oauth_config(server_name)
            
            server_config = self.mcp_config.servers[server_name]
            oauth_data = server_config.oauth
            
            if not oauth_data or not oauth_data.get('refresh_token'):
                raise RuntimeError("No refresh token available")
            
            refresh_token = oauth_data['refresh_token']
            
            # Perform refresh
            oauth_service = LarkOAuthService(client_id, client_secret)
            token_data = await oauth_service.refresh_token(refresh_token)
            
            logger.info(f"Token refreshed: {get_token_fingerprint(token_data['access_token'])}")
            
            # If the returned token_data does not contain a new refresh_token, use the old one
            if 'refresh_token' not in token_data:
                token_data['refresh_token'] = refresh_token
            
            # Update MCP config (token stored directly in config file)
            self.update_mcp_config(server_name, token_data)
            
            return token_data
            
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise
