"""
MCP Service using SDK

This module provides a simplified MCP service implementation using the agents library MCP SDK.
MCPService integrates all MCP functionality in a single class to avoid redundant architecture.
"""

import asyncio
import logging
import threading
import re
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass
from siada.config.mcp_config import MCPConfig, MCPTransportType
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
    
    # List of Siada native tool names (tool names that need protection)
    SIADA_NATIVE_TOOLS = {
        "edit_file", 
    }
    
    def __init__(self):
        self.conflicts: List[ToolConflictInfo] = []
        self.renamed_tools: Dict[str, str] = {}  # original_name -> new_name
    
    def resolve_tool_conflicts(self, mcp_servers: List[Any]) -> List[ToolConflictInfo]:
        """
        Detect and resolve name conflicts between MCP tools and Siada tools
        
        Args:
            mcp_servers: List of MCP servers
            
        Returns:
            List[ToolConflictInfo]: List of conflict information
        """
        self.conflicts.clear()
        self.renamed_tools.clear()
        
        for server in mcp_servers:
            server_conflicts = self._resolve_server_tool_conflicts(server)
            self.conflicts.extend(server_conflicts)
        
        if self.conflicts:
            for conflict in self.conflicts:
                logging.debug(f"  {conflict.original_name} -> {conflict.new_name} ({conflict.server_name})")
        
        return self.conflicts
    
    def _resolve_server_tool_conflicts(self, server: Any) -> List[ToolConflictInfo]:
        """Resolve tool name conflicts for a single server"""
        conflicts = []
        
        # Get server tool list (can only be obtained after connection)
        if not hasattr(server, '_tools_list') or server._tools_list is None:
            # If tool list is not yet loaded, skip temporarily
            logging.debug(f"Server {server.name} tools list not yet loaded, skipping conflict resolution")
            return conflicts
        
        for tool in server._tools_list:
            original_name = tool.name
            
            # Check if it conflicts with Siada tools
            if original_name in self.SIADA_NATIVE_TOOLS:
                new_name = self._generate_prefixed_name(server.name, original_name)
                
                # Modify tool name
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
        """Generate tool name with server prefix"""
        # Clean server name, remove special characters
        clean_server_name = self._clean_server_name(server_name)
        return f"{clean_server_name}_{tool_name}"
    
    def _clean_server_name(self, server_name: str) -> str:
        """Clean server name to make it suitable as tool name prefix"""
        # Remove special characters, keep only alphanumeric and underscore
        clean_name = re.sub(r'[^\w]', '_', server_name)
        # Remove redundant underscores
        clean_name = re.sub(r'_+', '_', clean_name)
        # Remove leading and trailing underscores
        clean_name = clean_name.strip('_')
        # Convert to lowercase
        clean_name = clean_name.lower()
        
        # If cleaned name is empty, use default name
        if not clean_name:
            clean_name = "mcp"
        
        return clean_name

class MCPService:
    """MCP Service - Unified service class integrating all MCP functionality"""
    
    def __init__(self):
        self.config: Optional[MCPConfig] = None
        self.mcp_servers: List[Any] = []
        self._initialized = False
        self.io = None  # IO object for output information
        self.tool_name_resolver = MCPToolNameResolver()  # Tool name conflict resolver
    
    def set_io(self, io):
        """Set IO object for output information"""
        self.io = io
    
    def set_mcp_config(self, mcp_config: MCPConfig):
        """Store MCP configuration (called during Controller initialization)"""
        self.config = mcp_config
    
    def has_config(self) -> bool:
        """Check if MCP configuration is available"""
        return self.config is not None and self.config.enabled
    
    def get_mcp_config(self) -> Optional[MCPConfig]:
        """Get stored MCP configuration"""
        return self.config
    
    @property
    def is_initialized(self) -> bool:
        """Check if MCP service is initialized"""
        return self._initialized
        
    async def initialize(self) -> List[Any]:
        """Initialize MCP service"""
        if not self.has_config():
            logger.info("MCP service is disabled or no config available")
            return
            
        if self._initialized:
            logger.debug("MCP service already initialized")
            return
            
        try:
            logger.info("Initializing MCP service using SDK...")
            
            # Set mcp.client.streamable_http logger level to ERROR to reduce verbose output
            mcp_http_logger = logging.getLogger('mcp.client')
            mcp_http_logger.setLevel(logging.ERROR)
            
            # # Set openai.agents logger level to CRITICAL to filter out cleanup error messages
            # openai_agents_logger = logging.getLogger('openai.agents')
            # openai_agents_logger.setLevel(logging.CRITICAL)
            
            # Create all MCP servers
            self.mcp_servers = await self._create_mcp_servers()
            
            # Connect all servers
            await self._connect_all_servers()
            
            self._initialized = True

            return self.mcp_servers

        except Exception as e:
            logger.error(f"Failed to initialize MCP service: {e}")
            self._initialized = False
            raise
            
    async def _create_mcp_servers(self) -> List[Any]:
        """Create MCP server objects based on configuration"""
        servers = []
        
        for server_name, server_config in self.config.servers.items():
            try:
                server = self._create_single_server(server_name, server_config)
                if server:
                    servers.append(server)
                    logger.info(f"Created MCP server: {server_name}")
            except Exception as e:
                logger.error(f"Failed to create server '{server_name}': {e}")
                
        return servers
    
    def _create_single_server(self, server_name: str, server_config):
        """Create a single MCP server"""
        # Check if server is enabled
        if not server_config.enabled:
            logger.info(f"Skipping disabled MCP server: {server_name}")
            return None
            
        transport_type = server_config.get_transport_type()
        
        try:
            if transport_type == MCPTransportType.STDIO:
                from agents.mcp import MCPServerStdio
                return MCPServerStdio(
                    params={
                        "command": server_config.command,
                        "args": server_config.args or [],
                        "env": server_config.env or {},
                        "cwd": server_config.cwd
                    },
                    cache_tools_list=True,  # Enable caching to improve performance
                    name=server_name,
                    client_session_timeout_seconds=server_config.timeout / 1000.0
                )
                
            elif transport_type == MCPTransportType.HTTP:
                from agents.mcp import MCPServerStreamableHttp
                # HTTP transport uses url field (same as SSE, distinguished by type)
                http_url = server_config.url or server_config.http_url
                return MCPServerStreamableHttp(
                    name=server_name,
                    params={
                        "url": http_url,
                        "headers": server_config.headers or {},
                        "timeout": server_config.timeout / 1000.0,
                        "terminate_on_close": True
                    },
                    cache_tools_list=True
                )
                
            elif transport_type == MCPTransportType.SSE:
                from agents.mcp import MCPServerSse
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
            logger.error(f"Failed to import MCP server class for {transport_type}: {e}")
            logger.error("Please ensure agents[mcp] is installed: pip install 'openai-agents[mcp]'")
            return None
        except Exception as e:
            logger.error(f"Failed to create {transport_type} server '{server_name}': {e}")
            return None
    
    async def _connect_all_servers(self):
        """Connect to all servers"""
        if not self.mcp_servers:
            logger.info("No MCP servers to connect")
            return
            
        connection_tasks = []
        for server in self.mcp_servers:
            task = asyncio.create_task(
                self._connect_single_server(server),
                name=f"connect-{server.name}"
            )
            connection_tasks.append(task)
        
        # Connect all servers concurrently
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        # Count connection results
        connected_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to connect server {self.mcp_servers[i].name}: {result}")
            else:
                connected_count += 1
        
        logger.info(f"Connected {connected_count}/{len(self.mcp_servers)} MCP servers")
        
        # Resolve tool name conflicts after successful connections
        if connected_count > 0:
            await self._resolve_tool_name_conflicts()
    
    async def _resolve_tool_name_conflicts(self):
        """Resolve MCP tool name conflicts"""
        try:
            # First preload all server tool lists to cache
            await self._preload_tools_cache()
            
            # Use internal tool name resolver to resolve conflicts
            conflicts = self.tool_name_resolver.resolve_tool_conflicts(self.mcp_servers)
            
            if conflicts:
                logger.info(f"Resolved {len(conflicts)} MCP tool name conflicts:")
                for conflict in conflicts:
                    logger.info(f"  • {conflict.original_name} → {conflict.new_name} (from {conflict.server_name})")
            else:
                logger.debug("No MCP tool name conflicts detected")
                
        except Exception as e:
            logger.error(f"Failed to resolve MCP tool name conflicts: {e}")
            # Tool name conflict resolution failure should not block MCP service usage
    
    async def _preload_tools_cache(self):
        """Preload all server tool lists to cache"""
        logger.debug("Preloading MCP tools cache for conflict resolution...")
        
        preload_tasks = []
        for server in self.mcp_servers:
            task = asyncio.create_task(
                self._preload_server_tools(server),
                name=f"preload-tools-{server.name}"
            )
            preload_tasks.append(task)
        
        # Concurrently preload all server tools
        await asyncio.gather(*preload_tasks, return_exceptions=True)
        
        logger.debug("MCP tools cache preloading completed")
    
    async def _preload_server_tools(self, server):
        """Preload tool list for a single server"""
        try:
            # Trigger tool list loading, results will be cached in server._tools_list
            await server.list_tools(None, None)
            logger.debug(f"Preloaded tools for server: {server.name}")
        except Exception as e:
            logger.error(f"Failed to preload tools for server '{server.name}': {e}")
    
    async def _connect_single_server(self, server):
        """Connect to a single server"""
        try:
            await server.connect()
            logger.debug(f"Successfully connected to MCP server: {server.name}")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{server.name}': {e}")
            raise
    
    def get_mcp_servers_for_agent(self) -> List[Any]:
        """Get MCP server list that can be directly used by Agent"""
        if not self._initialized:
            return []
        return self.mcp_servers
    
    async def get_real_server_status(self) -> Dict[str, str]:
        """Get real-time server status"""
        if not self._initialized:
            return {}
            
        status_results = {}
        for server in self.mcp_servers:
            try:
                # Test connection status through list_tools
                await asyncio.wait_for(server.list_tools(None, None), timeout=5.0)
                status_results[server.name] = "connected"
            except asyncio.TimeoutError:
                status_results[server.name] = "timeout"
            except Exception as e:
                logger.debug(f"Server {server.name} status check failed: {e}")
                status_results[server.name] = "failed"
                
        return status_results
    
    async def list_tools_async(self) -> Dict[str, List[str]]:
        """Asynchronously list tools from all servers"""
        if not self._initialized:
            return {}
            
        tools_by_server = {}
        for server in self.mcp_servers:
            try:
                # Use SDK to get tool list
                tools = await server.list_tools(None, None)
                tool_names = [tool.name for tool in tools]
                tools_by_server[server.name] = tool_names
                logger.debug(f"Server {server.name} has {len(tool_names)} tools")
            except Exception as e:
                logger.error(f"Failed to list tools for server {server.name}: {e}")
                tools_by_server[server.name] = []
                
        return tools_by_server
    
    async def shutdown(self) -> None:
        """Shutdown MCP service"""
        if not self._initialized or not self.mcp_servers:
            self._reset_state()
            return
            
        if self.io:
            self.io.print_info("Shutting down MCP service...")
        else:
            logging.info("Shutting down MCP service...")
        
        try:
            # Concurrently clean up all servers with unified timeout
            shutdown_tasks = [
                self._cleanup_server(server) for server in self.mcp_servers
            ]
            await asyncio.wait_for(
                asyncio.gather(*shutdown_tasks, return_exceptions=True),
                timeout=1.5  # Unified 1.5 second timeout
            )
            logger.info("MCP service shutdown completed")
            
        except asyncio.TimeoutError:
            logger.error("MCP shutdown timeout, forcing cleanup")
        except Exception as e:
            logger.error(f"Error during MCP service shutdown: {e}")
        
        self._reset_state()
    
    async def _cleanup_server(self, server):
        """Clean up a single server"""
        try:
            await asyncio.wait_for(server.cleanup(), timeout=1.0)
            logger.info(f"Successfully cleaned up server: {server.name}")
        except asyncio.TimeoutError:
            logger.error(f"Server cleanup timeout: {server.name}")
        except Exception as e:
            logger.error(f"Server cleanup error {server.name}: {e}")

    def _reset_state(self):
        """Reset service state"""
        self.mcp_servers = []
        self._initialized = False
    
    def cleanup_sync(self):
        """Synchronous cleanup method - force cleanup to avoid async conflicts"""
        if not self.is_initialized:
            return
            
        def run_cleanup():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(self.shutdown(), timeout=2.0)
                    )
                finally:
                    loop.close()
            except Exception:
                logger.error("Error during MCP synchronous cleanup")
                # If async cleanup fails, try force cleanup
        
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
        cleanup_thread.start()
        cleanup_thread.join(timeout=3.0)  # Give enough time to complete cleanup


def get_global_tool_name_resolver() -> MCPToolNameResolver:
    """Get global tool name resolver instance"""
    return mcp_service.tool_name_resolver


def resolve_mcp_tool_conflicts(mcp_servers: List[Any]) -> List[ToolConflictInfo]:
    """
    Convenience function to resolve MCP tool name conflicts
    
    Args:
        mcp_servers: List of MCP servers
        
    Returns:
        List[ToolConflictInfo]: List of conflict information
    """
    return mcp_service.tool_name_resolver.resolve_tool_conflicts(mcp_servers)


# Create global instance at the end of the file
mcp_service = MCPService()
