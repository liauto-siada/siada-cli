from dataclasses import dataclass, field
from typing import List, Optional

from agents import TResponseInputItem


@dataclass
class TaskMessageState:
    """
    Task message state for managing conversation history.
    
    This state manages the message history instead of storing it directly in CodeAgentContext,
    providing better separation of concerns and memory management.
    """
    task_id: str = ""
    # Complete message history list
    message_history: List[TResponseInputItem] = field(default_factory=list)
    
    def add_message(self, message: TResponseInputItem) -> None:
        """Add a single message to the history."""
        self.message_history.append(message)
    
    def add_messages(self, messages: List[TResponseInputItem]) -> None:
        """Add multiple messages to the history."""
        self.message_history.extend(messages)
    
    def reset_message_history(self, message_history: List[TResponseInputItem]) -> None:
        """Reset the entire message history."""
        self.message_history = message_history
    
    def remove_old_messages(self, remove_count: int) -> List[TResponseInputItem]:
        """
        Remove old messages, return remaining message list, always keep the first message.
        
        Args:
            remove_count: Number of messages to remove
            
        Returns:
            Copy of the remaining message history
        """
        if remove_count <= 0:
            return self.message_history.copy()
        
        # If history is empty or has only one message, don't remove any messages
        if len(self.message_history) <= 1:
            return self.message_history.copy()
        
        # Calculate actual removable message count (keep first message)
        max_removable = len(self.message_history) - 1
        actual_remove_count = min(remove_count, max_removable)
        
        # Remove N messages after the 1st message (index 1 to 1+actual_remove_count)
        # Keep the first message and remaining messages
        self.message_history = [self.message_history[0]] + self.message_history[1 + actual_remove_count:]
        return self.message_history.copy()
    
    def get_message_count(self) -> int:
        """Get the total number of messages in history."""
        return len(self.message_history)
    
    def get_messages(self, limit: Optional[int] = None) -> List[TResponseInputItem]:
        """
        Get messages from history.
        
        Args:
            limit: Maximum number of messages to return. If None, returns all messages.
                   When specified, returns the latest N messages.
                   
        Returns:
            List of messages
        """
        if limit is None:
            return self.message_history.copy()
        else:
            return self.message_history[-limit:] if len(self.message_history) > limit else self.message_history.copy()
    
    def clear_messages(self) -> None:
        """Clear all messages from history."""
        self.message_history.clear()
    
    def sync_from_openai_session(self, messages: List[TResponseInputItem]) -> None:
        """
        Sync messages from OpenAI session to this TaskMessageState.
        
        Args:
            messages: List of messages to sync from the OpenAI session
        """
        # Reset the message history with the synced messages
        self.reset_message_history(messages)