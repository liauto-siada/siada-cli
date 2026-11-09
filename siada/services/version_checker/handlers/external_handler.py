"""Public PyPI release handler."""

import os
import platform
import shlex
import sys
from typing import Optional, Tuple

from ..base import VersionHandler as BaseVersionHandler


class VersionHandler(BaseVersionHandler):
    """Query PyPI and upgrade through the active Python environment."""

    def __init__(self):
        self.pypi_url = "https://pypi.org/pypi/siada-cli/json"
        self.timeout = 5
        self.pip_args = ["siada-cli"]

    def get_version(self) -> Tuple[Optional[str], str]:
        try:
            import requests
            data = requests.get(self.pypi_url, timeout=self.timeout).json()
            return data["info"]["version"], "success"
        except Exception as error:
            return None, f"error: {error}"

    def get_install_message(self, latest_version: Optional[str] = None) -> str:
        return f"Newer version v{latest_version} is available." if latest_version else "Install latest version?"

    def _get_pip_command(self):
        return [sys.executable, "-m", "pip", "install", "--upgrade",
                "--upgrade-strategy", "only-if-needed", *self.pip_args]

    def get_manual_upgrade_hint(self) -> str:
        return shlex.join(self._get_pip_command())

    def install(self, io, latest_version: Optional[str] = None) -> bool:
        message = self.get_install_message(latest_version)
        docker_image = os.environ.get("SIADA_DOCKER_IMAGE")
        if docker_image:
            io.print_warning(f"{message} To upgrade, run: docker pull {docker_image}")
            return True
        io.print_warning(message)
        cmd = self._get_pip_command()
        if platform.system() == "Windows":
            io.print_info("Run this command to update:")
            print()
            print(shlex.join(cmd))
            return True
        if not io.confirm_ask("Run pip install?", default="y", subject=shlex.join(cmd)):
            return False
        success, output = self.run_command_with_spinner(cmd, "Installing")
        if success:
            io.print_info("Re-run siada-cli to use new version.")
            sys.exit()
        io.print_error(output)
        print()
        print("Install failed, try running this command manually:")
        print(shlex.join(cmd))
        return False


__all__ = ["VersionHandler"]