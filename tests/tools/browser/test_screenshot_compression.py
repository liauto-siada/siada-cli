"""
Test screenshot compression functionality for browser automation tool.

This module tests the screenshot compression features including different
compression levels, formats, and scaling options.
"""

import asyncio
import base64
import logging
from io import BytesIO
from PIL import Image

import pytest

from siada.tools.browser.browser_action_tool import BrowserActionTool
from siada.tools.browser.models import (
    BrowserSettings, 
    ScreenshotConfig, 
    CompressionLevel,
    ImageResult
)


class TestScreenshotCompression:
    """Test cases for screenshot compression functionality."""

    @pytest.fixture
    def sample_settings_low_compression(self):
        """Create browser settings with low compression."""
        screenshot_config = ScreenshotConfig(
            compression_level=CompressionLevel.LOW,
            jpeg_quality=90,
            max_width=0,
            max_height=0,
            format="png"
        )
        return BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000,
            screenshot_config=screenshot_config
        )

    @pytest.fixture
    def sample_settings_medium_compression(self):
        """Create browser settings with medium compression."""
        screenshot_config = ScreenshotConfig(
            compression_level=CompressionLevel.MEDIUM,
            jpeg_quality=75,
            max_width=1200,
            max_height=800,
            format="jpeg"
        )
        return BrowserSettings(
            viewport={"width": 1200, "height": 800},
            headless=True,
            timeout=30000,
            screenshot_config=screenshot_config
        )

    @pytest.fixture
    def sample_settings_high_compression(self):
        """Create browser settings with high compression."""
        screenshot_config = ScreenshotConfig(
            compression_level=CompressionLevel.HIGH,
            jpeg_quality=60,
            max_width=800,
            max_height=600,
            format="jpeg"
        )
        return BrowserSettings(
            viewport={"width": 1200, "height": 800},
            headless=True,
            timeout=30000,
            screenshot_config=screenshot_config
        )

    def test_compression_level_enum(self):
        """Test compression level enum values."""
        assert CompressionLevel.LOW.value == "low"
        assert CompressionLevel.MEDIUM.value == "medium"
        assert CompressionLevel.HIGH.value == "high"

    def test_screenshot_config_validation(self):
        """Test screenshot configuration validation."""
        # Valid configuration
        config = ScreenshotConfig(
            compression_level=CompressionLevel.MEDIUM,
            jpeg_quality=75,
            max_width=1200,
            max_height=800,
            format="jpeg"
        )
        assert config.compression_level == CompressionLevel.MEDIUM
        assert config.jpeg_quality == 75

        # Invalid JPEG quality
        with pytest.raises(ValueError, match="jpeg_quality must be an integer between 1 and 100"):
            ScreenshotConfig(jpeg_quality=150)

        # Invalid format
        with pytest.raises(ValueError, match="format must be 'png' or 'jpeg'"):
            ScreenshotConfig(format="gif")

        # Invalid dimensions
        with pytest.raises(ValueError, match="max_width must be a non-negative integer"):
            ScreenshotConfig(max_width=-100)

    def test_optimized_settings(self):
        """Test optimized settings for different compression levels."""
        # Low compression
        config_low = ScreenshotConfig(compression_level=CompressionLevel.LOW)
        settings_low = config_low.get_optimized_settings()
        assert settings_low["format"] == "png"
        assert settings_low["jpeg_quality"] == 90
        assert settings_low["max_width"] == 0
        assert settings_low["max_height"] == 0

        # Medium compression
        config_medium = ScreenshotConfig(compression_level=CompressionLevel.MEDIUM)
        settings_medium = config_medium.get_optimized_settings()
        assert settings_medium["format"] == "jpeg"
        assert settings_medium["jpeg_quality"] == 75
        assert settings_medium["max_width"] == 1200
        assert settings_medium["max_height"] == 800

        # High compression
        config_high = ScreenshotConfig(compression_level=CompressionLevel.HIGH)
        settings_high = config_high.get_optimized_settings()
        assert settings_high["format"] == "jpeg"
        assert settings_high["jpeg_quality"] == 60
        assert settings_high["max_width"] == 800
        assert settings_high["max_height"] == 600

    def test_image_result_with_format(self):
        """Test ImageResult creation with different formats."""
        # Test with PNG format
        image_result_png = ImageResult.from_base64("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==", "png")
        assert image_result_png.type == "image_url"
        assert "data:image/png;base64," in image_result_png.image_url.url

        # Test with JPEG format
        image_result_jpeg = ImageResult.from_base64("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==", "jpeg")
        assert image_result_jpeg.type == "image_url"
        assert "data:image/jpeg;base64," in image_result_jpeg.image_url.url

        # Test with invalid format
        with pytest.raises(ValueError, match="image_format must be 'png' or 'jpeg'"):
            ImageResult.from_base64("test", "gif")

    def test_scale_image_functionality(self):
        """Test image scaling functionality."""
        # Create a test browser tool instance
        settings = BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000
        )
        tool = BrowserActionTool(settings)

        # Create a test image (100x100 pixels)
        test_image = Image.new("RGB", (100, 100), color="red")

        # Test scaling down
        scaled_image = tool._scale_image(test_image, 50, 50)
        assert scaled_image.size == (50, 50)

        # Test scaling with aspect ratio preservation
        scaled_image_aspect = tool._scale_image(test_image, 50, 100)
        assert scaled_image_aspect.size == (50, 50)  # Should maintain aspect ratio

        # Test no scaling when max dimensions are larger
        no_scale_image = tool._scale_image(test_image, 200, 200)
        assert no_scale_image.size == (100, 100)  # Original size

        # Test no scaling when max dimensions are 0
        no_limit_image = tool._scale_image(test_image, 0, 0)
        assert no_limit_image.size == (100, 100)  # Original size

    async def test_compression_reduces_size(self):
        """Test that compression actually reduces file size."""
        settings = BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000
        )
        tool = BrowserActionTool(settings)

        # Create a test PNG image (larger size for better compression testing)
        test_image = Image.new("RGB", (800, 600), color="blue")
        png_buffer = BytesIO()
        test_image.save(png_buffer, format="PNG")
        original_bytes = png_buffer.getvalue()

        # Test JPEG compression
        jpeg_settings = {
            "format": "jpeg",
            "jpeg_quality": 75,
            "max_width": 0,
            "max_height": 0
        }
        compressed_bytes = await tool._compress_screenshot(original_bytes, jpeg_settings)
        
        # JPEG should be significantly smaller than PNG for solid colors
        assert len(compressed_bytes) < len(original_bytes)
        print(f"Original PNG: {len(original_bytes)} bytes")
        print(f"Compressed JPEG: {len(compressed_bytes)} bytes")
        print(f"Compression ratio: {(1 - len(compressed_bytes) / len(original_bytes)) * 100:.1f}%")

        # Test scaling compression
        scaling_settings = {
            "format": "jpeg",
            "jpeg_quality": 75,
            "max_width": 400,
            "max_height": 300
        }
        scaled_compressed_bytes = await tool._compress_screenshot(original_bytes, scaling_settings)
        
        # Scaled image should be even smaller
        assert len(scaled_compressed_bytes) < len(compressed_bytes)
        print(f"Scaled + compressed: {len(scaled_compressed_bytes)} bytes")

    def test_browser_settings_default_screenshot_config(self):
        """Test that browser settings initialize default screenshot config."""
        settings = BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000
        )
        
        # Should have default screenshot config
        assert settings.screenshot_config is not None
        assert settings.screenshot_config.compression_level == CompressionLevel.MEDIUM
        assert settings.screenshot_config.format == "jpeg"
        assert settings.screenshot_config.jpeg_quality == 75

    def test_browser_settings_custom_screenshot_config(self):
        """Test browser settings with custom screenshot config."""
        custom_config = ScreenshotConfig(
            compression_level=CompressionLevel.HIGH,
            jpeg_quality=50,
            max_width=600,
            max_height=400,
            format="jpeg"
        )
        
        settings = BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000,
            screenshot_config=custom_config
        )
        
        assert settings.screenshot_config.compression_level == CompressionLevel.HIGH
        assert settings.screenshot_config.jpeg_quality == 50
        assert settings.screenshot_config.max_width == 600
        assert settings.screenshot_config.max_height == 400


if __name__ == "__main__":
    # Run a simple compression test
    async def demo_compression():
        """Demonstrate compression functionality."""
        print("=== Screenshot Compression Demo ===")
        
        # Test different compression levels
        levels = [CompressionLevel.LOW, CompressionLevel.MEDIUM, CompressionLevel.HIGH]
        
        for level in levels:
            config = ScreenshotConfig(compression_level=level)
            settings = config.get_optimized_settings()
            print(f"\n{level.value.upper()} compression:")
            print(f"  Format: {settings['format']}")
            print(f"  JPEG Quality: {settings['jpeg_quality']}")
            print(f"  Max Width: {settings['max_width']}")
            print(f"  Max Height: {settings['max_height']}")

        # Test actual compression
        settings = BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=30000
        )
        tool = BrowserActionTool(settings)

        # Create test image
        test_image = Image.new("RGB", (800, 600), color="green")
        png_buffer = BytesIO()
        test_image.save(png_buffer, format="PNG")
        original_bytes = png_buffer.getvalue()

        print(f"\nOriginal PNG size: {len(original_bytes)} bytes")

        # Test different compression settings
        test_settings = [
            {"format": "png", "jpeg_quality": 90, "max_width": 0, "max_height": 0},
            {"format": "jpeg", "jpeg_quality": 90, "max_width": 0, "max_height": 0},
            {"format": "jpeg", "jpeg_quality": 75, "max_width": 0, "max_height": 0},
            {"format": "jpeg", "jpeg_quality": 60, "max_width": 0, "max_height": 0},
            {"format": "jpeg", "jpeg_quality": 75, "max_width": 400, "max_height": 300},
        ]

        for i, test_setting in enumerate(test_settings):
            compressed = await tool._compress_screenshot(original_bytes, test_setting)
            ratio = (1 - len(compressed) / len(original_bytes)) * 100
            print(f"Test {i+1}: {len(compressed)} bytes ({ratio:.1f}% reduction) - {test_setting}")

    # Run the demo
    asyncio.run(demo_compression())
