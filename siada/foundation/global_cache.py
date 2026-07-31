"""
Global Cache Module

Provides thread-safe global cache for cross-thread data sharing.
Unlike contextvars which is thread-isolated, this cache is shared across all threads.

This module is designed for scenarios where data needs to be shared across different threads,
such as in the dedicated event loop pattern used by ConversationTurn.
"""
import threading
from typing import Any, Dict, Optional


class GlobalCache:
    """
    Thread-safe global cache for sharing data across threads.
    
    Unlike contextvars.ContextVar which provides thread-local storage,
    this cache is truly global and shared across all threads in the process.
    
    Uses threading.RLock for thread safety, allowing recursive locking
    within the same thread.
    """
    
    def __init__(self):
        """Initialize the global cache with an empty dictionary and a reentrant lock."""
        self._cache: Dict[str, Any] = {}
        self._lock = threading.RLock()  # Reentrant lock supports recursive locking
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the global cache.
        
        Args:
            key: The key to store the value under
            value: The value to store
        """
        with self._lock:
            self._cache[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the global cache.
        
        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The value associated with the key, or default if not found
        """
        with self._lock:
            return self._cache.get(key, default)
    
    def remove(self, key: str) -> None:
        """
        Remove a key from the global cache.
        
        Args:
            key: The key to remove
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """Clear all items in the global cache."""
        with self._lock:
            self._cache.clear()
    
    def has(self, key: str) -> bool:
        """
        Check if a key exists in the cache.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key exists, False otherwise
        """
        with self._lock:
            return key in self._cache
    
    def keys(self):
        """
        Get all keys in the cache.
        
        Returns:
            A list of all keys
        """
        with self._lock:
            return list(self._cache.keys())
    
    def __len__(self) -> int:
        """Get the number of items in the cache."""
        with self._lock:
            return len(self._cache)


# Global instance - singleton pattern
_global_cache = GlobalCache()

# Define constant keys
LAST_MEMORY_NAME = 'LAST_MEMORY_NAME'
ACP_LEGACY_ADAPTER = 'ACP_LEGACY_ADAPTER'

# Provide convenience functions
def set_global_cache(key: str, value: Any) -> None:
    """
    Set a value in the global cache.
    
    Args:
        key: The key to store the value under
        value: The value to store
    """
    _global_cache.set(key, value)


def get_global_cache(key: str, default: Any = None) -> Any:
    """
    Get a value from the global cache.
    
    Args:
        key: The key to retrieve
        default: Default value if key doesn't exist
        
    Returns:
        The value associated with the key, or default if not found
    """
    return _global_cache.get(key, default)


def remove_global_cache(key: str) -> None:
    """
    Remove a key from the global cache.
    
    Args:
        key: The key to remove
    """
    _global_cache.remove(key)


def clear_global_cache() -> None:
    """Clear all items in the global cache."""
    _global_cache.clear()


def has_global_cache(key: str) -> bool:
    """
    Check if a key exists in the cache.
    
    Args:
        key: The key to check
        
    Returns:
        True if the key exists, False otherwise
    """
    return _global_cache.has(key)
