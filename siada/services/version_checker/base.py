"""VersionHandler base class.

This is the public contract shared by version handlers: a handler reports the
newest version it can see and can install an upgrade. Handlers without any
version source of their own stay inert — ``get_version()`` returns no version
and ``install()`` does nothing — so callers never need a private handler.
"""

import shlex
import subprocess
import sys
from abc import abstractmethod
from typing import Optional, Tuple

from siada.support.spinner import Spinner


class VersionHandler:
    """Contract for a source of release information.

    Subclasses override ``get_version``/``install``; the remaining helpers have
    inert default implementations.
    """

    @abstractmethod
    def get_version(self) -> Tuple[Optional[str], str]:
        pass

    @abstractmethod
    def install(self, io, latest_version: Optional[str] = None) -> bool:
        pass

    def get_install_message(self, latest_version: Optional[str] = None) -> str:
        if latest_version:
            return f"Newer version v{latest_version} is available."
        return "New version available."

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
            popen_kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding=sys.stdout.encoding,
                errors="replace",
            )
            process = subprocess.Popen(cmd, shell=shell, **popen_kwargs)
            spinner = Spinner(description)
            while True:
                char = process.stdout.read(1)  # type: ignore[union-attr]
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
            else:
                print(f"Command failed with return code {return_code}")
                return False, output
        except Exception as e:
            print(f"\nError running command: {e}")
            return False, str(e)


__all__ = ["VersionHandler"]
