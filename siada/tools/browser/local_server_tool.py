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
启动本地HTML服务器工具。

此工具用于在指定路径下启动一个本地HTTP服务器，服务器URL会自动添加 /card 后缀以便识别。

参数:
    html_path (str): 包含HTML文件的目录路径

返回:
    str: 本地服务器URL，格式为 http://localhost:端口/card

功能特点:
- 自动查找可用端口
- 后台运行服务器
- URL带有 /card 后缀便于识别

使用示例:
    start_local_html_server("/path/to/html/files")
    # 返回: "http://localhost:8000/card"
"""
)
def start_local_html_server(
    context: RunContextWrapper[CodeAgentContext],
    html_path: str
) -> str:
    """启动本地HTML服务器。
    
    Args:
        context: 运行上下文
        html_path: HTML文件所在目录路径
        
    Returns:
        str: 服务器URL，带有 /card 后缀
        
    Raises:
        ValueError: 如果路径无效或没有HTML文件
        RuntimeError: 如果服务器启动失败
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
        raise RuntimeError(f"启动本地服务器失败: {str(e)}")


@function_tool(
    name_override="stop_local_html_server",
    description_override="""
停止本地HTML服务器工具。

此工具用于停止指定端口的本地HTTP服务器。

参数:
    port (int): 要停止的服务器端口号

返回:
    str: 操作结果信息

功能特点:
- 优雅关闭服务器进程
- 清理相关资源

使用示例:
    stop_local_html_server(8000)
    # 返回: "Server on port 8000 stopped successfully"
"""
)
def stop_local_html_server(
    context: RunContextWrapper[CodeAgentContext],
    port: int
) -> str:
    """停止本地HTML服务器。
    
    Args:
        context: 运行上下文
        port: 要停止的服务器端口号
        
    Returns:
        str: 操作结果信息
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
