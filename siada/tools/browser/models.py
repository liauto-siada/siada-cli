"""
Data models for browser automation tools.

This module defines the data structures used by the browser automation tools,
including configuration settings and result objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class CompressionLevel(Enum):
    """Screenshot compression levels."""
    LOW = "low"      # Minimal compression, highest quality
    MEDIUM = "medium"  # Balanced compression and quality
    HIGH = "high"    # Maximum compression, lower quality


@dataclass
class ScreenshotConfig:
    """Configuration for screenshot compression and optimization.
    
    Attributes:
        compression_level: Compression level (LOW/MEDIUM/HIGH)
        jpeg_quality: JPEG quality (1-100, only used when format is JPEG)
        max_width: Maximum width for screenshot scaling (0 = no limit)
        max_height: Maximum height for screenshot scaling (0 = no limit)
        format: Image format ('png' or 'jpeg')
    """
    compression_level: CompressionLevel = CompressionLevel.HIGH
    jpeg_quality: int = 75
    max_width: int = 0
    max_height: int = 0
    format: str = "jpeg"

    def __post_init__(self):
        """Validate screenshot configuration after initialization."""
        if not isinstance(self.compression_level, CompressionLevel):
            raise ValueError("compression_level must be a CompressionLevel enum")
        
        if not isinstance(self.jpeg_quality, int) or not (1 <= self.jpeg_quality <= 100):
            raise ValueError("jpeg_quality must be an integer between 1 and 100")
        
        if not isinstance(self.max_width, int) or self.max_width < 0:
            raise ValueError("max_width must be a non-negative integer")
        
        if not isinstance(self.max_height, int) or self.max_height < 0:
            raise ValueError("max_height must be a non-negative integer")
        
        if self.format not in ["png", "jpeg"]:
            raise ValueError("format must be 'png' or 'jpeg'")

    def get_optimized_settings(self) -> dict:
        """Get optimized settings based on compression level.
        
        Returns:
            dict: Optimized settings for the current compression level
        """
        if self.compression_level == CompressionLevel.LOW:
            return {
                "format": "png"  # High quality, no compression
            }
        elif self.compression_level == CompressionLevel.MEDIUM:
            return {
                "format": "jpeg",
                "jpeg_quality": 75  # Balanced quality and size
            }
        else:  # HIGH compression
            return {
                "format": "jpeg",
                "jpeg_quality": 60  # Higher compression, smaller size
            }


@dataclass
class BrowserSettings:
    """Configuration settings for browser automation.
    
    Attributes:
        viewport: Dictionary containing width and height of the browser viewport
        headless: Whether to run browser in headless mode (default: False)
        timeout: Default timeout in milliseconds for browser operations (default: 30000)
        screenshot_config: Configuration for screenshot compression and optimization
    """
    viewport: Dict[str, int]
    headless: bool = False
    timeout: int = 30000
    screenshot_config: ScreenshotConfig = None

    def __post_init__(self):
        """Validate and initialize settings after initialization."""
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
        
        # Initialize default screenshot config if not provided
        if self.screenshot_config is None:
            self.screenshot_config = ScreenshotConfig()


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


@dataclass
class ImageUrl:
    """Image URL data structure for ImageResult.
    
    Attributes:
        url: Base64-encoded image data URL (e.g., "data:image/png;base64,...")
        axtree_info: Accessibility tree information (optional)
    """
    url: str
    axtree_info: Optional[Dict] = None

    def __post_init__(self):
        """Validate image URL data after initialization."""
        if not isinstance(self.url, str):
            raise ValueError("url must be a string")
        
        if not self.url:
            raise ValueError("url cannot be empty")
        
        if self.axtree_info is not None and not isinstance(self.axtree_info, dict):
            raise ValueError("axtree_info must be a dictionary or None")


@dataclass
class ImageResult:
    """Result object for image data with structured format.
    
    This class represents image data in a standardized format suitable for
    API responses and message content that includes images.
    
    Attributes:
        type: Type identifier for the content, fixed as "image_url"
        image_url: ImageUrl object containing the actual image data
    """
    type: str
    image_url: ImageUrl

    def __post_init__(self):
        """Validate image result data after initialization."""
        if not isinstance(self.type, str):
            raise ValueError("type must be a string")
        
        if self.type != "image_url":
            raise ValueError("type must be 'image_url'")
        
        if not isinstance(self.image_url, ImageUrl):
            raise ValueError("image_url must be an ImageUrl instance")

    @classmethod
    def from_base64(cls, base64_data: str, image_format: str = "png") -> "ImageResult":
        """Create ImageResult from base64 image data.
        
        Args:
            base64_data: Base64-encoded image data
            image_format: Image format ('png' or 'jpeg')
            
        Returns:
            ImageResult: Constructed image result object
        """
        if not isinstance(base64_data, str):
            raise ValueError("base64_data must be a string")
        
        if image_format not in ["png", "jpeg", "webp"]:
            raise ValueError("image_format must be 'png', 'jpeg', or 'webp'")
        
        # Construct the data URL with dynamic format
        data_url = f"data:image/{image_format};base64,{base64_data}"
        
        return cls(
            type="image_url",
            image_url=ImageUrl(url=data_url)
        )
