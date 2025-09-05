"""
Browser automation tool using Playwright.

This module provides browser automation capabilities equivalent to the TypeScript version,
using Playwright for cross-browser automation with screenshot and console log capture.

The current tool is temporarily abandoned because the model cannot correctly identify the component coordinates. Use browser_action_tool instead
"""

from __future__ import annotations

import warnings

warnings.warn(
    "browser_action_tool module is deprecated and will be removed in a future version. "
    "Use browsergym_action_tool instead for better element-based interactions.",
    DeprecationWarning,
    stacklevel=2
)

import asyncio
import base64
import logging
import os
from typing import Optional

from agents import function_tool, RunContextWrapper
from playwright.async_api import async_playwright, Browser, Page, Playwright

from .models import BrowserActionResult, BrowserSettings, ImageResult, ScreenshotConfig, CompressionLevel
from .chromium_installer import ChromiumAutoInstaller
from ...foundation.code_agent_context import CodeAgentContext

# Browser viewport configuration
DEFAULT_VIEWPORT_WIDTH = 900
DEFAULT_VIEWPORT_HEIGHT = 600

BROWSER_OPERATE_DOC ="""
        Request to interact with a Playwright browser. Every action, except `close`, will be responded to with a screenshot of the browser's current state, along with any new console logs. You may only perform one browser action per message, and wait for the user's response including a screenshot and logs to determine the next action.
        - The sequence of actions **must always start with** launching the browser at a URL, and **must always end with** closing the browser. If you need to visit a new URL that is not possible to navigate to from the current webpage, you must first close the browser, then launch again at the new URL.
        - While the browser is active, only the `browser_operate` tool can be used. No other tools should be called during this time. You may proceed to use other tools only after closing the browser. For example if you run into an error and need to fix a file, you must close the browser, then use other tools to make the necessary changes, then re-launch the browser to verify the result.
        - The browser window has a resolution of **{DEFAULT_VIEWPORT_WIDTH}x{DEFAULT_VIEWPORT_HEIGHT}** pixels. When performing any click actions, ensure the coordinates are within this resolution range.
        - Before clicking on any elements such as icons, links, or buttons, you must consult the provided screenshot of the page to determine the coordinates of the element. The click should be targeted at the **center of the element**, not on its edges.
        - Except for close, after each action you must extract the information you need from the image, because to avoid an overly long context window, each image will be deleted after you have viewed it.
        
        Args:
            action (str): The action type to execute. Available actions:
                
                **"launch"** - Launch a new Playwright-controlled browser instance at the specified URL. This **must always be the first action**.
                             - Use with the `url` parameter to provide the URL.
                             - Ensure the URL is valid and includes the appropriate protocol (e.g. http://localhost:8000/page, file:///path/to/file.html, etc.)
                
                **"click"** - Click at a specific x,y coordinate.
                            - Use with the `coordinate` parameter to specify the location.
                            - Always click in the center of an element (icon, button, link, etc.) based on coordinates derived from a screenshot.
                
                **"type"** - Type a string of text on the keyboard. You might use this after clicking on a text field to input text.
                           - Use with the `text` parameter to provide the string to type.
                
                **"scroll_down"** - Scroll down by one page height
                
                **"scroll_up"** - Scroll up by one page height  
                
                **"close"** - Close browser and cleanup resources
                    
            
            url (Optional[str]): Target website URL. Required for "launch" action only.
            coordinate (Optional[str]): Click coordinates in "x,y" format. Required for "click" action only.
            text (Optional[str]): Text content to type. Required for "type" action only.
        """

class BrowserActionTool:
    """Browser automation tool class.
    
    Provides browser automation capabilities using Playwright, including:
    - Browser launching and navigation
    - Click operations at specific coordinates
    - Text input simulation
    - Page scrolling
    - Screenshot capture
    - Console log monitoring
    """

    def __init__(self, browser_settings: BrowserSettings):
        """Initialize the browser action tool.
        
        Args:
            browser_settings: Configuration settings for the browser
        """
        self.browser_settings = browser_settings
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright: Optional[Playwright] = None
        self.console_logs: list[str] = []
        self.logger = logging.getLogger(__name__)
        
        # 光标位置管理
        self.current_cursor_position = {"x": 0, "y": 0}
        self.cursor_initialized = False

    async def execute_action(
        self, 
        action: str, 
        url: Optional[str] = None, 
        coordinate: Optional[str] = None, 
        text: Optional[str] = None
    ) -> BrowserActionResult:
        """
        @BROWSER_OPERATE_DOC
        """
        try:
            self.logger.info(f"Executing browser action: {action}")
            
            if action == "launch":
                return await self._launch(url)
            elif action == "click":
                return await self._click(coordinate)
            elif action == "type":
                return await self._type(text)
            elif action == "scroll_down":
                return await self._scroll_down()
            elif action == "scroll_up":
                return await self._scroll_up()
            elif action == "close":
                return await self._close()
            else:
                raise ValueError(f"Unknown action: {action}")
                
        except Exception as e:
            self.logger.error(f"Browser action failed: {str(e)}")
            return BrowserActionResult(
                success=False,
                screenshot=None,
                console_logs=self.console_logs.copy(),
                error=str(e)
            )

    async def _launch(self, url: str) -> BrowserActionResult:
        """Launch browser and navigate to the specified URL.
        
        Args:
            url: The URL to navigate to
            
        Returns:
            BrowserActionResult: The result of the launch operation
        """
        if not url:
            raise ValueError("URL is required for launch action")
        
        # Ensure Chromium is available (auto-install if needed)
        installer = ChromiumAutoInstaller()
        chromium_path = await installer.ensure_chromium_available()
        
        # Start Playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            executable_path=chromium_path,
            headless=self.browser_settings.headless
        )
        
        # Create new page
        self.page = await self.browser.new_page()
        
        # Set viewport size
        await self.page.set_viewport_size(self.browser_settings.viewport)
        
        # Set timeout
        self.page.set_default_timeout(self.browser_settings.timeout)
        
        # Listen for console logs
        self.page.on("console", self._handle_console_log)
        
        # Navigate to URL
        await self.page.goto(url, wait_until="networkidle")  # 等待网络空闲，确保页面完全加载
        
        # 等待页面完全渲染
        await self.page.wait_for_timeout(1000)
        
        # 初始化光标位置到页面中心
        await self._initialize_cursor_position()
        
        # 额外等待，确保光标指示器显示
        await self.page.wait_for_timeout(500)
        
        # Take screenshot
        screenshot = await self._take_screenshot()
        
        return BrowserActionResult(
            success=True,
            screenshot=screenshot,
            console_logs=self.console_logs.copy()
        )

    async def _click(self, coordinate: str) -> BrowserActionResult:
        """Click at the specified coordinates with visual indicators and smooth movement.
        
        Args:
            coordinate: Coordinates in "x,y" format
            
        Returns:
            BrowserActionResult: The result of the click operation
        """
        if not self.page:
            raise RuntimeError("Browser not launched")
            
        if not coordinate:
            raise ValueError("Coordinate is required for click action")
            
        try:
            x, y = map(int, coordinate.split(","))
        except ValueError:
            raise ValueError("Invalid coordinate format. Expected 'x,y'")
            
        # Validate coordinate bounds
        viewport = self.browser_settings.viewport
        if not (0 <= x <= viewport["width"] and 0 <= y <= viewport["height"]):
            raise ValueError(f"Coordinate out of viewport bounds: {coordinate}")
        
        # Bring browser window to front
        await self.page.bring_to_front()
        
        # 获取当前光标位置
        current_x = self.current_cursor_position["x"] if self.cursor_initialized else viewport["width"] // 2
        current_y = self.current_cursor_position["y"] if self.cursor_initialized else viewport["height"] // 2
        
        # 添加光标移动轨迹动画
        await self._animate_cursor_movement(current_x, current_y, x, y)
        
        # Add visual indicator at click position
        await self._add_click_indicator(x, y)
        
        # Move actual mouse to target position
        await self.page.mouse.move(x, y)
        await self.page.wait_for_timeout(200)
        
        # Perform click with mouse down and up for visibility
        await self.page.mouse.down()
        await self.page.wait_for_timeout(100)  # Brief hold for visual feedback
        await self.page.mouse.up()
        
        # 更新光标位置状态
        self.current_cursor_position = {"x": x, "y": y}
        self.cursor_initialized = True
        
        # Wait for page to stabilize
        await self.page.wait_for_timeout(800)
        
        # Remove click indicator
        await self._remove_click_indicator()
        
        # 添加新位置的持久光标指示器（解决双光标问题）
        await self._add_persistent_cursor_indicator(x, y)
        
        screenshot = await self._take_screenshot()
        return BrowserActionResult(
            success=True,
            screenshot=screenshot,
            console_logs=self.console_logs.copy()
        )

    async def _type(self, text: str) -> BrowserActionResult:
        """Type text using keyboard simulation with enhanced visibility.
        
        Args:
            text: The text to type
            
        Returns:
            BrowserActionResult: The result of the type operation
        """
        if not self.page:
            raise RuntimeError("Browser not launched")
            
        if not text:
            raise ValueError("Text is required for type action")
        
        # Bring browser window to front
        await self.page.bring_to_front()
        
        # Type text with delay for better visibility
        await self.page.keyboard.type(text, delay=50)  # 50ms delay between keystrokes
        
        # Wait longer for input completion and DOM updates
        await self.page.wait_for_timeout(500)
        
        screenshot = await self._take_screenshot()
        return BrowserActionResult(
            success=True,
            screenshot=screenshot,
            console_logs=self.console_logs.copy()
        )

    async def _scroll_down(self) -> BrowserActionResult:
        """Scroll down by one page height.
        
        Returns:
            BrowserActionResult: The result of the scroll operation
        """
        if not self.page:
            raise RuntimeError("Browser not launched")
        
        # Bring browser window to front
        await self.page.bring_to_front()
        
        try:
            # First check if page is scrollable and ensure there's content to scroll
            scroll_info = await self.page.evaluate("""
                () => {
                    const body = document.body;
                    const html = document.documentElement;
                    
                    // Get page dimensions
                    const pageHeight = Math.max(body.scrollHeight, body.offsetHeight, 
                                               html.clientHeight, html.scrollHeight, html.offsetHeight);
                    const viewportHeight = window.innerHeight;
                    const currentScroll = window.pageYOffset;
                    const maxScroll = pageHeight - viewportHeight;
                    
                    // If page is too short, add some content to make it scrollable
                    if (pageHeight <= viewportHeight * 1.5) {
                        const spacer = document.createElement('div');
                        spacer.style.height = (viewportHeight * 3) + 'px';
                        spacer.style.background = 'linear-gradient(to bottom, transparent, #f0f0f0, transparent)';
                        spacer.style.textAlign = 'center';
                        spacer.style.paddingTop = viewportHeight + 'px';
                        spacer.innerHTML = '<p style="color: #666; font-size: 18px;">↓ 滚动测试内容区域 ↓</p>';
                        spacer.id = 'siada-scroll-spacer';
                        
                        // Remove existing spacer if any
                        const existing = document.getElementById('siada-scroll-spacer');
                        if (existing) existing.remove();
                        
                        body.appendChild(spacer);
                    }
                    
                    return {
                        pageHeight: Math.max(body.scrollHeight, html.scrollHeight),
                        viewportHeight: viewportHeight,
                        currentScroll: currentScroll,
                        canScrollDown: currentScroll < (Math.max(body.scrollHeight, html.scrollHeight) - viewportHeight - 10)
                    };
                }
            """)
            
            self.logger.debug(f"Scroll down info: {scroll_info}")
            
            if scroll_info["canScrollDown"]:
                # Perform smooth scroll down
                await self.page.evaluate("""
                    () => {
                        const scrollAmount = window.innerHeight;
                        window.scrollBy({
                            top: scrollAmount,
                            left: 0,
                            behavior: 'smooth'
                        });
                    }
                """)
                
                # Wait for smooth scroll to complete
                await self.page.wait_for_timeout(600)
                
                self.logger.debug("Scroll down executed successfully")
            else:
                self.logger.debug("Cannot scroll down - already at bottom or no scrollable content")
            
        except Exception as e:
            self.logger.error(f"Scroll down failed: {e}")
            # Fallback to basic scroll
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.page.wait_for_timeout(300)
        
        # 滚动后保持光标位置（保持原有逻辑不变）
        await self._ensure_cursor_position()
        
        screenshot = await self._take_screenshot()
        return BrowserActionResult(
            success=True,
            screenshot=screenshot,
            console_logs=self.console_logs.copy()
        )

    async def _scroll_up(self) -> BrowserActionResult:
        """Scroll up by one page height.
        
        Returns:
            BrowserActionResult: The result of the scroll operation
        """
        if not self.page:
            raise RuntimeError("Browser not launched")
        
        # Bring browser window to front
        await self.page.bring_to_front()
        
        try:
            # Check if we can scroll up
            scroll_info = await self.page.evaluate("""
                () => {
                    const currentScroll = window.pageYOffset;
                    const viewportHeight = window.innerHeight;
                    
                    return {
                        currentScroll: currentScroll,
                        viewportHeight: viewportHeight,
                        canScrollUp: currentScroll > 0
                    };
                }
            """)
            
            self.logger.debug(f"Scroll up info: {scroll_info}")
            
            if scroll_info["canScrollUp"]:
                # Perform smooth scroll up
                await self.page.evaluate("""
                    () => {
                        const scrollAmount = -window.innerHeight;
                        window.scrollBy({
                            top: scrollAmount,
                            left: 0,
                            behavior: 'smooth'
                        });
                    }
                """)
                
                # Wait for smooth scroll to complete
                await self.page.wait_for_timeout(600)
                
                self.logger.debug("Scroll up executed successfully")
            else:
                self.logger.debug("Cannot scroll up - already at top")
            
        except Exception as e:
            self.logger.error(f"Scroll up failed: {e}")
            # Fallback to basic scroll
            await self.page.evaluate("window.scrollBy(0, -window.innerHeight)")
            await self.page.wait_for_timeout(300)
        
        # 滚动后保持光标位置（保持原有逻辑不变）
        await self._ensure_cursor_position()
        
        screenshot = await self._take_screenshot()
        return BrowserActionResult(
            success=True,
            screenshot=screenshot,
            console_logs=self.console_logs.copy()
        )

    async def _close(self) -> BrowserActionResult:
        """Close the browser.
        
        Returns:
            BrowserActionResult: The result of the close operation
        """
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
                
            # Clean up state
            self.browser = None
            self.page = None
            self.playwright = None
            
            return BrowserActionResult(
                success=True,
                screenshot=None,
                console_logs=self.console_logs.copy()
            )
        except Exception as e:
            self.logger.error(f"Error closing browser: {str(e)}")
            return BrowserActionResult(
                success=False,
                screenshot=None,
                console_logs=self.console_logs.copy(),
                error=str(e)
            )

    async def save_screenshot(self, file_path: str) -> bool:
        """Save screenshot to specified file path.
        
        Args:
            file_path: File path to save the screenshot
            
        Returns:
            bool: True if screenshot was saved successfully, False otherwise
        """
        try:
            # Call existing _take_screenshot method to get base64 data
            screenshot_base64 = await self._take_screenshot()
            
            if not screenshot_base64:
                self.logger.error("Failed to capture screenshot")
                return False
            
            # Decode base64 data to bytes
            screenshot_bytes = base64.b64decode(screenshot_base64)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save to file
            with open(file_path, 'wb') as f:
                f.write(screenshot_bytes)
            
            self.logger.info(f"Screenshot saved to: {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {str(e)}")
            return False

    async def _take_screenshot(self) -> str:
        """Take a screenshot using Playwright's native compression and return base64 encoded string.
        
        Returns:
            str: Base64 encoded screenshot, empty string if failed
        """
        if not self.page:
            return ""
            
        try:
            # Get screenshot configuration
            config = self.browser_settings.screenshot_config
            optimized_settings = config.get_optimized_settings()
            
            # Prepare Playwright screenshot parameters
            screenshot_params = {
                "full_page": False,
                "type": optimized_settings["format"]
            }
            
            # Add quality parameter for JPEG format
            if optimized_settings["format"] == "jpeg":
                screenshot_params["quality"] = optimized_settings["jpeg_quality"]
            
            # Take screenshot directly in target format
            screenshot_bytes = await self.page.screenshot(**screenshot_params)
            
            # Convert bytes to base64 string (no need for .decode() as we return str)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode()
            
            self.logger.debug(f"Screenshot captured in {screenshot_params['type'].upper()} format (requested: {optimized_settings['format'].upper()})")
            
            return screenshot_base64
            
        except Exception as e:
            self.logger.error(f"Screenshot failed: {str(e)}")
            return ""


    async def _add_click_indicator(self, x: int, y: int):
        """Add a visual indicator at the click position.
        
        Args:
            x: X coordinate
            y: Y coordinate
        """
        if not self.page:
            return
            
        try:
            # Add a red circle indicator at the click position
            await self.page.evaluate(f"""
                (() => {{
                    const indicator = document.createElement('div');
                    indicator.id = 'siada-click-indicator';
                    indicator.style.cssText = `
                        position: fixed;
                        left: {x - 10}px;
                        top: {y - 10}px;
                        width: 20px;
                        height: 20px;
                        border: 3px solid red;
                        border-radius: 50%;
                        background: rgba(255, 0, 0, 0.3);
                        z-index: 999999;
                        pointer-events: none;
                        animation: pulse 0.5s ease-in-out infinite alternate;
                    `;
                    
                    // Add pulse animation
                    const style = document.createElement('style');
                    style.textContent = `
                        @keyframes pulse {{
                            from {{ transform: scale(1); opacity: 0.7; }}
                            to {{ transform: scale(1.2); opacity: 1; }}
                        }}
                    `;
                    document.head.appendChild(style);
                    document.body.appendChild(indicator);
                }})();
            """)
        except Exception as e:
            self.logger.debug(f"Failed to add click indicator: {e}")

    async def _remove_click_indicator(self):
        """Remove the visual click indicator."""
        if not self.page:
            return
            
        try:
            await self.page.evaluate("""
                (() => {
                    const indicator = document.getElementById('siada-click-indicator');
                    if (indicator) {
                        indicator.remove();
                    }
                })();
            """)
        except Exception as e:
            self.logger.debug(f"Failed to remove click indicator: {e}")

    def _handle_console_log(self, msg):
        """Handle console log messages from the browser.
        
        Args:
            msg: Console message from Playwright
        """
        log_entry = f"[{msg.type.upper()}] {msg.text}"
        self.console_logs.append(log_entry)
        self.logger.debug(f"Console: {log_entry}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def _initialize_cursor_position(self):
        """初始化光标位置到页面中心."""
        if not self.page:
            return
            
        try:
            # 将光标移动到页面中心
            viewport = self.browser_settings.viewport
            center_x = viewport["width"] // 2
            center_y = viewport["height"] // 2
            
            await self.page.mouse.move(center_x, center_y)
            
            # 更新光标位置状态
            self.current_cursor_position = {"x": center_x, "y": center_y}
            self.cursor_initialized = True
            
            # 立即添加初始的持久光标指示器
            await self._add_persistent_cursor_indicator(center_x, center_y)
            
            self.logger.debug(f"Cursor initialized at center: ({center_x}, {center_y})")
            
        except Exception as e:
            self.logger.debug(f"Failed to initialize cursor position: {e}")

    async def _ensure_cursor_position(self):
        """确保光标保持在当前位置（光标常驻功能）."""
        if not self.page or not self.cursor_initialized:
            return
            
        try:
            # 重新将光标移动到记录的位置
            x = self.current_cursor_position["x"]
            y = self.current_cursor_position["y"]
            
            await self.page.mouse.move(x, y)
            
            # 添加持久的光标指示器，让用户能够清楚看到光标位置
            await self._add_persistent_cursor_indicator(x, y)
            
            self.logger.debug(f"Cursor position maintained at: ({x}, {y})")
            
        except Exception as e:
            self.logger.debug(f"Failed to maintain cursor position: {e}")

    async def _add_persistent_cursor_indicator(self, x: int, y: int):
        """添加持久的光标指示器，模拟真实光标常驻效果."""
        if not self.page:
            return
            
        try:
            await self.page.evaluate(f"""
                (() => {{
                    // 移除旧的光标指示器
                    const oldCursor = document.getElementById('siada-persistent-cursor');
                    if (oldCursor) oldCursor.remove();
                    
                    // 创建新的持久光标指示器
                    const cursor = document.createElement('div');
                    cursor.id = 'siada-persistent-cursor';
                    cursor.style.cssText = `
                        position: fixed;
                        left: {x - 3}px;
                        top: {y - 3}px;
                        width: 6px;
                        height: 6px;
                        background: #007bff;
                        border: 1px solid white;
                        border-radius: 50%;
                        z-index: 999998;
                        pointer-events: none;
                        box-shadow: 0 0 3px rgba(0,123,255,0.6), 0 0 6px rgba(0,123,255,0.4);
                        animation: cursorPulse 2s infinite;
                    `;
                    
                    // 添加脉动动画样式
                    let style = document.getElementById('siada-cursor-style');
                    if (!style) {{
                        style = document.createElement('style');
                        style.id = 'siada-cursor-style';
                        style.textContent = `
                            @keyframes cursorPulse {{
                                0%, 100% {{ 
                                    transform: scale(1); 
                                    opacity: 0.8; 
                                }}
                                50% {{ 
                                    transform: scale(1.3); 
                                    opacity: 1; 
                                }}
                            }}
                        `;
                        document.head.appendChild(style);
                    }}
                    
                    document.body.appendChild(cursor);
                    console.log('持久光标指示器已添加到位置: ({x}, {y})');
                }})();
            """)
        except Exception as e:
            self.logger.debug(f"Failed to add persistent cursor indicator: {e}")

    async def _animate_cursor_movement(self, from_x: int, from_y: int, to_x: int, to_y: int):
        """添加光标移动轨迹动画，从A点滑动到B点."""
        if not self.page:
            return
            
        try:
            # 计算移动距离和时间
            distance = ((to_x - from_x) ** 2 + (to_y - from_y) ** 2) ** 0.5
            duration = min(max(distance / 200, 0.3), 1.5)  # 基于距离计算持续时间，0.3-1.5秒
            
            await self.page.evaluate(f"""
                (() => {{
                    // 移除旧的移动轨迹
                    const oldTrail = document.getElementById('siada-cursor-trail');
                    if (oldTrail) oldTrail.remove();
                    
                    // 创建移动中的光标指示器
                    const movingCursor = document.createElement('div');
                    movingCursor.id = 'siada-cursor-trail';
                    movingCursor.style.cssText = `
                        position: fixed;
                        left: {from_x - 4}px;
                        top: {from_y - 4}px;
                        width: 8px;
                        height: 8px;
                        background: #28a745;
                        border: 2px solid white;
                        border-radius: 50%;
                        z-index: 999997;
                        pointer-events: none;
                        box-shadow: 0 0 4px rgba(40,167,69,0.8);
                        transition: all {duration}s cubic-bezier(0.25, 0.46, 0.45, 0.94);
                    `;
                    
                    document.body.appendChild(movingCursor);
                    
                    // 强制重新计算样式，然后开始动画
                    requestAnimationFrame(() => {{
                        movingCursor.style.left = '{to_x - 4}px';
                        movingCursor.style.top = '{to_y - 4}px';
                    }});
                    
                    // 动画完成后移除移动指示器
                    setTimeout(() => {{
                        if (movingCursor && movingCursor.parentNode) {{
                            movingCursor.remove();
                        }}
                    }}, {duration * 1000 + 100});
                    
                    console.log('光标移动轨迹动画开始: ({from_x}, {from_y}) -> ({to_x}, {to_y})');
                }})();
            """)
            
            # 等待动画完成
            await self.page.wait_for_timeout(int(duration * 1000))
            
        except Exception as e:
            self.logger.debug(f"Failed to animate cursor movement: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self._close()

@function_tool(
    name_override="browser_operate", description_override=BROWSER_OPERATE_DOC
)
async def browser_operate(
        context: RunContextWrapper[CodeAgentContext],
        action: str,
        url: Optional[str] = None,
        coordinate: Optional[str] = None,
        text: Optional[str] = None
    ) -> str:
    import json
    import weakref
    import asyncio
    from dataclasses import asdict

    # Get or create browser tool instance from context to maintain state across calls
    if not hasattr(context.context, '_browser_tool'):
        settings = BrowserSettings(
            viewport={"width": DEFAULT_VIEWPORT_WIDTH, "height": DEFAULT_VIEWPORT_HEIGHT},
            headless=False,
            timeout=30000
        )
        context.context._browser_tool = BrowserActionTool(settings)
        
        # Register cleanup function to ensure browser resources are freed when context is destroyed
        def cleanup_browser():
            if hasattr(context.context, '_browser_tool') and context.context._browser_tool:
                try:
                    # Convert async cleanup to sync for finalization
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(context.context._browser_tool._close())
                    loop.close()
                except Exception:
                    pass  # Ignore cleanup errors during finalization
        
        # Use weakref to register cleanup callback that runs when context is garbage collected
        weakref.finalize(context.context, cleanup_browser)
    
    tool = context.context._browser_tool
    
    try:
        browser_action_result = await tool.execute_action(action, url, coordinate, text)
        
        # If close action is successful, remove the tool instance from context
        if action == "close" and browser_action_result.success:
            if hasattr(context.context, '_browser_tool'):
                delattr(context.context, '_browser_tool')
                
    except Exception as e:
        # If browser operation fails (except for "Browser not launched" which is expected),
        # the browser instance might be corrupted, so remove it from context
        if "Browser not launched" not in str(e):
            if hasattr(context.context, '_browser_tool'):
                delattr(context.context, '_browser_tool')
        raise
    
    # Convert BrowserActionResult to ImageResult and then to JSON string
    if browser_action_result.screenshot and browser_action_result.success:
        # Get the image format from screenshot config
        settings = tool.browser_settings
        image_format = settings.screenshot_config.get_optimized_settings()["format"]
        # Create ImageResult from screenshot base64 data with correct format
        image_result = ImageResult.from_base64(browser_action_result.screenshot, image_format)
        return json.dumps(asdict(image_result))
    else:
        # Handle cases where screenshot is None or operation failed
        # Return empty base64 data for failed operations or close action
        image_result = ImageResult.from_base64("")
        return json.dumps(asdict(image_result))
