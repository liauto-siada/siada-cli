"""
Legacy ACP Adapter

Provides a compatibility layer between the existing Rich Console-based IO system
and the new ACP message system. Allows seamless switching between traditional
and ACP modes.

Usage:
    # Traditional mode (default)
    io = InputOutput(pretty=True)
    io.assistant_output("Hello")
    
    # ACP mode
    io = InputOutput(pretty=True, acp_mode=True)
    io.assistant_output("Hello")  # Sends ACP messages
"""

import asyncio
import sys
from typing import Optional, Any
from contextlib import contextmanager

from siada.io.acp.message_builder import ACPMessageBuilder
from siada.io.acp.stream_manager import ACPStreamManager
from siada.io.acp.transport.stdio import StdioTransport


class LegacyACPAdapter:
    """
    Adapter that wraps the existing IO system to support ACP messages
    
    This adapter provides two modes:
    1. **Traditional Mode**: Uses Rich Console (default)
    2. **ACP Mode**: Sends ACP messages via transport
    
    Key features:
    - Transparent mode switching
    - Backward compatible
    - No changes to existing code required
    - Support for both sync and async contexts
    
    Example:
        # Create adapter
        adapter = LegacyACPAdapter(acp_enabled=True)
        
        # Use like traditional IO
        adapter.thinking("Analyzing...")
        adapter.answer("The answer is...")
        adapter.tool_call("calculator", {"expr": "2+2"})
        adapter.complete()
    """
    
    def __init__(
        self,
        acp_enabled: bool = False,
        transport: Optional[Any] = None,
        fallback_to_console: bool = True
    ):
        """
        Initialize adapter
        
        Args:
            acp_enabled: Enable ACP mode
            transport: Custom transport (defaults to StdioTransport)
            fallback_to_console: Fallback to console if ACP fails
        """
        self.acp_enabled = acp_enabled
        self.fallback_to_console = fallback_to_console
        
        # ACP components
        self.transport = transport
        self.builder = ACPMessageBuilder()
        self.stream_manager: Optional[ACPStreamManager] = None
        
        # State
        self.is_streaming = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._tool_call_counter = 0
        
        # Initialize if ACP enabled
        if self.acp_enabled:
            self._initialize_acp()
    
    def _initialize_acp(self):
        """Initialize ACP components"""
        try:
            # Create transport if not provided
            if self.transport is None:
                self.transport = StdioTransport()
            
            # Get or create event loop
            try:
                self._event_loop = asyncio.get_event_loop()
            except RuntimeError:
                self._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._event_loop)
            
            # Connect transport (sync wrapper)
            if not self.transport.is_connected:
                self._run_async(self.transport.connect())
            
            # Create stream manager
            self.stream_manager = ACPStreamManager(self.transport, self.builder)
            
        except Exception as e:
            if self.fallback_to_console:
                self.acp_enabled = False
            else:
                raise
    
    def _ensure_healthy_event_loop(self):
        """
        确保 self._event_loop 是一个健康的、未关闭的事件循环。
        
        在 asyncio.run() 被调用后（例如 _send_if_acp_robust），
        之前缓存的事件循环可能已经被关闭或处于不可用状态。
        此方法检测这种情况并自动重建事件循环。
        
        Returns:
            asyncio.AbstractEventLoop: 一个健康的事件循环
        """
        if self._event_loop is not None and not self._event_loop.is_closed():
            return self._event_loop
        
        # Event loop is None or closed, needs to be recreated
        from siada.foundation.logging import logger
        logger.info("[_ensure_healthy_event_loop] Event loop is None or closed, rebuilding...")
        
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        
        logger.info("[_ensure_healthy_event_loop] New event loop created successfully")
        return self._event_loop

    def _run_async(self, coro):
        """Run async coroutine in sync context"""
        # Check if an event loop is already running
        try:
            loop = asyncio.get_running_loop()
            # Loop is running, schedule the coroutine as a task and wait for it
            import concurrent.futures
            import threading
            
            # Run in a separate thread to avoid blocking
            def run_in_thread():
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        except RuntimeError:
            # No event loop running, safe to use run_until_complete
            # Use _ensure_healthy_event_loop to ensure event loop is available
            # This resolves the issue of event loop being closed after asyncio.run()
            loop = self._ensure_healthy_event_loop()
            return loop.run_until_complete(coro)
    
    def _send_if_acp(self, message_func, *args, **kwargs):
        """Helper to send ACP message or fallback to console
        
        直接使用 transport.send_sync() 同步发送，
        完全不依赖 asyncio 事件循环，避免事件循环状态问题。
        """
        if not self.acp_enabled:
            return None
        
        try:
            msg = message_func(*args, **kwargs)
            # Use synchronous sending directly, no event loop needed
            # StdioTransport.send() internally calls send_sync(),
            # so no need to wrap in an async call via _run_async()
            self.transport.send_sync(msg)
            return msg
        except Exception as e:
            import sys
            print(f"Error sending ACP message: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            if self.fallback_to_console:
                return None
            else:
                raise
    
    def _send_if_acp_robust(self, message_func, *args, **kwargs):
        """
        Robust version of _send_if_acp for cleanup scenarios
        
        专门用于 finally 块等清理场景,确保消息送达。
        直接使用 transport.send_sync() 同步发送,完全不依赖 asyncio 事件循环。
        
        与 _send_if_acp 的区别:
        1. 更详细的日志记录,便于排查清理场景的问题
        2. 显式 flush stdout,确保消息被发送到 OS
        3. 更完善的异常处理和 fallback 机制
        
        适用场景:
        - finally 块中发送 stop animation 消息
        - 进程即将退出时的清理消息
        - 任何需要确保消息送达的关键场景
        
        Args:
            message_func: 消息构造函数 (通常是 lambda)
            *args, **kwargs: 传递给 message_func 的参数
        
        Returns:
            ACPMessage 对象,表示消息已发送; None 表示发送失败或 ACP 未启用
        
        Example:
            # 在 finally 块中使用
            adapter._send_if_acp_robust(
                lambda: builder.build_session_update(
                    reason="input_ready",
                    metadata={"animation_control": "stop"}
                )
            )
        """
        from siada.foundation.logging import logger
        
        if not self.acp_enabled:
            logger.debug("[_send_if_acp_robust] ACP not enabled, skipping")
            return None
        
        try:
            # Build message
            msg = message_func(*args, **kwargs)
            logger.info(f"[_send_if_acp_robust] Preparing to send message: {msg.method if hasattr(msg, 'method') else 'unknown'}")
            
            if not self.transport:
                logger.error("[_send_if_acp_robust] Transport not available")
                return None
            if not self.transport.is_connected:
                logger.warning("[_send_if_acp_robust] Transport not connected, attempting anyway")
            
            self.transport.send_sync(msg)
            sys.stdout.flush()

            return msg
            
        except Exception as e:
            logger.error(f"[_send_if_acp_robust] Failed to send message: {e}", exc_info=True)
            
            # Try to force flush
            try:
                sys.stdout.flush()
            except:
                pass
            
            if self.fallback_to_console:
                return None
            else:
                raise
    
    # ========== Public API ==========
    
    def start_session(self):
        """Start an ACP streaming session"""
        if self.acp_enabled and self.stream_manager:
            self._run_async(self.stream_manager.start_stream())
            self.is_streaming = True
    
    def end_session(self, final_answer: Optional[str] = None):
        """End the ACP streaming session"""
        if self.acp_enabled and self.stream_manager and self.is_streaming:
            self._run_async(self.stream_manager.end_stream(final_answer))
            self.is_streaming = False
    
    def thinking(self, message: str):
        """
        Send a thinking update
        
        Args:
            message: Thinking content
        """
        self._send_if_acp(self.builder.build_thinking_update, message)
    
    def answer(self, message: str, stream_end: bool = False, stream_start_id: str = ""):
        """
        Send an answer chunk
        
        Args:
            message: Answer content
            stream_end: Whether this is the last chunk of the answer stream
            stream_start_id: The ID of the first message in this stream (required)
        """
        # Use build_message_chunk to support stream_end parameter
        msg_func = lambda: self.builder.build_message_chunk(
            message,
            chunk_type="answer",
            is_streaming=True,
            stream_end=stream_end,
            stream_start_id=stream_start_id
        )
        self._send_if_acp(msg_func)
    
    def tool_output(self, message: str):
        """
        Send tool output
        
        Args:
            message: Tool output content
        """
        self._send_if_acp(self.builder.build_tool_use_chunk, message)
    
    def interactive_input_request(
        self,
        prompt: str,
        input_type: str = "text",
        is_password: bool = False
    ):
        """
        Send interactive input request
        
        Used when a command needs user input (e.g., password, confirmation).
        The frontend should display the prompt and wait for user input.
        
        Args:
            prompt: The prompt text to display to the user
            input_type: Type of input expected ("text", "password", "confirmation")
            is_password: Whether the input should be masked (for passwords)
        """
        self._send_if_acp(
            self.builder.build_interactive_input_request,
            prompt=prompt,
            input_type=input_type,
            is_password=is_password
        )
    
    def interactive_input_cancel(self, reason: str = "timeout"):
        """
        Send interactive input cancel notification
        
        Used to dismiss/cancel an active interactive input prompt on the frontend.
        This is sent when the backend times out or the command is cancelled while
        waiting for user input (e.g., password prompt).
        
        Args:
            reason: Reason for cancellation ("timeout", "cancelled", "error")
        """
        self._send_if_acp(
            self.builder.build_interactive_input_cancel,
            reason=reason
        )
    
    def tool_call(
        self,
        tool_name: str,
        arguments: Optional[dict] = None,
        result: Optional[Any] = None,
        tool_call_id: Optional[str] = None
    ):
        """
        Send tool call update
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            result: Tool result
            tool_call_id: Unique tool call ID (auto-generated if not provided)
        """
        if tool_call_id is None:
            self._tool_call_counter += 1
            tool_call_id = f"tool_call_{self._tool_call_counter}"
        
        self._send_if_acp(
            self.builder.build_tool_call_update,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=arguments,
            result=result
        )
    
    def complete(self, message: Optional[str] = None):
        """
        Send completion notification
        
        Args:
            message: Optional completion message
        """
        self._send_if_acp(self.builder.build_completed, message)
    
    def error(self, message: str):
        """
        Send error notification
        
        Args:
            message: Error message
        """
        self._send_if_acp(self.builder.build_failed, message)
    
    def cancelled(self, reason: Optional[str] = None):
        """
        Send cancellation notification
        
        Args:
            reason: Cancellation reason
        """
        self._send_if_acp(self.builder.build_cancelled, reason)
    
    # ========== Context Manager ==========
    
    @contextmanager
    def session(self):
        """
        Context manager for ACP session
        
        Usage:
            with adapter.session():
                adapter.thinking("...")
                adapter.answer("...")
        """
        self.start_session()
        try:
            yield self
        except Exception as e:
            self.error(str(e))
            raise
        finally:
            self.end_session()
    
    # ========== Advanced Features ==========
    
    def stream_answer_line_by_line(
        self,
        answer: str,
        delay_ms: int = 0
    ):
        """
        Stream answer line by line
        
        Args:
            answer: Complete answer text
            delay_ms: Delay between lines in milliseconds
        """
        if not self.acp_enabled or not self.stream_manager:
            return
        
        self._run_async(
            self.stream_manager.stream_answer_line_by_line(answer, delay_ms)
        )
    
    def stream_answer_char_by_char(
        self,
        answer: str,
        delay_ms: int = 10
    ):
        """
        Stream answer character by character
        
        Args:
            answer: Complete answer text
            delay_ms: Delay between characters in milliseconds
        """
        if not self.acp_enabled or not self.stream_manager:
            return
        
        self._run_async(
            self.stream_manager.stream_answer_char_by_char(answer, delay_ms)
        )
    
    # ========== Cleanup ==========
    
    def cleanup(self):
        """Cleanup resources"""
        if self.acp_enabled and self.transport:
            try:
                if self.is_streaming:
                    self.end_session()
                self._run_async(self.transport.disconnect())
            except Exception as e:
                print(f"Warning: Cleanup error: {e}", file=sys.stderr)
    
    def __del__(self):
        """Destructor"""
        try:
            self.cleanup()
        except:
            pass


class ACPModeDetector:
    """
    Detects whether to use ACP mode based on environment
    
    Checks for:
    - Environment variable: SIADA_ACP_MODE
    - Command line argument: --acp
    - Configuration file setting
    """
    
    @staticmethod
    def should_use_acp() -> bool:
        """
        Determine if ACP mode should be used
        
        Returns:
            True if ACP mode should be enabled
        """
        import os
        
        # Check environment variable
        if os.environ.get('SIADA_ACP_MODE', '').lower() in ('1', 'true', 'yes'):
            return True
        
        # Check command line arguments
        if '--acp' in sys.argv:
            return True
        
        # Default: disabled
        return False
    
    @staticmethod
    def get_acp_transport():
        """
        Get transport based on configuration
        
        Returns:
            Configured transport or None
        """
        import os
        
        transport_type = os.environ.get('SIADA_ACP_TRANSPORT', 'stdio').lower()
        
        if transport_type == 'stdio':
            return StdioTransport()
        else:
            # Future: support other transport types
            return StdioTransport()


# Convenience function
def create_io_adapter(
    acp_enabled: Optional[bool] = None,
    **kwargs
) -> LegacyACPAdapter:
    """
    Create IO adapter with automatic mode detection
    
    Args:
        acp_enabled: Override auto-detection (None = auto-detect)
        **kwargs: Additional arguments for LegacyACPAdapter
    
    Returns:
        Configured adapter
    
    Example:
        # Auto-detect mode
        adapter = create_io_adapter()
        
        # Force ACP mode
        adapter = create_io_adapter(acp_enabled=True)
    """
    if acp_enabled is None:
        acp_enabled = ACPModeDetector.should_use_acp()
    
    if acp_enabled and 'transport' not in kwargs:
        kwargs['transport'] = ACPModeDetector.get_acp_transport()
    
    return LegacyACPAdapter(acp_enabled=acp_enabled, **kwargs)
