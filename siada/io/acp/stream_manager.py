"""
ACP Stream Manager

Manages streaming output of ACP messages with flow control.
"""

import asyncio
from typing import Optional, List
from siada.io.acp.message_builder import ACPMessageBuilder, SessionUpdateReason
from siada.io.acp.transport.base import ACPTransport


class ACPStreamManager:
    """
    Manages streaming output for ACP sessions
    
    Provides high-level methods for streaming thinking, answers, and tool outputs
    with proper flow control and state management.
    
    Usage:
        transport = StdioTransport()
        await transport.connect()
        
        manager = ACPStreamManager(transport)
        
        # Start streaming
        await manager.start_stream()
        
        # Stream thinking
        await manager.stream_thinking("Analyzing problem...")
        
        # Stream answer line by line
        answer = "Line 1\\nLine 2\\nLine 3"
        await manager.stream_answer_line_by_line(answer)
        
        # End stream
        await manager.end_stream()
    """
    
    def __init__(self, transport: ACPTransport, builder: Optional[ACPMessageBuilder] = None):
        """
        Initialize stream manager
        
        Args:
            transport: ACPTransport instance for sending messages
            builder: Optional ACPMessageBuilder (creates one if not provided)
        """
        self.transport = transport
        self.builder = builder or ACPMessageBuilder()
        self.is_streaming = False
        self._stream_lock = asyncio.Lock()
    
    async def start_stream(self) -> None:
        """
        Start a streaming session
        
        Call this before streaming any content.
        """
        async with self._stream_lock:
            if self.is_streaming:
                raise RuntimeError("Stream already started")
            self.is_streaming = True
    
    async def end_stream(self, final_answer: Optional[str] = None) -> None:
        """
        End the streaming session
        
        Args:
            final_answer: Optional final answer text
        """
        async with self._stream_lock:
            if not self.is_streaming:
                return
            
            # Send completion message
            msg = self.builder.build_completed(final_answer)
            await self.transport.send(msg)
            
            self.is_streaming = False
    
    async def stream_thinking(self, thinking: str) -> None:
        """
        Stream a thinking update
        
        Args:
            thinking: Thinking text to stream
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        msg = self.builder.build_thinking_update(thinking)
        await self.transport.send(msg)
    
    async def stream_answer_chunk(self, chunk: str, is_final: bool = False) -> None:
        """
        Stream an answer chunk
        
        Args:
            chunk: Answer chunk to stream
            is_final: Whether this is the final chunk of the answer stream
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        # Use build_message_chunk to support stream_end parameter
        msg = self.builder.build_message_chunk(
            chunk,
            chunk_type="answer",
            is_streaming=True,
            stream_end=is_final
        )
        await self.transport.send(msg)
    
    async def stream_tool_output(self, output: str) -> None:
        """
        Stream tool output
        
        Args:
            output: Tool output text
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        msg = self.builder.build_tool_use_chunk(output)
        await self.transport.send(msg)
    
    async def stream_answer_line_by_line(
        self,
        full_answer: str,
        delay_ms: int = 0,
        chunk_size: int = 1
    ) -> None:
        """
        Stream answer line by line
        
        Splits the answer into lines and streams each line as a separate chunk.
        Useful for real-time output simulation.
        
        Args:
            full_answer: Complete answer text
            delay_ms: Delay between lines in milliseconds (default: 0)
            chunk_size: Number of lines per chunk (default: 1)
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        lines = full_answer.split('\n')
        
        # Stream in chunks
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk = '\n'.join(chunk_lines)
            
            # Add newline if not the last chunk
            if i + chunk_size < len(lines):
                chunk += '\n'
            
            await self.stream_answer_chunk(chunk)
            
            # Add delay if specified
            if delay_ms > 0 and i + chunk_size < len(lines):
                await asyncio.sleep(delay_ms / 1000.0)
    
    async def stream_answer_char_by_char(
        self,
        full_answer: str,
        delay_ms: int = 10,
        chunk_size: int = 1
    ) -> None:
        """
        Stream answer character by character
        
        Provides typewriter effect for answers.
        
        Args:
            full_answer: Complete answer text
            delay_ms: Delay between chunks in milliseconds (default: 10)
            chunk_size: Number of characters per chunk (default: 1)
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        for i in range(0, len(full_answer), chunk_size):
            chunk = full_answer[i:i + chunk_size]
            await self.stream_answer_chunk(chunk)
            
            # Add delay if specified
            if delay_ms > 0 and i + chunk_size < len(full_answer):
                await asyncio.sleep(delay_ms / 1000.0)
    
    async def stream_tool_call(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: Optional[dict] = None,
        result: Optional[any] = None
    ) -> None:
        """
        Stream a tool call update
        
        Args:
            tool_name: Name of the tool
            tool_call_id: Unique ID for this tool call
            arguments: Tool arguments (optional)
            result: Tool result (optional)
        """
        if not self.is_streaming:
            raise RuntimeError("Stream not started. Call start_stream() first.")
        
        msg = self.builder.build_tool_call_update(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=arguments,
            result=result
        )
        await self.transport.send(msg)
    
    async def stream_error(self, error_message: str) -> None:
        """
        Stream an error/failure notification
        
        Args:
            error_message: Error message
        """
        if not self.is_streaming:
            # Allow error even if stream not started
            pass
        
        msg = self.builder.build_failed(error_message)
        await self.transport.send(msg)
        
        # End stream
        self.is_streaming = False
    
    async def stream_cancelled(self, reason: Optional[str] = None) -> None:
        """
        Stream a cancellation notification
        
        Args:
            reason: Optional cancellation reason
        """
        if not self.is_streaming:
            return
        
        msg = self.builder.build_cancelled(reason)
        await self.transport.send(msg)
        
        # End stream
        self.is_streaming = False
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.start_stream()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is not None:
            # Error occurred, send failure message
            await self.stream_error(str(exc_val))
        else:
            # Normal completion
            await self.end_stream()
        return False


class StreamManagerSync:
    """
    Synchronous wrapper for ACPStreamManager
    
    Provides a synchronous interface using asyncio.run() internally.
    
    Usage:
        transport = StdioTransportSync()
        transport.connect()
        
        manager = StreamManagerSync(transport)
        manager.start_stream()
        manager.stream_thinking("Analyzing...")
        manager.stream_answer_chunk("Answer")
        manager.end_stream()
    """
    
    def __init__(self, transport, builder: Optional[ACPMessageBuilder] = None):
        """Initialize with transport (sync or async)"""
        # If transport is sync wrapper, get the underlying async transport
        if hasattr(transport, '_transport'):
            transport = transport._transport
        
        self._manager = ACPStreamManager(transport, builder)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def start_stream(self) -> None:
        """Start stream synchronously"""
        asyncio.run(self._manager.start_stream())
    
    def end_stream(self, final_answer: Optional[str] = None) -> None:
        """End stream synchronously"""
        asyncio.run(self._manager.end_stream(final_answer))
    
    def stream_thinking(self, thinking: str) -> None:
        """Stream thinking synchronously"""
        asyncio.run(self._manager.stream_thinking(thinking))
    
    def stream_answer_chunk(self, chunk: str) -> None:
        """Stream answer chunk synchronously"""
        asyncio.run(self._manager.stream_answer_chunk(chunk))
    
    def stream_tool_output(self, output: str) -> None:
        """Stream tool output synchronously"""
        asyncio.run(self._manager.stream_tool_output(output))
    
    def stream_answer_line_by_line(
        self,
        full_answer: str,
        delay_ms: int = 0,
        chunk_size: int = 1
    ) -> None:
        """Stream answer line by line synchronously"""
        asyncio.run(self._manager.stream_answer_line_by_line(
            full_answer, delay_ms, chunk_size
        ))
    
    def stream_tool_call(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: Optional[dict] = None,
        result: Optional[any] = None
    ) -> None:
        """Stream tool call synchronously"""
        asyncio.run(self._manager.stream_tool_call(
            tool_name, tool_call_id, arguments, result
        ))
    
    def stream_error(self, error_message: str) -> None:
        """Stream error synchronously"""
        asyncio.run(self._manager.stream_error(error_message))
    
    def stream_cancelled(self, reason: Optional[str] = None) -> None:
        """Stream cancellation synchronously"""
        asyncio.run(self._manager.stream_cancelled(reason))
    
    @property
    def is_streaming(self) -> bool:
        """Check if streaming"""
        return self._manager.is_streaming
    
    def __enter__(self):
        """Context manager entry"""
        self.start_stream()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is not None:
            self.stream_error(str(exc_val))
        else:
            self.end_stream()
        return False
