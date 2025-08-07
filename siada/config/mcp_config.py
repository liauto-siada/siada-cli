from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class MCPTransportType(Enum):
    """MCP transport protocol types (for runtime use only)"""
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


@dataclass(frozen=True)
class MCPServerConfig:
    """
    MCP server configuration - transport type specified by type field or auto-detected from config
    """
    
    # Explicit transport type (highest priority)
    type: Optional[str] = None  # "stdio", "sse", or "http"
    
    # Stdio transport configuration
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None
    
    # HTTP/SSE transport configuration
    url: Optional[str] = None
    http_url: Optional[str] = None  # Specific HTTP endpoint (higher priority than url)
    headers: Optional[Dict[str, str]] = None
    
    # General configuration
    enabled: bool = True
    timeout: int = 10000
    trust: bool = False
    auto_reconnect: bool = True
    
    def get_transport_type(self) -> MCPTransportType:
        """
        Determine transport type based on configuration
        
        Priority order:
        1. Explicit type field (highest priority) 
        2. Stdio transport (command) -> StdioClientTransport
        3. URL-based transport (url) -> auto-detect SSE (default for url field)
        
        Note: HTTP and SSE both use the url field, distinguished by explicit type
        """
        # Highest priority: Explicit type field
        if self.type:
            type_lower = self.type.lower()
            if type_lower == "stdio":
                return MCPTransportType.STDIO
            elif type_lower == "sse":
                return MCPTransportType.SSE
            elif type_lower == "http":
                return MCPTransportType.HTTP
            else:
                # Invalid type specified, fall back to auto-detection
                pass
        
        # Second priority: Stdio transport
        if self.command:
            return MCPTransportType.STDIO
            
        # Third priority: URL-based transport (default to SSE for backward compatibility)
        if self.url or self.http_url:
            return MCPTransportType.SSE
            
        # Default to Stdio (backward compatibility)
        return MCPTransportType.STDIO
    


@dataclass(frozen=True)
class MCPConfig:
    """MCP global configuration"""
    enabled: bool = True
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    auto_discover: bool = True
    global_timeout: int = 30000
