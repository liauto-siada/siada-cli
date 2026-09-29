"""
Data models for browser automation tools.

This module defines the data structures used by the browser automation tools,
including configuration settings and result objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from siada.tools.coder.observation.observation import FunctionCallResult


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


@dataclass
class BrowserOperateResult(FunctionCallResult):
    """Result object for browser_operate tool that extends FunctionCallResult.
    
    This class provides both UI display and API display formats for browser operation results.
    It stores the action details, page info, accessibility tree, and screenshot data.
    
    Attributes:
        content: The full content for API consumption (from parent class)
        action: The browser action that was executed
        success: Whether the operation was successful
        error: Error message if the operation failed
        page_info: Information about the current page (url, title)
        available_bids: List of available element IDs on the page
        axtree: Formatted accessibility tree content
        screenshot: Base64-encoded screenshot data URL
    """
    action: str = ""
    success: bool = True
    error: Optional[str] = None
    page_info: Dict[str, Any] = field(default_factory=dict)
    available_bids: List[str] = field(default_factory=list)
    axtree: str = ""
    screenshot: Optional[str] = None
    
    def format_for_display(self) -> str:
        """Format the result for UI display.
        
        Returns a concise, human-readable summary suitable for CLI output.
        Does not include the full accessibility tree or screenshot.
        
        Returns:
            str: Formatted string for UI display
        """
        parts = []
        
        # Action status with emoji
        if self.success:
            parts.append(f"✓ Browser action '{self.action}' executed successfully.")
        else:
            parts.append(f"✗ Browser action '{self.action}' failed: {self.error or 'Unknown error'}")
        
        # Page info (if available)
        if self.page_info:
            url = self.page_info.get("url", "")
            title = self.page_info.get("title", "")
            if url:
                # Truncate long URLs for display
                display_url = url if len(url) <= 80 else url[:77] + "..."
                parts.append(f"  URL: {display_url}")
            if title:
                # Truncate long titles for display
                display_title = title if len(title) <= 60 else title[:57] + "..."
                parts.append(f"  Title: {display_title}")
        
        # Available elements summary
        if self.available_bids:
            bid_count = len(self.available_bids)
            parts.append(f"  Available Elements: {bid_count}")
            # Show first 3 element IDs as preview
            if bid_count > 0:
                preview_bids = self.available_bids[:3]
                preview_str = ", ".join(preview_bids)
                if bid_count > 3:
                    preview_str += f" ... and {bid_count - 3} more"
                parts.append(f"  Element IDs: {preview_str}")
        
        return "\n".join(parts)
    
    def format_for_api(self) -> str:
        """Format the result for API consumption.
        
        Returns the JSON serialized content for the LLM.
        
        Returns:
            str: JSON string for API
        """
        return self.content
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Note: screenshot is NOT included in the dict - it will be sent as a 
        separate image block. The 'has_screenshot' field indicates whether 
        a screenshot is available in the following image block.
        
        Note: available_bids is NOT included as a full list to reduce context 
        size. Only the count is included, as the LLM can find specific bids 
        from the accessibility tree (axtree).
        
        Returns:
            Dict[str, Any]: Dictionary representation
        """
        result = {
            "action": self.action,
            "success": self.success,
            "error": self.error,
            "page_info": self.page_info,
            "available_bids_count": len(self.available_bids),
            "axtree": self.axtree,
            "has_screenshot": self.screenshot is not None
        }
        return result
    
    def to_json(self) -> str:
        """Serialize to JSON string.
        
        Returns:
            str: JSON string representation
        """
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str, screenshot: Optional[str] = None) -> "BrowserOperateResult":
        """Deserialize from JSON string.
        
        Args:
            json_str: JSON string
            screenshot: Optional screenshot data
            
        Returns:
            BrowserOperateResult: Reconstructed result object
        """
        import json
        data = json.loads(json_str)
        return cls(
            content=json_str,
            action=data.get("action", ""),
            success=data.get("success", True),
            error=data.get("error"),
            page_info=data.get("page_info", {}),
            available_bids=data.get("available_bids", []),
            axtree=data.get("axtree", ""),
            screenshot=screenshot
        )
    
    def get_api_output_items(self) -> List[Any]:
        """Get the output items for API consumption.
        
        Returns a list containing ToolOutputText and optionally ToolOutputImage
        for use with the agents framework.
        
        Returns:
            List[Any]: List of ToolOutputText and ToolOutputImage items
        """
        from agents import ToolOutputImage, ToolOutputText
        
        outputs = []
        
        # Add text output with full API content
        outputs.append(ToolOutputText(text=self.content))
        
        # Add image output if screenshot is available
        if self.screenshot and self.success:
            screenshot_data = self.screenshot
            # Ensure we have a proper data URL format
            if not screenshot_data.startswith("data:"):
                screenshot_data = f"data:image/jpeg;base64,{screenshot_data}"
            outputs.append(ToolOutputImage(image_url=screenshot_data, detail="auto"))
        
        return outputs
    
    def __str__(self) -> str:
        """String representation returns the API format."""
        return self.format_for_api()
    
    @classmethod
    def from_api_text(
        cls,
        text: str,
        screenshot: Optional[str] = None
    ) -> "BrowserOperateResult":
        """Deserialize a BrowserOperateResult from API text content.
        
        Parses the text content generated by create() to reconstruct
        the BrowserOperateResult object.
        
        Args:
            text: API text content
            screenshot: Optional screenshot data
            
        Returns:
            BrowserOperateResult: Reconstructed result object
        """
        import re
        
        lines = text.split("\n")
        
        # Parse action and success status from first line
        action = ""
        success = True
        error = None
        
        first_line = lines[0].strip() if lines else ""
        if first_line.startswith("Action '"):
            # Extract action name
            action_match = first_line.split("'")
            if len(action_match) >= 2:
                action = action_match[1]
            
            if "executed successfully" in first_line:
                success = True
            elif "failed" in first_line:
                success = False
                # Extract error message after "failed: "
                if "failed: " in first_line:
                    error = first_line.split("failed: ", 1)[1]
        
        # Parse page info
        page_info = {}
        url = ""
        title = ""
        
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("- URL:"):
                url = line_stripped.replace("- URL:", "").strip()
                page_info["url"] = url
            elif line_stripped.startswith("- Title:"):
                title = line_stripped.replace("- Title:", "").strip()
                page_info["title"] = title
        
        # Parse available element IDs count and list
        available_bids = []
        element_count = 0
        in_bids_section = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if "Available Element IDs" in line_stripped:
                # Extract element count
                match = re.search(r'\((\d+)\s+total\)', line_stripped)
                if match:
                    element_count = int(match.group(1))
                in_bids_section = True
            elif in_bids_section and line_stripped and not line_stripped.startswith("..."):
                # Parse bids from comma-separated list
                if "," in line_stripped:
                    bids = [bid.strip() for bid in line_stripped.split(",") if bid.strip()]
                    available_bids.extend(bids)
            elif line_stripped.startswith("... and"):
                in_bids_section = False
        
        # Parse accessibility tree
        axtree = ""
        in_axtree_section = False
        axtree_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if "**Accessibility Tree:**" in line:
                in_axtree_section = True
                continue
            elif in_axtree_section and ("**Available Element IDs" in line or "**Page Info:**" in line):
                in_axtree_section = False
            elif in_axtree_section:
                axtree_lines.append(line)
        
        if axtree_lines:
            axtree = "\n".join(axtree_lines).strip()
        
        return cls(
            content=text,
            action=action,
            success=success,
            error=error,
            page_info=page_info,
            available_bids=available_bids,
            axtree=axtree,
            screenshot=screenshot
        )
    
    @classmethod
    def create(
        cls,
        action: str,
        success: bool,
        error: Optional[str] = None,
        page_info: Optional[Dict[str, Any]] = None,
        available_bids: Optional[List[str]] = None,
        axtree: str = "",
        screenshot: Optional[str] = None
    ) -> "BrowserOperateResult":
        """Factory method to create a BrowserOperateResult with JSON content.
        
        Args:
            action: The browser action that was executed
            success: Whether the operation was successful
            error: Error message if the operation failed
            page_info: Information about the current page
            available_bids: List of available element IDs
            axtree: Formatted accessibility tree content
            screenshot: Base64-encoded screenshot data
            
        Returns:
            BrowserOperateResult: Constructed result object with JSON content
        """
        import json
        
        page_info = page_info or {}
        available_bids = available_bids or []
        
        # Build the object first without content
        result = cls(
            content="",  # Will be set below
            action=action,
            success=success,
            error=error,
            page_info=page_info,
            available_bids=available_bids,
            axtree=axtree,
            screenshot=screenshot
        )
        
        # Set content to JSON serialized string
        result.content = result.to_json()
        
        return result
