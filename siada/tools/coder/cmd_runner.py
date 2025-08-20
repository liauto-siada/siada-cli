import os
import platform
import subprocess
import sys
from io import BytesIO

import pexpect
import psutil

# Global timeout for command execution (in seconds)
COMMAND_TIMEOUT = 60


def run_cmd_impl(command, verbose=False, cwd=None, error_print=None):
    try:
        if sys.stdin.isatty() and hasattr(pexpect, "spawn") and platform.system() != "Windows":
            return run_cmd_pexpect(command, verbose, cwd)

        return run_cmd_subprocess(command, verbose, cwd)
    except OSError as e:
        error_message = f"Error occurred while running command '{command}': {str(e)}"
        if error_print is None:
            print(error_message)
        else:
            error_print(error_message)
        return 1, error_message


def get_windows_parent_process_name():
    try:
        current_process = psutil.Process()
        while True:
            parent = current_process.parent()
            if parent is None:
                break
            parent_name = parent.name().lower()
            if parent_name in ["powershell.exe", "cmd.exe"]:
                return parent_name
            current_process = parent
        return None
    except Exception:
        return None


def run_cmd_subprocess(command, verbose=False, cwd=None, encoding=sys.stdout.encoding):
    if verbose:
        print("Using run_cmd_subprocess:", command)

    try:
        shell = os.environ.get("SHELL", "/bin/sh")
        parent_process = None

        # Determine the appropriate shell
        if platform.system() == "Windows":
            parent_process = get_windows_parent_process_name()
            if parent_process == "powershell.exe":
                command = f"powershell -Command {command}"

        if verbose:
            print("Running command:", command)
            print("SHELL:", shell)
            if platform.system() == "Windows":
                print("Parent process:", parent_process)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
            encoding=encoding,
            errors="replace",
            bufsize=0,  # Set bufsize to 0 for unbuffered output
            universal_newlines=True,
            cwd=cwd,
        )

        import time
        output = []
        start_time = time.time()
        
        try:
            while True:
                # Check for timeout
                if time.time() - start_time > COMMAND_TIMEOUT:
                    process.kill()
                    process.wait()
                    return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
                
                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining output
                    remaining = process.stdout.read()
                    if remaining:
                        output.append(remaining)
                    break
                
                # Try to read one character with a short timeout
                try:
                    chunk = process.stdout.read(1)
                    if chunk:
                        output.append(chunk)
                        # print(chunk, end="", flush=True)  # Print the chunk in real-time
                    else:
                        # No data available, sleep briefly to avoid busy waiting
                        time.sleep(0.01)
                except Exception:
                    # Handle any read errors
                    time.sleep(0.01)

            return process.returncode, "".join(output)
        finally:
            # Ensure the process and its streams are properly closed
            try:
                if process.stdout:
                    process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
            except Exception:
                pass
    except Exception as e:
        return 1, str(e)


def run_cmd_pexpect(command, verbose=False, cwd=None):
    """
    Run a shell command interactively using pexpect, capturing all output.

    :param command: The command to run as a string.
    :param verbose: If True, print output in real-time.
    :return: A tuple containing (exit_status, output)
    """
    if verbose:
        print("Using run_cmd_pexpect:", command)

    output = BytesIO()

    def output_callback(b):
        output.write(b)
        return b

    try:
        # Use the SHELL environment variable, falling back to /bin/sh if not set
        shell = os.environ.get("SHELL", "/bin/sh")
        if verbose:
            print("With shell:", shell)

        if os.path.exists(shell):
            # Use the shell from SHELL environment variable
            if verbose:
                print("Running pexpect.spawn with shell:", shell)
            child = pexpect.spawn(shell, args=["-i", "-c", command], encoding="utf-8", cwd=cwd)
        else:
            # Fall back to spawning the command directly
            if verbose:
                print("Running pexpect.spawn without shell.")
            child = pexpect.spawn(command, encoding="utf-8", cwd=cwd)

        # Transfer control to the user, capturing output
        child.interact(output_filter=output_callback)

        # Wait for the command to finish and get the exit status
        child.close()
        return child.exitstatus, output.getvalue().decode("utf-8", errors="replace")

    except (pexpect.ExceptionPexpect, TypeError, ValueError) as e:
        error_msg = f"Error running command {command}: {e}"
        return 1, error_msg
