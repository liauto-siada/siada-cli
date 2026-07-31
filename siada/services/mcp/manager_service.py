
"""
MCP Service using MCPServerManager from agents framework
Provides hot-reload capability and better server management
"""
from __future__ import annotations

import asyncio
import atexit
import hashlib
import re
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass
from pathlib import Path

# agents.mcp types are lazy-imported inside the functions that use them
# (MCPServerFactory.create_server and MCPManagerService.initialize) to avoid
# pulling in the agents SDK (~500ms) at module load / startup time.
if TYPE_CHECKING:
    from agents.mcp import MCPServerManager, MCPServer
    from agents.mcp import MCPServerStdio, MCPServerStreamableHttp, MCPServerSse

from siada.config.mcp_config import MCPConfig, MCPServerConfig, MCPTransportType
from siada.config.mcp_config_loader import MCPConfigLoader
from siada.foundation.logging import logger


@dataclass
class ToolConflictInfo:
    """Information about a tool name conflict"""
    original_name: str
    new_name: str
    server_name: str
    conflict_reason: str


class MCPToolNameResolver:
    """Resolves tool name conflicts between Siada and MCP tools"""
    
    SIADA_NATIVE_TOOLS = {
        "edit_file", 
    }
    
    def __init__(self):
        self.conflicts: List[ToolConflictInfo] = []
        self.renamed_tools: Dict[str, str] = {}
    
    def resolve_tool_conflicts(self, mcp_servers: List[MCPServer]) -> List[ToolConflictInfo]:
        self.conflicts.clear()
        self.renamed_tools.clear()
        
        for server in mcp_servers:
            server_conflicts = self._resolve_server_tool_conflicts(server)
            self.conflicts.extend(server_conflicts)
        
        if self.conflicts:
            for conflict in self.conflicts:
                logger.debug(f"  {conflict.original_name} -> {conflict.new_name} ({conflict.server_name})")
        
        return self.conflicts
    
    def _resolve_server_tool_conflicts(self, server: MCPServer) -> List[ToolConflictInfo]:
        conflicts = []
        
        if not hasattr(server, '_tools_list') or server._tools_list is None:
            logger.debug(f"Server {server.name} tools list not yet loaded, skipping conflict resolution")
            return conflicts
        
        for tool in server._tools_list:
            original_name = tool.name
            
            if original_name in self.SIADA_NATIVE_TOOLS:
                new_name = self._generate_prefixed_name(server.name, original_name)
                tool.name = new_name
                
                conflict_info = ToolConflictInfo(
                    original_name=original_name,
                    new_name=new_name,
                    server_name=server.name,
                    conflict_reason=f"Conflicts with Siada native tool '{original_name}'"
                )
                
                conflicts.append(conflict_info)
                self.renamed_tools[original_name] = new_name
        
        return conflicts
    
    def _generate_prefixed_name(self, server_name: str, tool_name: str) -> str:
        clean_server_name = self._clean_server_name(server_name)
        return f"{clean_server_name}_{tool_name}"
    
    def _clean_server_name(self, server_name: str) -> str:
        clean_name = re.sub(r'[^\w]', '_', server_name)
        clean_name = re.sub(r'_+', '_', clean_name)
        clean_name = clean_name.strip('_')
        clean_name = clean_name.lower()
        
        if not clean_name:
            clean_name = "mcp"
        
        return clean_name


class MCPServerFactory:
    """Factory for creating MCP server instances"""
    
    @staticmethod
    def create_server(server_name: str, server_config: MCPServerConfig) -> Optional[MCPServer]:
        """Create a server instance based on configuration"""
        if not server_config.enabled:
            logger.info(f"Skipping disabled MCP server: {server_name}")
            return None
        
        transport_type = server_config.get_transport_type()
        
        try:
            from agents.mcp import MCPServerStdio, MCPServerStreamableHttp, MCPServerSse  # lazy: agents SDK
            if transport_type == MCPTransportType.STDIO:
                return MCPServerStdio(
                    params={
                        "command": server_config.command,
                        "args": server_config.args or [],
                        "env": server_config.env or {},
                        "cwd": server_config.cwd
                    },
                    cache_tools_list=True,
                    name=server_name,
                    client_session_timeout_seconds=server_config.timeout / 1000.0
                )
            
            elif transport_type == MCPTransportType.HTTP:
                http_url = server_config.url or server_config.http_url
                return MCPServerStreamableHttp(
                    name=server_name,
                    params={
                        "url": http_url,
                        "headers": server_config.headers or {},
                        "timeout": server_config.timeout / 1000.0,
                        "terminate_on_close": True,
                    },
                    client_session_timeout_seconds=300,
                    cache_tools_list=True
                )
            
            elif transport_type == MCPTransportType.SSE:
                return MCPServerSse(
                    name=server_name,
                    params={
                        "url": server_config.url,
                        "headers": server_config.headers or {},
                        "timeout": server_config.timeout / 1000.0,
                        "sse_read_timeout": 300.0
                    },
                    cache_tools_list=True
                )
            else:
                logger.error(f"Unsupported transport type: {transport_type}")
                return None
        
        except ImportError as e:
            logger.error(f"Failed to import MCP server class: {e}")
            logger.error("Please ensure installed: pip install 'openai-agents[mcp]'")
            return None
        except Exception as e:
            logger.error(f"Failed to create {transport_type} server '{server_name}': {e}")
            return None


class MCPManagerService:
    """MCP service using MCPServerManager"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config: Optional[MCPConfig] = None
        self.config_path = config_path
        self.manager: Optional[MCPServerManager] = None
        self._initialized = False
        self.io = None
        self.tool_name_resolver = MCPToolNameResolver()
        
        # Register cleanup hook on program exit
        atexit.register(self._cleanup_on_exit)
    
    def set_io(self, io):
        """Set the IO object"""
        self.io = io
    
    def set_mcp_config(self, mcp_config: MCPConfig):
        """Set the MCP configuration"""
        self.config = mcp_config
    
    def has_config(self) -> bool:
        """Check if configuration exists"""
        return self.config is not None and self.config.enabled
    
    def get_mcp_config(self) -> Optional[MCPConfig]:
        """Get the MCP configuration"""
        return self.config
    
    @property
    def is_initialized(self) -> bool:
        """Check if the service is initialized"""
        return self._initialized
    
    async def initialize(self) -> List[MCPServer]:
        """Initialize the MCP service"""
        if not self.has_config():
            logger.info("MCP service is disabled or has no configuration")
            return []
        
        if self._initialized:
            logger.debug("MCP service already initialized")
            return self.manager.active_servers if self.manager else []
        
        try:
            logger.info("Initializing MCP service...")
            
            # Create server list
            servers = self._create_servers_from_config()
            if not servers:
                logger.warning("No valid MCP servers found")
                self._initialized = True
                return []
            
            # Use MCPServerManager
            from agents.mcp import MCPServerManager  # lazy: agents SDK
            self.manager = MCPServerManager(
                servers=servers,
                connect_timeout_seconds=10.0,
                cleanup_timeout_seconds=10.0,
                drop_failed_servers=True,
                strict=False,
                connect_in_parallel=True
            )
            
            # Connect all servers
            await self.manager.connect_all()
            
            # Resolve tool name conflicts
            if self.manager.active_servers:
                await self._resolve_tool_conflicts()
            
            self._initialized = True
            logger.info(f"MCP service initialization complete: {len(self.manager.active_servers)} active server(s)")
            
            return self.manager.active_servers
        
        except Exception as e:
            logger.error(f"MCP service initialization failed: {e}")
            self._initialized = False
            raise
    
    def _create_servers_from_config(self) -> List[MCPServer]:
        """Create server list from configuration"""
        servers = []
        
        if not self.config:
            return servers
        
        for server_name, server_config in self.config.servers.items():
            try:
                server = MCPServerFactory.create_server(server_name, server_config)
                if server:
                    servers.append(server)
                    logger.info(f"Created MCP server: {server_name}")
            except Exception as e:
                logger.error(f"Failed to create server '{server_name}': {e}")
        
        return servers
    
    async def _resolve_tool_conflicts(self):
        """Resolve tool name conflicts"""
        try:
            # Preload tool lists
            await self._preload_tools_cache()
            
            conflicts = self.tool_name_resolver.resolve_tool_conflicts(
                self.manager.active_servers
            )
            
            if conflicts:
                logger.info(f"Resolved {len(conflicts)} tool name conflict(s):")
                for conflict in conflicts:
                    logger.info(f"  • {conflict.original_name} → {conflict.new_name}")
        
        except Exception as e:
            logger.error(f"Tool conflict resolution failed: {e}")
    
    async def _preload_tools_cache(self):
        """Preload tool lists for all active servers.
        
        Servers that fail list_tools (e.g. returning invalid response format)
        are removed from the active list so they won't block agent runs.
        """
        logger.debug("Preloading MCP tool lists...")
        
        failed_servers: list[tuple[MCPServer, Exception]] = []
        _LIST_TOOLS_TIMEOUT = 20.0

        for server in list(self.manager.active_servers):
            try:
                await asyncio.wait_for(server.list_tools(None, None), timeout=_LIST_TOOLS_TIMEOUT)
                logger.debug(f"Server {server.name} tool list loaded successfully")
            except asyncio.TimeoutError as e:
                logger.warning(
                    f"MCP server '{server.name}' list_tools timed out after {_LIST_TOOLS_TIMEOUT}s, "
                    f"removing from active servers"
                )
                failed_servers.append((server, e))
            except Exception as e:
                logger.warning(
                    f"MCP server '{server.name}' list_tools failed, "
                    f"removing from active servers: {e}"
                )
                failed_servers.append((server, e))
        
        # Remove servers whose list_tools returned invalid data,
        # preventing them from crashing the agent run later.
        if failed_servers:
            for server, exc in failed_servers:
                self.manager._record_failure(server, exc, phase="list_tools")
            self.manager._refresh_active_servers()
            logger.warning(
                f"Removed {len(failed_servers)} server(s) that failed list_tools: "
                f"{', '.join(s.name for s, _ in failed_servers)}"
            )
        
        logger.debug("Tool list preloading complete")
    
    async def check_and_refresh_lark_token(self) -> None:
        """
        Check and refresh the Lark MCP token if needed.
        
        This method will:
        1. Check if the lark-mcp server is configured
        2. Verify whether the access token is about to expire (within 5-minute buffer)
        3. If needed, automatically refresh using the refresh_token
        4. Reload MCP configuration and reconnect after refresh
        """
        try:
            if not self.config or "lark-mcp" not in self.config.servers:
                logger.debug("lark-mcp server not found in MCP config, skipping token refresh")
                return
            
            logger.debug("Checking lark-mcp token status...")
            
            from .oauth.lark_oauth_manager import LarkOAuthManager
            
            # Create OAuth manager
            oauth_manager = LarkOAuthManager(self.config, self.config_path)
            
            # Check if refresh is needed
            if not oauth_manager.should_refresh_token("lark-mcp"):
                logger.debug("lark-mcp token is still valid, no refresh needed")
                return
            
            logger.info("lark-mcp token is about to expire, attempting refresh...")
            
            # Check if refresh_token is expired
            if oauth_manager.is_refresh_token_expired("lark-mcp"):
                logger.warning("lark-mcp refresh_token has expired, cannot auto-refresh. User needs to re-authorize.")
                return
            
            # Perform token refresh
            await oauth_manager.refresh_access_token("lark-mcp")
            logger.info("lark-mcp token refreshed successfully")
            
            # Invalidate connections and reload config with new token.
            # New connections will be established by lazy init in _configure_mcp_servers.
            logger.info("Reloading MCP config to apply new token...")
            success = self.reload_config()
            if success:
                logger.info("MCP config successfully reloaded with new token")
            else:
                logger.warning("Failed to reload MCP config with new token")
        
        except Exception as e:
            # Log error but do not interrupt the agent configuration process
            logger.warning(f"Failed to check/refresh lark-mcp token: {e}")
    
    def get_mcp_servers_for_agent(self) -> List[MCPServer]:
        """Get the list of available MCP servers"""
        if not self._initialized or not self.manager:
            return []
        return self.manager.active_servers
    
    async def get_real_server_status(self) -> Dict[str, str]:
        """Get real-time server status"""
        if not self._initialized or not self.manager:
            return {}
        
        status = {}
        for server in self.manager.all_servers:
            if server in self.manager.failed_servers:
                status[server.name] = "failed"
            else:
                try:
                    await asyncio.wait_for(server.list_tools(None, None), timeout=5.0)
                    status[server.name] = "connected"
                except asyncio.TimeoutError:
                    status[server.name] = "timeout"
                except Exception:
                    status[server.name] = "failed"
        
        return status
    
    async def list_tools_async(self) -> Dict[str, List[str]]:
        """List all tools"""
        if not self._initialized or not self.manager:
            return {}
        
        tools_by_server = {}
        for server in self.manager.active_servers:
            try:
                tools = await server.list_tools(None, None)
                tool_names = [tool.name for tool in tools]
                tools_by_server[server.name] = tool_names
                logger.debug(f"Server {server.name} has {len(tool_names)} tool(s)")
            except Exception as e:
                logger.error(f"Failed to list tools for server {server.name}: {e}")
                tools_by_server[server.name] = []
        
        return tools_by_server
    
    def reload_config(self) -> bool:
        """
        Invalidate current MCP connections and reload config from file (sync).
        
        This does NOT establish new connections — the lazy initialization in
        SiadaRunner._configure_mcp_servers() will handle reconnection in the
        correct event loop when the next agent run begins.
        
        This avoids the cross-event-loop issue: MCP stdio connections are tied
        to the event loop that created them. If connections were established in
        a temporary event loop (e.g., from a slash command handler), they would
        die when that loop closes. By deferring connection establishment to the
        agent's dedicated event loop, connections remain alive for their entire
        usage lifetime.
        
        Returns:
            bool: True if config was reloaded successfully
        """
        try:
            logger.info("Invalidating MCP state and reloading config...")
            
            # Mark as uninitialized so lazy init triggers on next agent run
            self._initialized = False
            # Drop reference to old manager (old connections will be GC'd)
            self.manager = None
            
            # Reload configuration from file
            if self.config_path:
                logger.info(f"Reloading configuration from: {self.config_path}")
                from siada.config.mcp_config_loader import MCPConfigLoader
                new_config = MCPConfigLoader.load_config(str(self.config_path))
                self.config = new_config
                logger.info("MCP config reloaded. New connections will be established on next use.")
                return True
            else:
                logger.warning("Configuration file path not set, cannot reload")
                return False
        
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown MCP service"""
        if not self._initialized:
            return
        
        if self.io:
            self.io.print_info("Shutting down MCP service...")
        else:
            logger.info("Shutting down MCP service...")
        
        try:
            # Clean up all servers
            if self.manager:
                await self.manager.cleanup_all()
            
            logger.info("MCP service shutdown completed")
        
        except Exception as e:
            logger.error(f"MCP service shutdown failed: {e}")
        
        finally:
            self._initialized = False
            self.manager = None
    
    def _cleanup_on_exit(self) -> None:
        """Cleanup callback on program exit (atexit hook)"""
        if not self._initialized:
            return

        async def _shutdown_with_timeout() -> None:
            try:
                await asyncio.wait_for(self.shutdown(), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("MCP cleanup timed out after 1s, forcing exit")
                self._initialized = False
                self.manager = None

        try:
            logger.info("Program exit detected, cleaning up MCP service...")
            asyncio.run(_shutdown_with_timeout())
        except Exception as e:
            logger.error(f"Failed to clean up MCP on program exit: {e}")


def get_global_tool_name_resolver() -> MCPToolNameResolver:
    """Get the global tool name resolver"""
    global _mcp_manager_service
    return _mcp_manager_service.tool_name_resolver


_mcp_manager_service = MCPManagerService()
