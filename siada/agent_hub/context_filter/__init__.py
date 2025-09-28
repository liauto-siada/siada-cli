"""
Context filter module for processing and managing message context.

This module provides filters for capturing, transforming, and managing
message context before LLM calls.
"""

from .base_filter import ContextFilter
from .context_capture_filter import context_capture_filter, get_context_filters
from .message_history_capture_filter import MessageHistoryCaptureFilter
from .api_message_transfer_filter import ApiMessageTransferFilter
from .utils import compute_message_signature

__all__ = [
    # Main filter function
    'context_capture_filter',
    'get_context_filters',
    
    # Filter interface
    'ContextFilter',
    
    # Filter implementations
    'MessageHistoryCaptureFilter',
    'ApiMessageTransferFilter',
    
    # Utility functions
    'compute_message_signature',
]