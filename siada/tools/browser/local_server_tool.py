"""
Local server tool for serving HTML files with /card suffix.

This module provides functionality to start and stop local HTTP servers for HTML files.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any

from agents import function_tool, RunContextWrapper
from ...foundation.code_agent_context import CodeAgentContext


def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port.
    
    Args:
        start_port: Starting port number to check
        max_attempts: Maximum number of ports to try
        
    Returns:
        int: Available port number
        
    Raises:
        RuntimeError: If no available port is found
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    
    raise RuntimeError(f"No available port found in range {start_port}-{start_port + max_attempts}")


@function_tool(
    name_override="start_local_html_server",
    description_override="""
Start a local HTML server.

Starts a local HTTP server in the given directory; the server URL is
automatically suffixed with /card for identification.

Args:
    html_path (str): Directory containing the HTML files

Returns:
    str: The local server URL in the form http://localhost:<port>/card

Features:
- Automatically finds an available port
- Runs the server in the background
- URL carries a /card suffix for easy identification

Example:
    start_local_html_server("/path/to/html/files")
    # Returns: "http://localhost:8000/card"
"""
)
def start_local_html_server(
    context: RunContextWrapper[CodeAgentContext],
    html_path: str
) -> str:
    """Start a local HTML server.
    
    Args:
        context: The runtime context.
        html_path: The directory path containing the HTML files.
        
    Returns:
        str: The server URL with a /card suffix.
        
    Raises:
        ValueError: If the path is invalid or contains no HTML files.
        RuntimeError: If the server fails to start.
    """
    try:
        # Validate path
        path_obj = Path(html_path).resolve()
        if not path_obj.exists():
            raise ValueError(f"Path does not exist: {html_path}")
        
        if not path_obj.is_dir():
            raise ValueError(f"Path is not a directory: {html_path}")
        
        # Check for HTML files
        html_files = list(path_obj.glob("*.html"))
        if not html_files:
            raise ValueError(f"No HTML files found in directory: {html_path}")
        
        # Find available port
        port = find_available_port()
        
        # Start HTTP server
        cmd = [
            sys.executable, "-m", "http.server", str(port),
            "--directory", str(path_obj)
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(path_obj)
        )
        
        # Wait a moment for server to start
        time.sleep(1)
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(f"Server failed to start: {stderr.decode()}")
        
        # Store process info in context for later cleanup
        if not hasattr(context.context, '_local_servers'):
            context.context._local_servers = {}
        
        server_key = f"localhost:{port}"
        context.context._local_servers[server_key] = {
            'process': process,
            'port': port,
            'path': str(path_obj)
        }
        
        return f"http://localhost:{port}/?card=true"
        
    except Exception as e:
        raise RuntimeError(f"Failed to start local server: {str(e)}")


@function_tool(
    name_override="stop_local_html_server",
    description_override="""
Stop a local HTML server.

Stops the local HTTP server on the given port.

Args:
    port (int): Port of the server to stop

Returns:
    str: Result message

Features:
- Gracefully shuts down the server process
- Cleans up related resources

Example:
    stop_local_html_server(8000)
    # Returns: "Server on port 8000 stopped successfully"
"""
)
def stop_local_html_server(
    context: RunContextWrapper[CodeAgentContext],
    port: int
) -> str:
    """Stop a local HTML server.
    
    Args:
        context: The runtime context.
        port: The port number of the server to stop.
        
    Returns:
        str: The operation result message.
    """
    try:
        if not hasattr(context.context, '_local_servers'):
            return f"No servers found to stop"
        
        server_key = f"localhost:{port}"
        servers = context.context._local_servers
        
        if server_key not in servers:
            return f"No server found running on port {port}"
        
        server_info = servers[server_key]
        process = server_info['process']
        
        # Stop the server process
        if process.poll() is None:  # Still running
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        
        # Remove from context
        del servers[server_key]
        
        return f"Server on port {port} stopped successfully"
        
    except Exception as e:
        return f"Failed to stop server on port {port}: {str(e)}"
