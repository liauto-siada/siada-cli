"""
VersionHandler base class.
Delegates to siada.internal.services.version_checker.base when available.
"""
try:
    from siada.internal.services.version_checker.base import VersionHandler
except ImportError:
    # Internal module not available — define a minimal local base class.
    from abc import abstractmethod
    from typing import Tuple, Optional
    import subprocess
    import sys
    import shlex
    from siada.support.spinner import Spinner

    class VersionHandler:  # type: ignore[no-redef]
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
