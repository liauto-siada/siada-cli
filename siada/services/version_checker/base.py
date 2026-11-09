"""Shared public version handler contract."""

import shlex
import subprocess
import sys
from abc import abstractmethod
from typing import Optional, Tuple

from siada.support.spinner import Spinner


class VersionHandler:
    """Report a version and install an explicitly requested upgrade."""

    @abstractmethod
    def get_version(self) -> Tuple[Optional[str], str]:
        pass

    @abstractmethod
    def install(self, io, latest_version: Optional[str] = None) -> bool:
        pass

    def get_install_message(self, latest_version: Optional[str] = None) -> str:
        return f"Newer version v{latest_version} is available." if latest_version else "New version available."

    def get_manual_upgrade_hint(self) -> str:
        return "siada-cli --upgrade"

    def run_command_with_spinner(self, cmd, description, shell=False):
        print()
        if shell:
            print(f"{description}...")
            print(f"Command: {cmd}")
        else:
            print(f"{description}: {shlex.join(cmd)}")
        try:
            output = []
            process = subprocess.Popen(
                cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True,
                encoding=sys.stdout.encoding, errors="replace",
            )
            spinner = Spinner(description)
            while True:
                char = process.stdout.read(1)
                if not char:
                    break
                output.append(char)
                spinner.step()
            spinner.end()
            return_code = process.wait()
            output = "".join(output)
            if return_code == 0:
                print("Command completed successfully.")
                print()
                return True, output
            print(f"Command failed with return code {return_code}")
            return False, output
        except Exception as error:
            print(f"\nError running command: {error}")
            return False, str(error)


__all__ = ["VersionHandler"]