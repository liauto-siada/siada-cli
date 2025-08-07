"""
Chromium Auto-Installer for Browser Automation Tool.

This module provides automatic Chromium installation and detection functionality
across different platforms (Windows, macOS, Linux) using Playwright.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

import logging


class ChromiumAutoInstaller:
    """
    Automatic Chromium installer and detector.
    
    This class handles the detection of existing Chromium installations
    and automatic installation via Playwright when needed.
    """

    def __init__(self):
        """Initialize the installer with platform detection."""
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.logger = logging.getLogger(__name__)

    async def ensure_chromium_available(self) -> str:
        """
        Ensure Chromium is available, install if necessary.
        
        Returns:
            str: Path to the Chromium executable
            
        Raises:
            RuntimeError: If Chromium cannot be found or installed
        """
        self.logger.info("Checking for Chromium availability...")
        
        # 1. Try to find existing Chromium installations
        existing_path = self._find_existing_chromium()
        if existing_path:
            self.logger.info(f"Found existing Chromium: {existing_path}")
            return existing_path
        
        # 2. If not found, attempt automatic installation
        self.logger.info("Chromium not found, attempting automatic installation...")
        success = await self._auto_install_chromium()
        
        if success:
            # 3. Search again after installation
            installed_path = self._find_playwright_chromium()
            if installed_path:
                self.logger.info(f"Chromium installed successfully: {installed_path}")
                return installed_path
        
        # 4. Final fallback - provide helpful error message
        raise RuntimeError(
            "Unable to find or install Chromium browser. "
            "Please install Playwright and run 'playwright install chromium' manually."
        )

    def _find_existing_chromium(self) -> Optional[str]:
        """
        Find existing Chromium installations in order of preference.
        
        Search order:
        1. Environment variable CHROMIUM_BINARY_PATH
        2. Playwright-installed Chromium
        3. System-installed browsers (Chrome/Chromium)
        
        Returns:
            Optional[str]: Path to Chromium executable if found
        """
        # 1. Check environment variable first
        env_path = os.environ.get('CHROMIUM_BINARY_PATH')
        if env_path and self._is_valid_browser(env_path):
            self.logger.info(f"Using Chromium from environment variable: {env_path}")
            return env_path

        # 2. Check Playwright installation
        playwright_path = self._find_playwright_chromium()
        if playwright_path:
            self.logger.info(f"Found Playwright Chromium: {playwright_path}")
            return playwright_path

        # 3. Check system installations
        system_path = self._find_system_chromium()
        if system_path:
            self.logger.info(f"Found system Chromium: {system_path}")
            return system_path

        return None

    def _find_playwright_chromium(self) -> Optional[str]:
        """
        Find Playwright-installed Chromium.
        
        Returns:
            Optional[str]: Path to Playwright Chromium executable
        """
        if self.system == "windows":
            base_path = Path.home() / "AppData/Local/ms-playwright"
            executable_path = "chrome-win/chrome.exe"
        elif self.system == "darwin":  # macOS
            base_path = Path.home() / "Library/Caches/ms-playwright"
            executable_path = "chrome-mac/Chromium.app/Contents/MacOS/Chromium"
        else:  # Linux
            base_path = Path.home() / ".cache/ms-playwright"
            executable_path = "chrome-linux/chrome"

        if not base_path.exists():
            return None

        # Find the latest Chromium version
        chromium_dirs = list(base_path.glob("chromium-*"))
        if not chromium_dirs:
            return None

        # Sort by version and get the latest
        latest_dir = max(chromium_dirs, key=lambda x: x.name)
        chrome_path = latest_dir / executable_path

        if chrome_path.exists() and self._is_valid_browser(str(chrome_path)):
            return str(chrome_path)

        return None

    def _find_system_chromium(self) -> Optional[str]:
        """
        Find system-installed Chrome/Chromium.
        
        Returns:
            Optional[str]: Path to system Chromium executable
        """
        if self.system == "windows":
            possible_paths = [
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                "C:/Users/{}/AppData/Local/Google/Chrome/Application/chrome.exe".format(
                    os.environ.get('USERNAME', '')
                ),
            ]
        elif self.system == "darwin":  # macOS
            possible_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        else:  # Linux
            possible_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ]

        for path in possible_paths:
            if self._is_valid_browser(path):
                return path

        return None

    def _is_valid_browser(self, path: str) -> bool:
        """
        Check if the given path is a valid browser executable.
        
        Args:
            path: Path to check
            
        Returns:
            bool: True if valid browser executable
        """
        if not path:
            return False

        path_obj = Path(path)
        
        # Check if file exists and is executable
        if not path_obj.exists():
            return False

        # On macOS, check for .app bundle
        if self.system == "darwin" and path.endswith(".app/Contents/MacOS/Google Chrome"):
            return path_obj.is_file()
        elif self.system == "darwin" and path.endswith(".app/Contents/MacOS/Chromium"):
            return path_obj.is_file()

        # For other platforms, check if it's a regular file
        return path_obj.is_file()

    async def _auto_install_chromium(self) -> bool:
        """
        Automatically install Chromium using Playwright.
        
        Returns:
            bool: True if installation succeeded
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Installing Chromium (attempt {attempt + 1}/{max_retries})...")
                
                # Check if playwright command is available
                if not self._is_playwright_available():
                    self.logger.error("Playwright command not found. Please install: pip install playwright")
                    return False

                # Run playwright install chromium
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "playwright", "install", "chromium",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

                if process.returncode == 0:
                    self.logger.info("Chromium installation completed successfully")
                    return True
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    self.logger.warning(f"Installation attempt {attempt + 1} failed: {error_msg}")
                    
                    if attempt < max_retries - 1:
                        self.logger.info("Retrying installation...")
                        await asyncio.sleep(5)  # Wait before retry
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Installation attempt {attempt + 1} timed out")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    
            except Exception as e:
                self.logger.warning(f"Installation attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)

        self.logger.error("All installation attempts failed")
        return False

    def _is_playwright_available(self) -> bool:
        """
        Check if Playwright is available in the current environment.
        
        Returns:
            bool: True if Playwright is available
        """
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def get_installation_info(self) -> dict:
        """
        Get information about the current installation state.
        
        Returns:
            dict: Installation information
        """
        info = {
            "platform": self.system,
            "architecture": self.machine,
            "playwright_available": self._is_playwright_available(),
            "existing_chromium": self._find_existing_chromium(),
            "playwright_chromium": self._find_playwright_chromium(),
            "system_chromium": self._find_system_chromium(),
        }
        
        return info

    def print_installation_info(self):
        """Print detailed installation information for debugging."""
        info = self.get_installation_info()
        
        print("Chromium Installation Information:")
        print("=" * 40)
        print(f"Platform: {info['platform']} ({info['architecture']})")
        print(f"Playwright Available: {info['playwright_available']}")
        print(f"Existing Chromium: {info['existing_chromium'] or 'Not found'}")
        print(f"Playwright Chromium: {info['playwright_chromium'] or 'Not found'}")
        print(f"System Chromium: {info['system_chromium'] or 'Not found'}")
        
        if info['existing_chromium']:
            print(f"\n✅ Chromium is available at: {info['existing_chromium']}")
        else:
            print(f"\n❌ No Chromium found. Installation required.")
