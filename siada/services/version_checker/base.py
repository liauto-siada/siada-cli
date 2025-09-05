from abc import ABC, abstractmethod
from typing import Tuple, Optional
import subprocess
import sys
import shlex
from siada.support.spinner import Spinner


class VersionHandler():
    """
    Template class for version handling
    Combines version checking and installation logic
    """
    
    @abstractmethod
    def get_version(self) -> Tuple[Optional[str], str]:
        """
        Get version from this source
        Returns: (version, source_name) where version is None if failed
        """
        pass
    
    @abstractmethod
    def install(self, io, latest_version: Optional[str] = None) -> bool:
        """
        Install the version
        Args:
            io: IO handler for user interaction
            latest_version: Version to install (optional)
        Returns:
            bool: True if installation succeeded
        """
        pass
    
    def get_install_message(self, latest_version: Optional[str] = None) -> str:
        """
        Get the installation prompt message (can be overridden)
        """
        if latest_version:
            return f"Newer version v{latest_version} is available."
        else:
            return "New version available."
    
    def run_command_with_spinner(self, cmd, description, shell=False):
        """
        Common utility method for running commands with spinner
        """
        print()
        if shell:
            print(f"{description}...")
            print(f"Command: {cmd}")
        else:
            print(f"{description}: {shlex.join(cmd)}")

        try:
            output = []
            if shell:
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    encoding=sys.stdout.encoding,
                    errors="replace",
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    encoding=sys.stdout.encoding,
                    errors="replace",
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
            else:
                print(f"Command failed with return code {return_code}")
                return False, output

        except Exception as e:
            print(f"\nError running command: {e}")
            return False, str(e)
