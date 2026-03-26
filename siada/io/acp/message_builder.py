"""
ACP Message Builder

Builds standard ACP (Agent Client Protocol) messages following JSON-RPC 2.0 format.

Reference: https://agentclientprotocol.com/
"""

from typing import Dict, Any, Optional, Literal, Union
from dataclasses import dataclass, field
import json
from enum import Enum


class ACPMessageType(Enum):
    """ACP message types"""
    NOTIFICATION = "notification"
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"


class SessionUpdateReason(Enum):
    """Session update reasons
    
    Used in session/update notifications to indicate what type of update this is.
    """
    MESSAGE_CHUNK = "message_chunk"
    TOOL_CALL = "tool_call"
    THINKING = "thinking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERACTIVE_INPUT_REQUEST = "interactive_input_request"  # Request user input for interactive command
    INTERACTIVE_INPUT_CANCEL = "interactive_input_cancel"    # Cancel/dismiss interactive input (e.g., timeout)


@dataclass
class ACPMessage:
    """
    ACP Standard Message (JSON-RPC 2.0 format)
    
    Examples:
        Notification:
            {"jsonrpc": "2.0", "method": "session/update", "params": {...}}
        
        Request:
            {"jsonrpc": "2.0", "id": 1, "method": "agent/execute", "params": {...}}
        
        Response:
            {"jsonrpc": "2.0", "id": 1, "result": {...}}
        
        Error:
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "..."}}
    """
    jsonrpc: str = "2.0"
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[int, str]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        data = {"jsonrpc": self.jsonrpc}
        
        if self.method is not None:
            data['method'] = self.method
        if self.params is not None:
            data['params'] = self.params
        if self.id is not None:
            data['id'] = self.id
        if self.result is not None:
            data['result'] = self.result
        if self.error is not None:
            data['error'] = self.error
        
        return data
    
    def to_json(self, ensure_ascii: bool = False, indent: Optional[int] = None) -> str:
        """
        Convert to JSON string
        
        Args:
            ensure_ascii: If True, escape non-ASCII characters
            indent: Pretty print with indentation (None for compact)
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ACPMessage':
        """
        Parse from JSON string
        
        Args:
            json_str: JSON string to parse
        
        Returns:
            ACPMessage instance
        
        Raises:
            json.JSONDecodeError: If invalid JSON
        """
        data = json.loads(json_str)
        return cls(**data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ACPMessage':
        """Create from dictionary"""
        return cls(**data)
    
    def is_notification(self) -> bool:
        """Check if this is a notification (has method but no id)"""
        return self.method is not None and self.id is None
    
    def is_request(self) -> bool:
        """Check if this is a request (has method and id)"""
        return self.method is not None and self.id is not None
    
    def is_response(self) -> bool:
        """Check if this is a response (has id and result)"""
        return self.id is not None and self.result is not None
    
    def is_error(self) -> bool:
        """Check if this is an error response (has id and error)"""
        return self.id is not None and self.error is not None


class ACPMessageBuilder:
    """
    ACP Message Builder
    
    Provides convenient methods to build standard ACP messages.
    
    Usage:
        builder = ACPMessageBuilder()
        
        # Build a thinking update
        msg = builder.build_thinking_update("Analyzing the problem...")
        
        # Build an answer chunk
        msg = builder.build_answer_chunk("Here's the answer")
        
        # Send via transport
        await transport.send(msg)
    """
    
    def __init__(self, start_id: int = 0):
        """
        Initialize builder
        
        Args:
            start_id: Starting message ID for requests
        """
        self._message_id_counter = start_id
    
    def _next_id(self) -> int:
        """Generate next message ID"""
        self._message_id_counter += 1
        return self._message_id_counter
    
    def build_session_update(
        self,
        reason: Union[SessionUpdateReason, str],
        content: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ACPMessage:
        """
        Build session/update notification
        
        This is the core ACP message for reporting agent execution status.
        
        Args:
            reason: Update reason (message_chunk, tool_call, thinking, completed, etc.)
            content: Message content
            tool_call_id: Tool call identifier (for tool_call reason)
            metadata: Additional metadata in _meta field
        
        Returns:
            ACPMessage notification
        
        Examples:
            # Thinking update
            msg = builder.build_session_update(
                reason=SessionUpdateReason.THINKING,
                content="Analyzing..."
            )
            
            # Tool call update
            msg = builder.build_session_update(
                reason=SessionUpdateReason.TOOL_CALL,
                tool_call_id="call_123",
                content='{"tool": "calculator", "result": 42}'
            )
        """
        # Convert enum to string if needed
        if isinstance(reason, SessionUpdateReason):
            reason = reason.value
        
        params: Dict[str, Any] = {
            "reason": reason,
        }
        
        if content is not None:
            params["content"] = content
        
        if tool_call_id is not None:
            params["toolCallId"] = tool_call_id
        
        # For lifecycle_event reason, merge metadata directly into params
        # instead of wrapping in _meta, so frontend can access fields directly
        if metadata:
            if reason == "lifecycle_event":
                # Merge metadata fields directly into params for lifecycle events
                params.update(metadata)
            else:
                # For other reasons, keep the _meta wrapper
                params["_meta"] = metadata
        
        return ACPMessage(
            method="session/update",
            params=params
        )
    
    def build_message_chunk(
        self,
        content: str,
        chunk_type: Literal["thinking", "answer", "tool_use"] = "answer",
        is_streaming: bool = True,
        stream_end: bool = False,
        stream_start_id: str = ""
    ) -> ACPMessage:
        """
        Build message chunk for streaming output
        
        Args:
            content: Message content
            chunk_type: Type of chunk (thinking/answer/tool_use)
            is_streaming: Whether this is part of a streaming response
            stream_end: Whether this is the last chunk of the stream
            stream_start_id: The ID of the first message in this stream (for React key stability, required)
        
        Returns:
            ACPMessage with message_chunk reason
        
        Examples:
            # Thinking chunk (streaming)
            msg = builder.build_message_chunk("Thinking...", chunk_type="thinking", is_streaming=True, stream_start_id="msg_1")
            
            # Answer chunk (streaming)
            msg = builder.build_message_chunk("The answer is...", chunk_type="answer", is_streaming=True, stream_start_id="msg_1")
            
            # Final answer chunk (stream end)
            msg = builder.build_message_chunk("Done!", chunk_type="answer", is_streaming=True, stream_end=True, stream_start_id="msg_1")
        """
        metadata = {
            "chunkType": chunk_type,
            "isStreaming": is_streaming,
            "streamEnd": stream_end,
            "streamStartId": stream_start_id  # Always include streamStartId
        }
        
        return self.build_session_update(
            reason=SessionUpdateReason.MESSAGE_CHUNK,
            content=content,
            metadata=metadata
        )
    
    def build_thinking_update(self, thinking: str) -> ACPMessage:
        """
        Build thinking process update
        
        Args:
            thinking: Thinking content
        
        Returns:
            ACPMessage for thinking
        """
        return self.build_message_chunk(thinking, chunk_type="thinking")
    
    def build_answer_chunk(self, answer: str) -> ACPMessage:
        """
        Build answer chunk
        
        Args:
            answer: Answer content
        
        Returns:
            ACPMessage for answer chunk
        """
        return self.build_message_chunk(answer, chunk_type="answer")
    
    def build_tool_use_chunk(self, tool_output: str) -> ACPMessage:
        """
        Build tool use chunk
        
        Args:
            tool_output: Tool output content
        
        Returns:
            ACPMessage for tool use
        """
        return self.build_message_chunk(tool_output, chunk_type="tool_use")
    
    def build_tool_call_update(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: Optional[Dict[str, Any]] = None,
        result: Optional[Any] = None
    ) -> ACPMessage:
        """
        Build tool call update
        
        Args:
            tool_name: Name of the tool being called
            tool_call_id: Unique identifier for this tool call
            arguments: Tool arguments (optional)
            result: Tool execution result (optional)
        
        Returns:
            ACPMessage for tool call
        
        Examples:
            # Tool call start
            msg = builder.build_tool_call_update(
                tool_name="calculator",
                tool_call_id="call_123",
                arguments={"expression": "2+2"}
            )
            
            # Tool call result
            msg = builder.build_tool_call_update(
                tool_name="calculator",
                tool_call_id="call_123",
                result=4
            )
        """
        content_dict = {
            "toolName": tool_name,
        }
        if arguments is not None:
            content_dict["arguments"] = arguments
        if result is not None:
            content_dict["result"] = result
        
        return self.build_session_update(
            reason=SessionUpdateReason.TOOL_CALL,
            content=json.dumps(content_dict, ensure_ascii=False),
            tool_call_id=tool_call_id
        )
    
    def build_completed(self, final_answer: Optional[str] = None) -> ACPMessage:
        """
        Build completion notification
        
        Signals that the agent has finished processing.
        
        Args:
            final_answer: Optional final answer summary
        
        Returns:
            ACPMessage for completion
        """
        return self.build_session_update(
            reason=SessionUpdateReason.COMPLETED,
            content=final_answer
        )
    
    def build_cancelled(self, reason: Optional[str] = None) -> ACPMessage:
        """
        Build cancellation notification
        
        Args:
            reason: Optional cancellation reason
        
        Returns:
            ACPMessage for cancellation
        """
        return self.build_session_update(
            reason=SessionUpdateReason.CANCELLED,
            content=reason
        )
    
    def build_failed(self, error_message: str) -> ACPMessage:
        """
        Build failure notification
        
        Args:
            error_message: Error message describing the failure
        
        Returns:
            ACPMessage for failure
        """
        return self.build_session_update(
            reason=SessionUpdateReason.FAILED,
            content=error_message
        )
    
    def build_interactive_input_request(
        self,
        prompt: str,
        input_type: str = "text",
        is_password: bool = False
    ) -> ACPMessage:
        """
        Build interactive input request notification
        
        Used when a command needs user input (e.g., password, confirmation).
        The frontend should display the prompt and wait for user input.
        
        Args:
            prompt: The prompt text to display to the user
            input_type: Type of input expected ("text", "password", "confirmation")
            is_password: Whether the input should be masked (for passwords)
        
        Returns:
            ACPMessage for interactive input request
        
        Examples:
            # Password prompt
            msg = builder.build_interactive_input_request(
                prompt="Password: ",
                input_type="password",
                is_password=True
            )
            
            # Confirmation prompt
            msg = builder.build_interactive_input_request(
                prompt="Continue? (y/n): ",
                input_type="confirmation"
            )
        """
        metadata = {
            "inputType": input_type,
            "isPassword": is_password,
        }
        
        return self.build_session_update(
            reason=SessionUpdateReason.INTERACTIVE_INPUT_REQUEST,
            content=prompt,
            metadata=metadata
        )
    
    def build_interactive_input_cancel(
        self,
        reason: str = "timeout"
    ) -> ACPMessage:
        """
        Build interactive input cancel notification
        
        Used to dismiss/cancel an active interactive input prompt on the frontend.
        This is sent when the backend times out or the command is cancelled while
        waiting for user input (e.g., password prompt).
        
        Args:
            reason: Reason for cancellation ("timeout", "cancelled", "error")
        
        Returns:
            ACPMessage for interactive input cancel
        
        Examples:
            # Timeout cancel
            msg = builder.build_interactive_input_cancel(reason="timeout")
            
            # Manual cancel
            msg = builder.build_interactive_input_cancel(reason="cancelled")
        """
        metadata = {
            "cancelReason": reason,
        }
        
        return self.build_session_update(
            reason=SessionUpdateReason.INTERACTIVE_INPUT_CANCEL,
            content=f"Interactive input cancelled: {reason}",
            metadata=metadata
        )
    
    def build_error_response(
        self,
        request_id: Union[int, str],
        code: int,
        message: str,
        data: Optional[Any] = None
    ) -> ACPMessage:
        """
        Build error response
        
        Args:
            request_id: ID of the request that caused the error
            code: Error code (JSON-RPC error codes)
            message: Human-readable error message
            data: Additional error data
        
        Returns:
            ACPMessage error response
        
        Error codes (JSON-RPC 2.0):
            -32700: Parse error
            -32600: Invalid request
            -32601: Method not found
            -32602: Invalid params
            -32603: Internal error
            -32000 to -32099: Server errors
        """
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data
        
        return ACPMessage(
            id=request_id,
            error=error
        )
    
    def build_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[Union[int, str]] = None
    ) -> ACPMessage:
        """
        Build a request message
        
        Args:
            method: Method name
            params: Method parameters
            request_id: Request ID (auto-generated if not provided)
        
        Returns:
            ACPMessage request
        """
        if request_id is None:
            request_id = self._next_id()
        
        return ACPMessage(
            id=request_id,
            method=method,
            params=params
        )
    
    def build_response(
        self,
        request_id: Union[int, str],
        result: Any
    ) -> ACPMessage:
        """
        Build a response message
        
        Args:
            request_id: ID of the request being responded to
            result: Response result
        
        Returns:
            ACPMessage response
        """
        return ACPMessage(
            id=request_id,
            result=result
        )
    
    def build_custom_notification(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> ACPMessage:
        """
        Build a custom notification with arbitrary method and params
        
        Used for extending ACP protocol with custom notifications.
        
        Args:
            method: Notification method name (e.g., "ui/showSessionBrowser")
            params: Optional parameters dictionary
        
        Returns:
            ACPMessage notification
        
        Examples:
            # Custom UI notification
            msg = builder.build_custom_notification(
                method="ui/showSessionBrowser",
                params={"scope": "all", "projectRoot": "/path/to/project"}
            )
        """
        return ACPMessage(
            method=method,
            params=params or {}
        )


# Convenience function for quick message creation
def create_thinking_message(content: str) -> ACPMessage:
    """Quick helper to create a thinking message"""
    builder = ACPMessageBuilder()
    return builder.build_thinking_update(content)


def create_answer_message(content: str) -> ACPMessage:
    """Quick helper to create an answer message"""
    builder = ACPMessageBuilder()
    return builder.build_answer_chunk(content)


def create_completion_message(final_answer: Optional[str] = None) -> ACPMessage:
    """Quick helper to create a completion message"""
    builder = ACPMessageBuilder()
    return builder.build_completed(final_answer)
