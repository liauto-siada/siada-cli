"""
External version handler.
Delegates to siada.internal.services.version_checker.handlers.external_handler when available.
"""
try:
    from siada.internal.services.version_checker.handlers.external_handler import VersionHandler
except ImportError:
    # Internal module not available — define a minimal local implementation.
    import sys
    import os
    import platform
    import shlex
    from typing import Tuple, Optional
    from ..base import VersionHandler as BaseVersionHandler  # type: ignore[no-redef]

    class VersionHandler(BaseVersionHandler):  # type: ignore[no-redef]
        def __init__(self):
            self.pypi_url = "https://pypi.org/pypi/siada-cli/json"
            self.timeout = 5
            self.pip_args = ["siada-cli"]

        def get_version(self) -> Tuple[Optional[str], str]:
            try:
                import requests
                response = requests.get(self.pypi_url, timeout=self.timeout)
                data = response.json()
                return data["info"]["version"], "success"
            except Exception as e:
                return None, f"error: {e}"

        def get_install_message(self, latest_version: Optional[str] = None) -> str:
            if latest_version:
                return f"Newer version v{latest_version} is available."
            return "Install latest version?"

        def _get_pip_command(self):
            return [sys.executable, "-m", "pip", "install", "--upgrade",
                    "--upgrade-strategy", "only-if-needed"] + self.pip_args

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
                return True
            else:
                io.print_error(output)
                print()
                print("Install failed, try running this command manually:")
                print(shlex.join(cmd))
                return False

__all__ = ["VersionHandler"]
