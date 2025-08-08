"""
Data models for browser automation tools.

This module defines the data structures used by the browser automation tools,
including configuration settings and result objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class BrowserSettings:
    """Configuration settings for browser automation.
    
    Attributes:
        viewport: Dictionary containing width and height of the browser viewport
        headless: Whether to run browser in headless mode (default: False)
        timeout: Default timeout in milliseconds for browser operations (default: 30000)
    """
    viewport: Dict[str, int]
    headless: bool = False
    timeout: int = 30000

    def __post_init__(self):
        """Validate viewport settings after initialization."""
        if not isinstance(self.viewport, dict):
            raise ValueError("viewport must be a dictionary")
        
        if "width" not in self.viewport or "height" not in self.viewport:
            raise ValueError("viewport must contain 'width' and 'height' keys")
        
        if not isinstance(self.viewport["width"], int) or not isinstance(self.viewport["height"], int):
            raise ValueError("viewport width and height must be integers")
        
        if self.viewport["width"] <= 0 or self.viewport["height"] <= 0:
            raise ValueError("viewport width and height must be positive integers")
        
        if self.timeout <= 0:
            raise ValueError("timeout must be a positive integer")


@dataclass
class BrowserActionResult:
    """Result object for browser actions.
    
    Attributes:
        success: Whether the operation was successful
        screenshot: Base64-encoded screenshot of the browser state (optional)
        console_logs: List of console log messages captured during the operation
        error: Error message if the operation failed (optional)
    """
    success: bool
    screenshot: Optional[str]
    console_logs: List[str]
    error: Optional[str] = None

    def __post_init__(self):
        """Validate result data after initialization."""
        if not isinstance(self.success, bool):
            raise ValueError("success must be a boolean")
        
        if self.screenshot is not None and not isinstance(self.screenshot, str):
            raise ValueError("screenshot must be a string or None")
        
        if not isinstance(self.console_logs, list):
            raise ValueError("console_logs must be a list")
        
        if not all(isinstance(log, str) for log in self.console_logs):
            raise ValueError("all console_logs entries must be strings")
        
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError("error must be a string or None")
