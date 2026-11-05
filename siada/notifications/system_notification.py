"""
Cross-platform system notification module.

Shows a desktop notification when the agent completes a task.
Supported platforms: macOS (osascript), Windows (PowerShell Toast), Linux (notify-send).
All calls are fire-and-forget (subprocess.Popen, no wait) and never raise.
"""

import platform
import shutil
import subprocess

from siada.foundation.logging import logger


def _escape_applescript(s: str) -> str:
    """Escape backslashes and double quotes for AppleScript string literals."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _escape_powershell(s: str) -> str:
    """Escape single quotes for PowerShell single-quoted string literals."""
    return s.replace("'", "''")


# ---------------------------------------------------------------------------
# Platform-specific notification
# ---------------------------------------------------------------------------

def _show_macos(title: str, message: str) -> None:
    script = (
        f'display notification "{_escape_applescript(message)}" '
        f'with title "{_escape_applescript(title)}" '
        f'sound name "Tink"'
    )
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _show_windows(title: str, message: str) -> None:
    safe_title = _escape_powershell(title)
    safe_message = _escape_powershell(message)
    # Use PowerShell's built-in AUMID so the toast notification shows without
    # registering a custom AppUserModelID. This is the standard approach for
    # scripts that want to display toast notifications on Windows 10+.
    powershell_aumid = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
    script = (
        f"$title = '{safe_title}'\n"
        f"$message = '{safe_message}'\n"
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, "
        "Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        "$xml.LoadXml('"
        '<toast><visual><binding template="ToastText02">'
        '<text id="1"></text><text id="2"></text>'
        "</binding></visual></toast>')\n"
        "$textNodes = $xml.GetElementsByTagName('text')\n"
        "$textNodes.Item(0).InnerText = $title\n"
        "$textNodes.Item(1).InnerText = $message\n"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
        f"[Windows.UI.Notifications.ToastNotificationManager]"
        f"::CreateToastNotifier('{powershell_aumid}').Show($toast)\n"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _show_linux(title: str, message: str) -> None:
    if not shutil.which("notify-send"):
        logger.debug("[notification] notify-send not found, skipping Linux notification")
        return
    subprocess.Popen(
        ["notify-send", title, message],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_completion_notification(title: str = "Siada", message: str = "任务已完成") -> None:
    """Show a system notification. Non-blocking, never raises."""
    try:
        system = platform.system()

        if system == "Darwin":
            _show_macos(title, message)
        elif system == "Windows":
            _show_windows(title, message)
        elif system == "Linux":
            _show_linux(title, message)
        else:
            logger.debug(f"[notification] Unsupported platform: {system}")
    except Exception as e:
        logger.debug(f"[notification] Failed to show notification: {e}")
