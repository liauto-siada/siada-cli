
import shutil
import platform


class NotificationCommandUtil:
    """A utility class for handling notification commands."""

    NOTIFICATION_MESSAGE = "Siada is waiting for your input"

    @staticmethod
    def get_default_notification_command():
        """Return a default notification command based on the operating system."""
        system = platform.system()

        if system == "Darwin":  # macOS
            # Check for terminal-notifier first
            if shutil.which("terminal-notifier"):
                return f"terminal-notifier -title 'Siada' -message '{NotificationCommandUtil.NOTIFICATION_MESSAGE}'"
            # Fall back to osascript
            return f'osascript -e \'display notification "{NotificationCommandUtil.NOTIFICATION_MESSAGE}" with title "Siada"\''
        elif system == "Linux":
            # Check for common Linux notification tools
            for cmd in ["notify-send", "zenity"]:
                if shutil.which(cmd):
                    if cmd == "notify-send":
                        return f"notify-send 'Siada' '{NotificationCommandUtil.NOTIFICATION_MESSAGE}'"
                    elif cmd == "zenity":
                        return f"zenity --notification --text='{NotificationCommandUtil.NOTIFICATION_MESSAGE}'"
            return None  # No known notification tool found
        elif system == "Windows":
            # PowerShell notification
            return (
                "powershell -command"
                " \"[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                f" [System.Windows.Forms.MessageBox]::Show('{NotificationCommandUtil.NOTIFICATION_MESSAGE}',"
                " 'Siada')\""
            )

        return None  # Unknown system 