"""
Browser automation tools for Siada.

This module provides browser automation capabilities using BrowserGym,
offering element-based interactions using accessibility tree.
"""

from .browsergym_action_tool import browser_operate_by_gym, execute_action
from .browsergym_env import BrowserGymEnvManager
from .models import BrowserSettings, BrowserActionResult, CompressionLevel, ScreenshotConfig
from .chromium_installer import ChromiumAutoInstaller

__all__ = [
    "browser_operate_by_gym",
    "execute_action",
    "BrowserGymEnvManager",
    "BrowserSettings", 
    "BrowserActionResult",
    "CompressionLevel",
    "ScreenshotConfig",
    "ChromiumAutoInstaller"
]
