"""
Tests for browser action tool.

This module contains comprehensive tests for the browser automation functionality,
including unit tests and integration tests.
"""

import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from siada.tools.browser import BrowserActionTool, BrowserSettings, BrowserActionResult


class TestBrowserSettings:
    """Test cases for BrowserSettings data model."""

    def test_valid_browser_settings(self):
        """Test creating valid browser settings."""
        settings = BrowserSettings(
            viewport={"width": 900, "height": 600},
            headless=True,
            timeout=30000
        )
        assert settings.viewport == {"width": 900, "height": 600}
        assert settings.headless is True
        assert settings.timeout == 30000

    def test_default_browser_settings(self):
        """Test default values for browser settings."""
        settings = BrowserSettings(viewport={"width": 800, "height": 600})
        assert settings.headless is False
        assert settings.timeout == 30000

    def test_invalid_viewport_type(self):
        """Test validation of viewport type."""
        with pytest.raises(ValueError, match="viewport must be a dictionary"):
            BrowserSettings(viewport="invalid")

    def test_missing_viewport_keys(self):
        """Test validation of required viewport keys."""
        with pytest.raises(ValueError, match="viewport must contain 'width' and 'height' keys"):
            BrowserSettings(viewport={"width": 800})

    def test_invalid_viewport_values(self):
        """Test validation of viewport value types."""
        with pytest.raises(ValueError, match="viewport width and height must be integers"):
            BrowserSettings(viewport={"width": "800", "height": 600})

    def test_negative_viewport_values(self):
        """Test validation of positive viewport values."""
        with pytest.raises(ValueError, match="viewport width and height must be positive integers"):
            BrowserSettings(viewport={"width": -800, "height": 600})

    def test_invalid_timeout(self):
        """Test validation of timeout value."""
        with pytest.raises(ValueError, match="timeout must be a positive integer"):
            BrowserSettings(viewport={"width": 800, "height": 600}, timeout=-1000)


class TestBrowserActionResult:
    """Test cases for BrowserActionResult data model."""

    def test_valid_browser_action_result(self):
        """Test creating valid browser action result."""
        result = BrowserActionResult(
            success=True,
            screenshot="base64string",
            console_logs=["log1", "log2"],
            error=None
        )
        assert result.success is True
        assert result.screenshot == "base64string"
        assert result.console_logs == ["log1", "log2"]
        assert result.error is None

    def test_invalid_success_type(self):
        """Test validation of success field type."""
        with pytest.raises(ValueError, match="success must be a boolean"):
            BrowserActionResult(
                success="true",
                screenshot=None,
                console_logs=[]
            )

    def test_invalid_screenshot_type(self):
        """Test validation of screenshot field type."""
        with pytest.raises(ValueError, match="screenshot must be a string or None"):
            BrowserActionResult(
                success=True,
                screenshot=123,
                console_logs=[]
            )

    def test_invalid_console_logs_type(self):
        """Test validation of console_logs field type."""
        with pytest.raises(ValueError, match="console_logs must be a list"):
            BrowserActionResult(
                success=True,
                screenshot=None,
                console_logs="not a list"
            )

    def test_invalid_console_logs_content(self):
        """Test validation of console_logs content."""
        with pytest.raises(ValueError, match="all console_logs entries must be strings"):
            BrowserActionResult(
                success=True,
                screenshot=None,
                console_logs=["valid", 123, "also valid"]
            )

    def test_invalid_error_type(self):
        """Test validation of error field type."""
        with pytest.raises(ValueError, match="error must be a string or None"):
            BrowserActionResult(
                success=False,
                screenshot=None,
                console_logs=[],
                error=123
            )


class TestBrowserActionTool:
    """Test cases for BrowserActionTool class."""

    @pytest.fixture
    def browser_settings(self):
        """Fixture providing valid browser settings."""
        return BrowserSettings(
            viewport={"width": 900, "height": 600},
            headless=True,
            timeout=30000
        )

    @pytest.fixture
    def browser_tool(self, browser_settings):
        """Fixture providing browser action tool instance."""
        return BrowserActionTool(browser_settings)

    def test_browser_tool_initialization(self, browser_tool, browser_settings):
        """Test browser tool initialization."""
        assert browser_tool.browser_settings == browser_settings
        assert browser_tool.browser is None
        assert browser_tool.page is None
        assert browser_tool.playwright is None
        assert browser_tool.console_logs == []

    @pytest.mark.asyncio
    async def test_unknown_action(self, browser_tool):
        """Test handling of unknown action."""
        result = await browser_tool.execute_action("unknown_action")
        assert result.success is False
        assert "Unknown action: unknown_action" in result.error

    @pytest.mark.asyncio
    async def test_launch_without_url(self, browser_tool):
        """Test launch action without URL."""
        result = await browser_tool.execute_action("launch", url=None)
        assert result.success is False
        assert "URL is required for launch action" in result.error

    @pytest.mark.asyncio
    async def test_click_without_browser(self, browser_tool):
        """Test click action without browser launched."""
        result = await browser_tool.execute_action("click", coordinate="100,100")
        assert result.success is False
        assert "Browser not launched" in result.error

    @pytest.mark.asyncio
    async def test_click_without_coordinate(self, browser_tool):
        """Test click action without coordinate."""
        # Mock browser and page
        browser_tool.page = MagicMock()
        
        result = await browser_tool.execute_action("click", coordinate=None)
        assert result.success is False
        assert "Coordinate is required for click action" in result.error

    @pytest.mark.asyncio
    async def test_click_invalid_coordinate_format(self, browser_tool):
        """Test click action with invalid coordinate format."""
        browser_tool.page = MagicMock()
        
        result = await browser_tool.execute_action("click", coordinate="invalid")
        assert result.success is False
        assert "Invalid coordinate format" in result.error

    @pytest.mark.asyncio
    async def test_click_out_of_bounds(self, browser_tool):
        """Test click action with out-of-bounds coordinates."""
        browser_tool.page = MagicMock()
        
        result = await browser_tool.execute_action("click", coordinate="1000,1000")
        assert result.success is False
        assert "Coordinate out of viewport bounds" in result.error

    @pytest.mark.asyncio
    async def test_type_without_browser(self, browser_tool):
        """Test type action without browser launched."""
        result = await browser_tool.execute_action("type", text="hello")
        assert result.success is False
        assert "Browser not launched" in result.error

    @pytest.mark.asyncio
    async def test_type_without_text(self, browser_tool):
        """Test type action without text."""
        browser_tool.page = MagicMock()
        
        result = await browser_tool.execute_action("type", text=None)
        assert result.success is False
        assert "Text is required for type action" in result.error

    @pytest.mark.asyncio
    async def test_scroll_without_browser(self, browser_tool):
        """Test scroll actions without browser launched."""
        result = await browser_tool.execute_action("scroll_down")
        assert result.success is False
        assert "Browser not launched" in result.error

        result = await browser_tool.execute_action("scroll_up")
        assert result.success is False
        assert "Browser not launched" in result.error

    @pytest.mark.asyncio
    @patch('siada.tools.browser.browser_action_tool.ChromiumAutoInstaller')
    @patch('siada.tools.browser.browser_action_tool.async_playwright')
    async def test_successful_launch(self, mock_playwright, mock_installer_class, browser_tool):
        """Test successful browser launch."""
        # Mock the auto-installer
        mock_installer = AsyncMock()
        mock_installer.ensure_chromium_available = AsyncMock(return_value="/fake/chromium/path")
        mock_installer_class.return_value = mock_installer
        
        # Mock Playwright components
        mock_playwright_instance = AsyncMock()
        mock_browser = AsyncMock()
        mock_page = AsyncMock()
        
        mock_playwright.return_value.start = AsyncMock(return_value=mock_playwright_instance)
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_page.set_viewport_size = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.on = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")

        result = await browser_tool.execute_action("launch", url="https://www.baidu.com")
        
        assert result.success is True
        assert result.screenshot is not None
        assert isinstance(result.console_logs, list)
        
        # Verify auto-installer was called
        mock_installer.ensure_chromium_available.assert_called_once()
        
        # Verify browser setup calls
        mock_playwright_instance.chromium.launch.assert_called_once_with(
            executable_path="/fake/chromium/path",
            headless=True
        )
        mock_browser.new_page.assert_called_once()
        mock_page.set_viewport_size.assert_called_once_with({"width": 900, "height": 600})
        mock_page.goto.assert_called_once_with("https://www.baidu.com", wait_until="networkidle")

    @pytest.mark.asyncio
    async def test_successful_click(self, browser_tool):
        """Test successful click action."""
        # Mock page and mouse - need to include all methods used by enhanced click
        mock_page = AsyncMock()
        mock_mouse = AsyncMock()
        mock_page.mouse = mock_mouse
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")
        mock_page.evaluate = AsyncMock()  # For visual indicators
        mock_page.bring_to_front = AsyncMock()  # For enhanced functionality
        
        # Initialize cursor position for the tool
        browser_tool.cursor_initialized = True
        browser_tool.current_cursor_position = {"x": 400, "y": 300}
        browser_tool.page = mock_page

        result = await browser_tool.execute_action("click", coordinate="450,300")
        
        assert result.success is True
        assert result.screenshot is not None
        # Enhanced click uses mouse.down() and mouse.up() instead of click()
        mock_mouse.move.assert_called_with(450, 300)
        mock_mouse.down.assert_called_once()
        mock_mouse.up.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_type(self, browser_tool):
        """Test successful type action."""
        # Mock page and keyboard
        mock_page = AsyncMock()
        mock_keyboard = AsyncMock()
        mock_page.keyboard = mock_keyboard
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")
        mock_page.bring_to_front = AsyncMock()  # For enhanced functionality
        
        browser_tool.page = mock_page

        result = await browser_tool.execute_action("type", text="Hello World!")
        
        assert result.success is True
        assert result.screenshot is not None
        # Enhanced type uses delay parameter for better visual effect
        mock_keyboard.type.assert_called_once_with("Hello World!", delay=50)
        mock_page.wait_for_timeout.assert_called_once_with(500)

    @pytest.mark.asyncio
    async def test_successful_scroll_down(self, browser_tool):
        """Test successful scroll down action."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")
        mock_page.bring_to_front = AsyncMock()  # For enhanced functionality
        
        # Mock the scroll info response to indicate scrolling is possible
        mock_page.evaluate.return_value = {
            "pageHeight": 2000,
            "viewportHeight": 800,
            "currentScroll": 0,
            "canScrollDown": True
        }
        
        # Initialize cursor position for the tool
        browser_tool.cursor_initialized = True
        browser_tool.current_cursor_position = {"x": 400, "y": 300}
        browser_tool.page = mock_page

        result = await browser_tool.execute_action("scroll_down")
        
        assert result.success is True
        assert result.screenshot is not None
        # Enhanced scroll down calls evaluate multiple times (scroll info check + actual scroll)
        assert mock_page.evaluate.call_count >= 1
        mock_page.bring_to_front.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_scroll_up(self, browser_tool):
        """Test successful scroll up action."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot")
        mock_page.bring_to_front = AsyncMock()  # For enhanced functionality
        
        # Mock the scroll info response to indicate scrolling up is possible
        mock_page.evaluate.return_value = {
            "currentScroll": 400,
            "viewportHeight": 800,
            "canScrollUp": True
        }
        
        # Initialize cursor position for the tool
        browser_tool.cursor_initialized = True
        browser_tool.current_cursor_position = {"x": 400, "y": 300}
        browser_tool.page = mock_page

        result = await browser_tool.execute_action("scroll_up")
        
        assert result.success is True
        assert result.screenshot is not None
        # Enhanced scroll up calls evaluate multiple times (scroll info check + actual scroll)
        assert mock_page.evaluate.call_count >= 1
        mock_page.bring_to_front.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_close(self, browser_tool):
        """Test successful close action."""
        # Mock browser and playwright
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        
        browser_tool.browser = mock_browser
        browser_tool.playwright = mock_playwright

        result = await browser_tool.execute_action("close")
        
        assert result.success is True
        assert result.screenshot is None
        assert browser_tool.browser is None
        assert browser_tool.page is None
        assert browser_tool.playwright is None
        
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_error(self, browser_tool):
        """Test close action with error."""
        # Mock browser that raises exception
        mock_browser = AsyncMock()
        mock_browser.close.side_effect = Exception("Close failed")
        
        browser_tool.browser = mock_browser

        result = await browser_tool.execute_action("close")
        
        assert result.success is False
        assert "Close failed" in result.error

    def test_handle_console_log(self, browser_tool):
        """Test console log handling."""
        # Mock console message
        mock_msg = MagicMock()
        mock_msg.type = "log"
        mock_msg.text = "Test console message"
        
        browser_tool._handle_console_log(mock_msg)
        
        assert len(browser_tool.console_logs) == 1
        assert browser_tool.console_logs[0] == "[LOG] Test console message"

    @pytest.mark.asyncio
    async def test_take_screenshot_success(self, browser_tool):
        """Test successful screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")
        
        browser_tool.page = mock_page
        
        screenshot = await browser_tool._take_screenshot()
        
        assert screenshot == base64.b64encode(b"fake_screenshot_data").decode()
        mock_page.screenshot.assert_called_once_with(full_page=False)

    @pytest.mark.asyncio
    async def test_take_screenshot_no_page(self, browser_tool):
        """Test screenshot capture without page."""
        screenshot = await browser_tool._take_screenshot()
        assert screenshot == ""

    @pytest.mark.asyncio
    async def test_take_screenshot_error(self, browser_tool):
        """Test screenshot capture with error."""
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = Exception("Screenshot failed")
        
        browser_tool.page = mock_page
        
        screenshot = await browser_tool._take_screenshot()
        assert screenshot == ""

    @pytest.mark.asyncio
    async def test_save_screenshot_to_file(self, browser_tool, tmp_path):
        """Test saving screenshot to file functionality."""
        # Create a real PNG image using PIL
        from PIL import Image
        from io import BytesIO
        
        # Create a simple 10x10 white image
        image = Image.new('RGB', (10, 10), color='white')
        
        # Convert to PNG bytes
        png_buffer = BytesIO()
        image.save(png_buffer, format='PNG')
        fake_png_data = png_buffer.getvalue()
        
        # Mock page and screenshot data
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=fake_png_data)
        browser_tool.page = mock_page
        
        # Define save path using tmp_path fixture
        screenshot_path = tmp_path / "test_screenshot.jpg"
        
        # Call save method
        result = await browser_tool.save_screenshot(str(screenshot_path))
        
        # Verify result
        assert result is True
        assert screenshot_path.exists()
        
        # Verify file content (should be compressed/processed data, not raw)
        with open(screenshot_path, 'rb') as f:
            saved_data = f.read()
        
        # Verify saved data is not empty and has been processed
        assert len(saved_data) > 0
        # The saved data should be different from raw PNG data due to compression to JPEG
        assert saved_data != fake_png_data
        # Verify it's a JPEG file (starts with JPEG signature)
        assert saved_data.startswith(b'\xff\xd8\xff')

    @pytest.mark.asyncio
    async def test_save_screenshot_no_page(self, browser_tool, tmp_path):
        """Test saving screenshot when no page is available."""
        screenshot_path = tmp_path / "test_screenshot.jpg"
        
        result = await browser_tool.save_screenshot(str(screenshot_path))
        
        assert result is False
        assert not screenshot_path.exists()

    @pytest.mark.asyncio
    async def test_save_screenshot_capture_failed(self, browser_tool, tmp_path):
        """Test saving screenshot when capture fails."""
        # Mock page that fails to take screenshot
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = Exception("Screenshot failed")
        browser_tool.page = mock_page
        
        screenshot_path = tmp_path / "test_screenshot.jpg"
        
        result = await browser_tool.save_screenshot(str(screenshot_path))
        
        assert result is False
        assert not screenshot_path.exists()

    @pytest.mark.asyncio
    async def test_save_screenshot_directory_creation(self, browser_tool, tmp_path):
        """Test that save_screenshot creates directories if they don't exist."""
        # Mock page and screenshot data
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")
        browser_tool.page = mock_page
        
        # Define path with nested directories that don't exist
        screenshot_path = tmp_path / "nested" / "directories" / "test_screenshot.jpg"
        
        # Ensure the nested directories don't exist initially
        assert not screenshot_path.parent.exists()
        
        # Call save method
        result = await browser_tool.save_screenshot(str(screenshot_path))
        
        # Verify result and directory creation
        assert result is True
        assert screenshot_path.exists()
        assert screenshot_path.parent.exists()

    @pytest.mark.asyncio
    async def test_context_manager(self, browser_tool):
        """Test async context manager functionality."""
        mock_browser = AsyncMock()
        browser_tool.browser = mock_browser
        
        async with browser_tool as tool:
            assert tool is browser_tool
        
        # Verify close was called
        mock_browser.close.assert_called_once()


class TestIntegration:
    """Integration tests for browser automation."""

    @pytest.fixture
    def browser_settings(self):
        """Fixture providing browser settings for integration tests."""
        return BrowserSettings(
            viewport={"width": 800, "height": 600},
            headless=True,
            timeout=10000
        )

    @pytest.mark.asyncio
    async def test_action_sequence_validation(self, browser_settings):
        """Test that actions follow proper sequence requirements."""
        tool = BrowserActionTool(browser_settings)
        
        # Try to click before launching browser
        result = await tool.execute_action("click", coordinate="100,100")
        assert result.success is False
        assert "Browser not launched" in result.error
        
        # Try to type before launching browser
        result = await tool.execute_action("type", text="test")
        assert result.success is False
        assert "Browser not launched" in result.error

    @pytest.mark.asyncio
    async def test_coordinate_validation(self, browser_settings):
        """Test coordinate validation against viewport bounds."""
        tool = BrowserActionTool(browser_settings)
        tool.page = MagicMock()  # Mock page to bypass browser check
        
        # Test valid coordinates
        result = await tool.execute_action("click", coordinate="400,300")
        assert result.success is False  # Will fail due to mocked page, but coordinate validation passes
        assert "Coordinate out of viewport bounds" not in str(result.error)
        
        # Test out-of-bounds coordinates
        result = await tool.execute_action("click", coordinate="900,700")
        assert result.success is False
        assert "Coordinate out of viewport bounds" in result.error

    @pytest.mark.asyncio
    async def test_error_propagation(self, browser_settings):
        """Test that errors are properly propagated and logged."""
        tool = BrowserActionTool(browser_settings)
        
        # Test with invalid action
        result = await tool.execute_action("invalid_action")
        assert result.success is False
        assert result.error is not None
        assert "Unknown action" in result.error
        
        # Console logs should be preserved even on error
        assert isinstance(result.console_logs, list)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
