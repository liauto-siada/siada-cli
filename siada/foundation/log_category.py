"""
Log category enumeration for categorizing different types of logs.
"""

from enum import Enum


class LogCategory(str, Enum):
    """
    Enumeration for log categories.
    
    This enum is used to categorize logs and route them to different handlers.
    Inherits from str to enable easy serialization and comparison.
    """
    
    GENERAL = "general"           # General application logs (default)
    MODEL_ERROR = "model_error"   # Model/API error logs
