"""
Browser automation tools for Siada.

This module provides browser automation capabilities using BrowserGym,
offering element-based interactions using accessibility tree.

NOTE: All imports are lazy to avoid loading gymnasium/numpy at startup.
"""

__all__ = [
    "browser_operate_by_gym",
    "execute_action",
    "BrowserGymEnvManager",
    "BrowserSettings",
    "BrowserActionResult",
    "CompressionLevel",
    "ScreenshotConfig",
    "ChromiumAutoInstaller",
    "BrowserOperateResult",
]


def __getattr__(name: str):
    if name in ("browser_operate_by_gym", "execute_action"):
        from .browsergym_action_tool import browser_operate_by_gym, execute_action
        globals()["browser_operate_by_gym"] = browser_operate_by_gym
        globals()["execute_action"] = execute_action
        return globals()[name]
    if name == "BrowserGymEnvManager":
        from .browsergym_env import BrowserGymEnvManager
        globals()["BrowserGymEnvManager"] = BrowserGymEnvManager
        return BrowserGymEnvManager
    if name in ("BrowserSettings", "BrowserActionResult", "CompressionLevel", "ScreenshotConfig", "BrowserOperateResult"):
        from .models import BrowserSettings, BrowserActionResult, CompressionLevel, ScreenshotConfig, BrowserOperateResult
        globals()["BrowserSettings"] = BrowserSettings
        globals()["BrowserActionResult"] = BrowserActionResult
        globals()["CompressionLevel"] = CompressionLevel
        globals()["ScreenshotConfig"] = ScreenshotConfig
        globals()["BrowserOperateResult"] = BrowserOperateResult
        return globals()[name]
    if name == "ChromiumAutoInstaller":
        from .chromium_installer import ChromiumAutoInstaller
        globals()["ChromiumAutoInstaller"] = ChromiumAutoInstaller
        return ChromiumAutoInstaller
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
