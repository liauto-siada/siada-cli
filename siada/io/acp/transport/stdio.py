"""
Stdio Transport

Provides communication via standard input/output streams.
Used for process-to-process communication (e.g., with siada-cli-ui).
"""

import sys
import asyncio
import json
import traceback
import threading
from typing import Optional
from siada.io.acp.message_builder import ACPMessage
from .base import ACPTransport, ConnectionError, SendError, ReceiveError
from siada.foundation.logging import logger


class StdioTransport(ACPTransport):
    """
    Standard Input/Output Transport
    
    Communicates via stdin/stdout using newline-delimited JSON messages.
    
    Protocol:
    - Each message is a single JSON line
    - Messages are separated by newline (\\n)
    - stdout is used for sending messages
    - stdin is used for receiving messages
    
    Usage:
        transport = StdioTransport()
        await transport.connect()
        
        # Send a message
        msg = ACPMessage(method="session/update", params={...})
        await transport.send(msg)
        
        # Receive messages via callback
        async def handle_message(msg: ACPMessage):
            print(f"Received: {msg.method}")
        
        transport.on_message(handle_message)
        await transport.start_receive_loop()
    
    Notes:
    - stdout is line-buffered for immediate delivery
    - stdin is read asynchronously
    - Errors are logged to stderr
    """
    
    def __init__(
        self,
        stdin=None,
        stdout=None,
        buffer_size: int = 8192,
        ensure_ascii: bool = False
    ):
        """
        Initialize Stdio Transport
        
        Args:
            stdin: Input stream (default: sys.stdin)
            stdout: Output stream (default: sys.stdout)
            buffer_size: Buffer size for reading (default: 8192)
            ensure_ascii: Whether to escape non-ASCII characters in JSON
        """
        super().__init__()
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._buffer_size = buffer_size
        self._ensure_ascii = ensure_ascii
        
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._read_buffer = ""
        self._write_lock = threading.Lock()  # Lock for synchronized writes

    async def connect(self) -> None:
        """
        Connect stdio streams (sync-only mode)
        
        Marks the transport as connected without setting up async pipe readers/writers.
        
        All message sending uses send_sync() which writes directly to stdout.buffer,
        and stdin reading is done synchronously in io.py's get_input().
        Therefore async pipe registration (connect_read_pipe/connect_write_pipe) is
        unnecessary and can cause issues:
        - On Windows: ProactorEventLoop's IOCP fails with pipe handles
          (OSError: [WinError 6] The handle is invalid)
        - On all platforms: adds complexity with no benefit since async streams
          are never actually used by business code
        
        Raises:
            ConnectionError: If already connected
        """
        if self.is_connected:
            raise ConnectionError("Already connected")
        
        self.is_connected = True
        logger.debug("[StdioTransport] Connected in sync-only mode (async pipe registration skipped)")
    
    async def disconnect(self) -> None:
        """
        Disconnect stdio streams
        
        Closes writers and cleans up resources.
        """
        if not self.is_connected:
            return
        
        # Stop receive loop if running
        await self.stop_receive_loop()
        
        # Close writer
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                print(f"Error closing writer: {e}", file=sys.stderr)
        
        self._reader = None
        self._writer = None
        self.is_connected = False
    
    def send_sync(self, message: ACPMessage) -> None:
        """
        同步发送 ACP 消息到 stdout

        使用直接的同步写入，避免 asyncio 事件循环问题。
        这是线程安全的方法，可以从任何线程调用。

        Args:
            message: ACPMessage to send
        
        Raises:
            SendError: If send fails
        """
        try:
            # Convert message to JSON
            json_str = message.to_json(ensure_ascii=self._ensure_ascii)
            
            # Add unique delimiter and newline for reliable message separation
            # Using \x1E (Record Separator) as delimiter to avoid conflicts with content
            data = ('\x1E' + json_str + '\n').encode('utf-8')

            # Use lock to ensure thread-safe writes
            with self._write_lock:
                # Write directly to stdout buffer
                self._stdout.buffer.write(data)
                self._stdout.buffer.flush()

            logger.debug(f"[STDIO SEND SYNC] Message {data} sent successfully")

        except Exception as e:
            raise SendError(f"Failed to send message: {e}") from e
    
    async def send(self, message: ACPMessage) -> None:
        """
        Send an ACP message to stdout

        使用同步写入方式，避免 asyncio 事件循环跨线程问题。

        Args:
            message: ACPMessage to send

        Raises:
            SendError: If send fails
        """
        # Use synchronous method directly to avoid asyncio event loop issues
        self.send_sync(message)

    async def receive(self) -> Optional[ACPMessage]:
        """
        Receive an ACP message from stdin (blocking)
        
        Reads lines from stdin and parses them as JSON messages.
        
        Returns:
            ACPMessage if available, None if EOF reached
        
        Raises:
            RuntimeError: If not connected
            ReceiveError: If receive or parse fails
        """
        if not self.is_connected or not self._reader:
            raise RuntimeError("Transport not connected")
        
        try:
            # Read a line from stdin
            line_bytes = await self._reader.readline()
            
            if not line_bytes:
                # EOF reached
                return None
            
            # Decode and strip newline
            line = line_bytes.decode('utf-8').strip()
            
            if not line:
                # Empty line, skip
                return await self.receive()
            
            # Parse JSON
            try:
                data = json.loads(line)
                return ACPMessage.from_dict(data)
            except json.JSONDecodeError as e:
                # Log parse error but don't crash
                print(f"Failed to parse JSON: {line[:100]}...", file=sys.stderr)
                print(f"Error: {e}", file=sys.stderr)
                # Continue to next line
                return await self.receive()
        
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise ReceiveError(f"Failed to receive message: {e}") from e
    
    def __repr__(self) -> str:
        """String representation"""
        return f"<StdioTransport connected={self.is_connected}>"


class StdioTransportSync:
    """
    Synchronous wrapper for StdioTransport
    
    Provides a synchronous interface for environments where async is not available.
    Uses asyncio.run() internally for each operation.
    
    Usage:
        transport = StdioTransportSync()
        transport.connect()
        
        msg = ACPMessage(method="test", params={})
        transport.send(msg)
        
        transport.disconnect()
    
    Note: Less efficient than async version. Use async when possible.
    """
    
    def __init__(self, **kwargs):
        """Initialize with same arguments as StdioTransport"""
        self._transport = StdioTransport(**kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def connect(self) -> None:
        """Connect synchronously"""
        asyncio.run(self._transport.connect())
    
    def disconnect(self) -> None:
        """Disconnect synchronously"""
        asyncio.run(self._transport.disconnect())
    
    def send(self, message: ACPMessage) -> None:
        """Send message synchronously"""
        # 🔍 Add log tracing for synchronous send
        msg_id = message.id if hasattr(message, 'id') else 'unknown'
        logger.debug(f"🔍 [STDIO SYNC SEND] Sending message {msg_id} via sync wrapper")
        asyncio.run(self._transport.send(message))
    
    def receive(self) -> Optional[ACPMessage]:
        """Receive message synchronously"""
        return asyncio.run(self._transport.receive())
    
    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._transport.is_connected


# Utility functions for quick testing
async def send_message_stdio(message: ACPMessage) -> None:
    """
    Quick helper to send a single message to stdout
    
    Args:
        message: ACPMessage to send
    """
    # 🔍 Add log tracing for tool function send
    msg_id = message.id if hasattr(message, 'id') else 'unknown'
    logger.debug(f"🔍 [STDIO UTIL SEND] Sending message {msg_id} via utility function")
    
    transport = StdioTransport()
    await transport.connect()
    await transport.send(message)
    await transport.disconnect()


async def receive_message_stdio() -> Optional[ACPMessage]:
    """
    Quick helper to receive a single message from stdin
    
    Returns:
        ACPMessage or None
    """
    transport = StdioTransport()
    await transport.connect()
    message = await transport.receive()
    await transport.disconnect()
    return message
