"""
Browser automation tools for Siada.

This module provides browser automation capabilities using both Playwright
and BrowserGym, offering different approaches to browser automation:

- Playwright-based tools: Coordinate-based interactions with visual feedback
- BrowserGym-based tools: Element-based interactions using accessibility tree
"""

from .browser_action_tool import BrowserActionTool
from .browsergym_action_tool import BrowserGymActionTool
from .browsergym_env import BrowserGymEnv
from .models import BrowserSettings, BrowserActionResult, CompressionLevel, ScreenshotConfig
from .chromium_installer import ChromiumAutoInstaller

__all__ = [
    "BrowserActionTool",
    "BrowserGymActionTool", 
    "BrowserGymEnv",
    "BrowserSettings", 
    "BrowserActionResult",
    "CompressionLevel",
    "ScreenshotConfig",
    "ChromiumAutoInstaller"
]
