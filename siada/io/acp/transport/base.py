"""
ACP Transport Base Class

Defines the abstract interface for ACP message transport.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable
import asyncio
from siada.io.acp.message_builder import ACPMessage


class ACPTransport(ABC):
    """
    Abstract base class for ACP message transport
    
    Defines the interface for sending and receiving ACP messages
    through different transport mechanisms (stdio, HTTP, WebSocket, etc.)
    
    Usage:
        # Implement a concrete transport
        class MyTransport(ACPTransport):
            async def connect(self):
                # Implementation
                pass
            
            async def send(self, message):
                # Implementation
                pass
            
            # ... implement other methods
        
        # Use the transport
        transport = MyTransport()
        await transport.connect()
        
        msg = ACPMessage(method="test", params={})
        await transport.send(msg)
    """
    
    def __init__(self):
        """Initialize transport"""
        self.is_connected = False
        self.on_message_callback: Optional[Callable[[ACPMessage], Awaitable[None]]] = None
        self._receive_task: Optional[asyncio.Task] = None
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection
        
        This method should:
        1. Set up the transport mechanism
        2. Start listening for messages
        3. Set is_connected to True
        
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection
        
        This method should:
        1. Stop listening for messages
        2. Clean up resources
        3. Set is_connected to False
        """
        pass
    
    @abstractmethod
    async def send(self, message: ACPMessage) -> None:
        """
        Send an ACP message
        
        Args:
            message: ACPMessage to send
        
        Raises:
            RuntimeError: If not connected
            IOError: If send fails
        """
        pass
    
    @abstractmethod
    async def receive(self) -> Optional[ACPMessage]:
        """
        Receive an ACP message (blocking)
        
        Returns:
            ACPMessage if available, None if connection closed
        
        Raises:
            RuntimeError: If not connected
        """
        pass
    
    def on_message(self, callback: Callable[[ACPMessage], Awaitable[None]]) -> None:
        """
        Register callback for received messages
        
        The callback will be invoked asynchronously for each received message.
        
        Args:
            callback: Async function that takes ACPMessage as parameter
        
        Example:
            async def handle_message(msg: ACPMessage):
                print(f"Received: {msg.method}")
            
            transport.on_message(handle_message)
        """
        self.on_message_callback = callback
    
    async def start_receive_loop(self) -> None:
        """
        Start the message receive loop
        
        This method continuously receives messages and invokes the callback.
        Should be called after connect() if using callbacks.
        """
        if not self.is_connected:
            raise RuntimeError("Transport not connected")
        
        if self._receive_task is not None:
            raise RuntimeError("Receive loop already running")
        
        self._receive_task = asyncio.create_task(self._receive_loop())
    
    async def stop_receive_loop(self) -> None:
        """Stop the message receive loop"""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
    
    async def _receive_loop(self) -> None:
        """Internal receive loop implementation"""
        try:
            while self.is_connected:
                message = await self.receive()
                if message is None:
                    break
                
                if self.on_message_callback:
                    try:
                        await self.on_message_callback(message)
                    except Exception as e:
                        # Log error but continue receiving
                        import sys
                        print(f"Error in message callback: {e}", file=sys.stderr)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            import sys
            print(f"Error in receive loop: {e}", file=sys.stderr)
    
    def __repr__(self) -> str:
        """String representation"""
        return f"<{self.__class__.__name__} connected={self.is_connected}>"


class TransportError(Exception):
    """Base exception for transport errors"""
    pass


class ConnectionError(TransportError):
    """Connection related errors"""
    pass


class SendError(TransportError):
    """Send operation errors"""
    pass


class ReceiveError(TransportError):
    """Receive operation errors"""
    pass
