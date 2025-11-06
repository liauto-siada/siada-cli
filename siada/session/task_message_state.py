from dataclasses import dataclass, field
import re
from typing import List, Optional

from agents import TResponseInputItem

@dataclass
class RealApiMessage:
    """
    Represents a real API message in the conversation.
    """
    
    real_api_history: List[TResponseInputItem] = field(default_factory=list)
    # last_index_at_message_history
    last_index: int = -1
    # the signature of the last message
    last_signature: str = ""
    
    def add(self, message: TResponseInputItem) -> None:
        """Add a single message to real API history."""
        self.real_api_history.append(message)
    
    def add_multiple(self, messages: List[TResponseInputItem]) -> None:
        """Add multiple messages to real API history."""
        self.real_api_history.extend(messages)
    
    def get(self, limit: Optional[int] = None) -> List[TResponseInputItem]:
        """Get real API messages."""
        if limit is None:
            return self.real_api_history.copy()
        return self.real_api_history[-limit:] if len(self.real_api_history) > limit else self.real_api_history.copy()
    
    def reset(self, messages: List[TResponseInputItem]) -> None:
        """Reset real API history with new messages."""
        self.real_api_history = messages
    
    def clear(self) -> None:
        """Clear all real API messages."""
        self.real_api_history.clear()
    
    def update_index(self, index: int) -> None:
        """Update the last index."""
        self.last_index = index
    
    def get_count(self) -> int:
        """Get the count of real API messages."""
        return len(self.real_api_history)
    
    def set_last_signature(self, last_message_signiture):
        self.last_signature = last_message_signiture

    def get_last_signature(self):
        return self.last_signature
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'real_api_history': self.real_api_history,
            'last_index': self.last_index,
            'last_signature': self.last_signature
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'RealApiMessage':
        """Create RealApiMessage from dictionary."""
        return cls(
            real_api_history=data.get('real_api_history', []),
            last_index=data.get('last_index', -1),
            last_signature=data.get('last_signature', '')
        )

    
@dataclass
class ApiMessageHistory:
    """
    Encapsulates message history operations.
    """
    _messages: List[TResponseInputItem] = field(default_factory=list)
    
    def append(self, message: TResponseInputItem) -> None:
        """Add a single message to the history."""
        self._messages.append(message)
    
    def extend(self, messages: List[TResponseInputItem]) -> None:
        """Add multiple messages to the history."""
        self._messages.extend(messages)
    
    def reset(self, messages: List[TResponseInputItem]) -> None:
        """Reset the entire message history."""
        self._messages = messages
    
    def remove_old(self, remove_count: int) -> List[TResponseInputItem]:
        """
        Remove old messages, return remaining message list, always keep the first message.
        
        Args:
            remove_count: Number of messages to remove
            
        Returns:
            Copy of the remaining message history
        """
        if remove_count <= 0:
            return self._messages.copy()
        
        # If history is empty or has only one message, don't remove any messages
        if len(self._messages) <= 1:
            return self._messages.copy()
        
        # Calculate actual removable message count (keep first message)
        max_removable = len(self._messages) - 1
        actual_remove_count = min(remove_count, max_removable)
        
        # Remove N messages after the 1st message (index 1 to 1+actual_remove_count)
        # Keep the first message and remaining messages
        self._messages = [self._messages[0]] + self._messages[1 + actual_remove_count:]
        return self._messages.copy()
    
    def get_count(self) -> int:
        """Get the total number of messages in history."""
        return len(self._messages)
    
    def get(self, limit: Optional[int] = None) -> List[TResponseInputItem]:
        """
        Get messages from history.
        
        Args:
            limit: Maximum number of messages to return. If None, returns all messages.
                   When specified, returns the latest N messages.
                   
        Returns:
            List of messages
        """
        if limit is None:
            return self._messages.copy()
        else:
            return self._messages[-limit:] if len(self._messages) > limit else self._messages.copy()
    
    def clear(self) -> None:
        """Clear all messages from history."""
        self._messages.clear()
    
    def copy(self) -> List[TResponseInputItem]:
        """Get a copy of all messages."""
        return self._messages.copy()


@dataclass
class TaskMessageState:
    """
    Task message state for managing conversation history.
    
    This state manages the message history instead of storing it directly in CodeAgentContext,
    providing better separation of concerns and memory management.
    """
    task_id: str = ""
    # Complete message history list encapsulated in MessageHistory object
    _message_history: ApiMessageHistory = field(default_factory=ApiMessageHistory)

    _real_messages: RealApiMessage = field(default_factory=RealApiMessage)


    def add_message(self, message: TResponseInputItem) -> None:
        """Add a single message to the history."""
        self._message_history.append(message)

    def add_messages(self, messages: List[TResponseInputItem]) -> None:
        """Add multiple messages to the history."""
        self._message_history.extend(messages)

    def reset_message_history(self, message_history: List[TResponseInputItem]) -> None:
        """Reset the entire message history."""
        self._message_history.reset(message_history)

    def remove_old_messages(self, remove_count: int) -> List[TResponseInputItem]:
        """
        Remove old messages, return remaining message list, always keep the first message.
        
        Args:
            remove_count: Number of messages to remove
            
        Returns:
            Copy of the remaining message history
        """
        return self._message_history.remove_old(remove_count)

    def get_message_count(self) -> int:
        """Get the total number of messages in history."""
        return self._message_history.get_count()

    def get_messages(self, limit: Optional[int] = None) -> List[TResponseInputItem]:
        """
        Get messages from history.
        
        Args:
            limit: Maximum number of messages to return. If None, returns all messages.
                   When specified, returns the latest N messages.
                   
        Returns:
            List of messages
        """
        return self._message_history.get(limit)

    def clear_messages(self) -> None:
        """Clear all messages from history."""
        self._message_history.clear()


    def get_real_messages(self, limit: Optional[int] = None) -> List[TResponseInputItem]:
        """
        Get real API messages from history.
        
        Args:
            limit: Maximum number of messages to return. If None, returns all messages.
                   When specified, returns the latest N messages.
                   
        Returns:
            List of real API messages
        """
        return self._real_messages.get(limit)
    
    def get_real_message_last_index(self) -> int:
        """Get the last index of real API messages."""
        return self._real_messages.last_index
    
    def set_real_message_last_index(self, index: int) -> None:
        """Set the last index of real API messages."""
        self._real_messages.update_index(index)

    def get_real_message_last_signature(self) -> str:
        return self._real_messages.get_last_signature()
    
    def set_real_message_last_signature(self, signature: str):
        self._real_messages.set_last_signature(signature)

    def set_real_messages(self, real_messages: RealApiMessage):
        self._real_messages = real_messages

    def reset_real_messages(self):
        self._real_messages = RealApiMessage()
