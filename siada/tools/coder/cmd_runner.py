import os
import platform
import re
import select as _select
import shutil
import subprocess
import sys
import threading
from functools import lru_cache
from io import BytesIO

import pexpect
import psutil

from siada.foundation.logging import logger


def _load_command_timeout(default: int = 60) -> int:
    """Load COMMAND_TIMEOUT from ~/.siada-cli/conf.yaml via load_conf().

    Expected key: command_timeout

    Falls back to default on any error or invalid value.
    """
    try:
        from siada.config.config_loader import load_conf

        conf = load_conf()
        raw = getattr(conf, "command_timeout", None)
        if raw is None:
            return default

        timeout = int(raw)
        return timeout if timeout > 0 else default
    except Exception:
        return default


# Global timeout for command execution (in seconds)
COMMAND_TIMEOUT = _load_command_timeout(60)

# Maximum output length to prevent memory issues (in characters)
MAX_OUTPUT_LENGTH = 20000

# Global cancellation event for cross-thread interrupt signaling.
# When Ctrl+C is caught by the main thread (in conversation_turn.py),
# it sets this event to signal the dedicated loop thread to stop
# blocking on select.select() in _poll_stdin_with_timeout_check.
_cancel_event = threading.Event()

# Global reference to the current pexpect child process.
# Used by cancel_current_command() to kill the process from outside.
_current_child_process = None
_current_child_lock = threading.Lock()


def cancel_current_command():
    """
    Cancel the currently running interactive command from outside.
    
    This is called from conversation_turn.py when KeyboardInterrupt is caught
    in the main thread, to signal the dedicated loop thread to stop waiting
    and kill the child process.
    
    This function is thread-safe and can be called from any thread.
    """
    logger.info("[cancel_current_command] Setting cancel event and killing child process")
    
    # 1. Set the cancel event to unblock _poll_stdin_with_timeout_check
    _cancel_event.set()
    
    # 2. Kill the child process
    with _current_child_lock:
        child = _current_child_process
    
    if child:
        try:
            if child.isalive():
                if hasattr(child, 'pid') and child.pid:
                    kill_process_tree(child.pid)
                else:
                    child.kill(9)
                logger.info("[cancel_current_command] Child process killed")
        except Exception as e:
            logger.debug(f"[cancel_current_command] Error killing child: {e}")
    
    # 3. Send interactive_input_cancel to frontend
    try:
        from siada.io.io import InputOutput
        io = InputOutput.get_instance()
        if io and io.acp_enabled and io.acp_adapter:
            logger.info("[cancel_current_command] Sending interactive_input_cancel (interrupted)")
            io.acp_adapter.interactive_input_cancel(reason="interrupted")
    except Exception as e:
        logger.error(f"[cancel_current_command] Error sending cancel: {e}")


def is_acp_mode():
    """
    Check if running in ACP mode (new UI mode).
    
    In ACP mode, stdin is a pipe (not a TTY), but we still want to support
    interactive commands by using pexpect with expect/sendline pattern
    instead of interact().
    
    Returns:
        bool: True if in ACP mode
    """
    return os.environ.get('SIADA_ACP_MODE', '').lower() in ('1', 'true', 'yes')


def kill_process_tree(pid):
    """
    Kill a process and all its children recursively.
    
    This ensures that interactive commands like 'sudo' are fully terminated,
    including any child processes they may have spawned.
    
    Args:
        pid: Process ID to kill
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # Kill children first
        for child in children:
            try:
                logger.debug(f"Killing child process {child.pid}")
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Kill parent
        try:
            logger.debug(f"Killing parent process {pid}")
            parent.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
        # Wait for processes to terminate
        gone, alive = psutil.wait_procs(children + [parent], timeout=3)
        for p in alive:
            try:
                logger.warning(f"Force killing process {p.pid}")
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.debug(f"Process {pid} already terminated or access denied: {e}")


def _make_no_pager_env():
    """Return a copy of the current environment with terminal pagers disabled.

    Prevents tools like git/less from invoking interactive pagers that would
    block command execution inside a Siada session.
    """
    env = os.environ.copy()
    env['GIT_PAGER'] = 'cat'
    env['SYSTEMD_PAGER'] = 'cat'
    env['PAGER'] = 'cat'
    env['LESS'] = '-FRX'
    return env


def _validate_cwd(cwd):
    """Validate working directory exists and is a directory.
    
    Returns error message string if invalid, None if valid.
    """
    if cwd is None:
        return None
    if not os.path.exists(cwd):
        return f"Working directory does not exist: {cwd}"
    if not os.path.isdir(cwd):
        return f"Working directory path is not a directory: {cwd}"
    return None


def _report_error(message, error_print=None):
    """Report error via error_print callback or stdout + IO fallback."""
    if error_print is not None:
        error_print(message)
        return
    print(message)
    try:
        from siada.io.io import InputOutput
        io = InputOutput.get_instance()
        if io:
            io.print_error(message)
    except:
        pass


def run_cmd_impl(command, verbose=False, cwd=None, error_print=None, timeout=None):
    # import time
    # start_time = time.time()
    
    # Validate cwd exists if provided
    cwd_error = _validate_cwd(cwd)
    if cwd_error:
        _report_error(cwd_error, error_print)
        return 1, cwd_error

    effective_timeout = timeout if timeout and timeout > 0 else COMMAND_TIMEOUT

    try:
        # Determine which execution method to use
        if platform.system() == "Windows":
            # Windows doesn't support pexpect well
            result = run_cmd_subprocess(command, verbose, cwd, timeout=effective_timeout)
        elif sys.stdin.isatty() and hasattr(pexpect, "spawn"):
            # Traditional TTY mode - use interact() for full interactivity
            result = run_cmd_pexpect(command, verbose, cwd, timeout=effective_timeout)
        elif is_acp_mode() and hasattr(pexpect, "spawn"):
            # ACP mode (new UI) - use pexpect with expect/sendline pattern
            # This allows interactive commands to work even without TTY
            result = run_cmd_pexpect_acp(command, verbose, cwd, timeout=effective_timeout)
        else:
            # Fallback to subprocess (no interactivity)
            result = run_cmd_subprocess(command, verbose, cwd, timeout=effective_timeout)
        
        # elapsed_time = time.time() - start_time
        # print(f"\n[time: {elapsed_time:.2f}s]")
        return result
    except OSError as e:
        # elapsed_time = time.time() - start_time
        error_message = f"Error occurred while running command '{command}': {str(e)}"
        if error_print is None:
            print(error_message)
            # Add IO to print errors for sending ACP messages
            try:
                from siada.io.io import InputOutput
                io = InputOutput.get_instance()
                if io:
                    io.print_error(error_message)
            except:
                pass
        else:
            error_print(error_message)
        # print(f"\n[time: {elapsed_time:.2f}s]")
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


def _check_and_truncate_output(output_list, new_data, output_truncated):
    """
    Check if adding new data would exceed the limit and handle truncation.
    
    Args:
        output_list: List of output chunks
        new_data: New data to potentially add
        output_truncated: Current truncation status
    
    Returns:
        tuple: (updated_output_truncated, should_add_data)
    """
    if output_truncated or not new_data:
        return output_truncated, False
    
    current_length = sum(len(chunk) for chunk in output_list)
    
    # Check if we've already reached the limit
    if current_length >= MAX_OUTPUT_LENGTH:
        if not output_truncated:
            output_list.append(f"\n... [Output truncated, exceeded {MAX_OUTPUT_LENGTH} character limit] ...")
        return True, False
    
    # Check if adding new data would exceed the limit
    if current_length + len(new_data) > MAX_OUTPUT_LENGTH:
        # Add only the portion that fits
        allowed_length = MAX_OUTPUT_LENGTH - current_length
        if allowed_length > 0:
            output_list.append(new_data[:allowed_length])
        output_list.append(f"\n... [Output truncated, exceeded {MAX_OUTPUT_LENGTH} character limit] ...")
        return True, False
    
    return False, True


def _run_subprocess_core(
    *,
    popen_args,
    shell: bool,
    cwd,
    timeout: int,
    encoding,
    verbose: bool,
):
    """Shared subprocess driver loop with reader-thread + queue draining.

    Used by both run_cmd_subprocess (shell=True, str command) and
    run_powershell_impl (shell=False, argv list).
    """
    try:
        process = subprocess.Popen(
            popen_args,
            stdin=subprocess.DEVNULL,  # Close stdin so non-interactive tools (e.g. python -c on Windows) receive EOF immediately instead of blocking
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Binary mode: avoids Windows pipe-buffer deadlock.
            # _select.select() on Windows raises OSError on pipe objects, so the
            # old select+read(1) loop never actually read anything — the child's
            # pipe buffer filled up and it stalled waiting for space, causing a
            # timeout.  Using a reader thread + read1(4096) drains whatever bytes
            # are currently available without waiting for a full 4096-byte chunk,
            # so the pipe is always emptied promptly on both Windows and POSIX.
            shell=shell,
            bufsize=-1,  # default BufferedReader — required for read1()
            cwd=cwd,
            env=_make_no_pager_env(),
        )

        import codecs as _codecs
        import queue
        import time

        output = []
        output_truncated = False
        effective_timeout = timeout if timeout and timeout > 0 else COMMAND_TIMEOUT
        _enc = encoding or sys.stdout.encoding or "utf-8"
        _decoder = _codecs.getincrementaldecoder(_enc)("replace")

        # Drain stdout in a dedicated reader thread and feed decoded text into a
        # queue.  The main thread pulls from the queue with a short timeout so the
        # COMMAND_TIMEOUT check keeps running every 0.5 s.
        stdout_queue: queue.Queue[str | None] = queue.Queue()

        def _reader():
            try:
                while True:
                    raw = process.stdout.read1(4096)
                    if not raw:
                        break
                    text = _decoder.decode(raw).replace("\r\n", "\n")
                    if text:
                        stdout_queue.put(text)
            finally:
                remaining = _decoder.decode(b"", final=True)
                if remaining:
                    stdout_queue.put(remaining.replace("\r\n", "\n"))
                stdout_queue.put(None)  # sentinel: EOF

        import threading as _threading
        reader_thread = _threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        start_time = time.time()

        try:
            while True:
                # Check for timeout
                if time.time() - start_time > effective_timeout:
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error("_run_subprocess_core timed out, killing process...")
                    except Exception:
                        pass
                    process.kill()
                    process.wait()
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error("_run_subprocess_core timed out, killing process success.")
                    except Exception:
                        pass
                    return 1, f"Command timed out after {effective_timeout} seconds"

                try:
                    chunk = stdout_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if chunk is None:
                    break

                output_truncated, should_add = _check_and_truncate_output(output, chunk, output_truncated)
                if should_add:
                    output.append(chunk)

            reader_thread.join(timeout=2)
            process.wait()
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


@lru_cache(maxsize=1)
def _resolve_powershell_executable() -> str:
    """Find PowerShell executable. Prefer pwsh (7+), fall back to powershell (5.1).

    Returns absolute path. Raises RuntimeError if neither is found.
    Result cached for the process lifetime.
    """
    pwsh = shutil.which("pwsh")
    if pwsh:
        return pwsh
    powershell = shutil.which("powershell")
    if powershell:
        return powershell
    raise RuntimeError(
        "PowerShell executable not found. Neither 'pwsh' nor 'powershell' is on PATH."
    )


def _build_powershell_wrapped_command(user_command: str) -> str:
    """Wrap user command with UTF-8 setup prefix and exit-code capture suffix.

    Prefix forces console output encoding to UTF-8 (avoids PS 5.1's UTF-16 LE BOM).
    Suffix captures $LASTEXITCODE with $? fallback, working around PS 5.1's
    stderr-sets-$?-to-false bug.
    """
    prefix = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8; "
    )
    suffix = (
        "; $_ec = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } "
        "elseif ($?) { 0 } else { 1 }; exit $_ec"
    )
    return f"{prefix}{user_command}{suffix}"


def run_powershell_impl(command, verbose=False, cwd=None, timeout=None):
    """Execute a PowerShell command on Windows.

    Returns (returncode, stdout_text). On non-Windows platforms raises
    RuntimeError — the upstream tool registration should prevent this from
    being reached, but we fail loud rather than silently mis-execute.
    """
    if platform.system() != "Windows":
        raise RuntimeError("run_powershell_impl is Windows-only")

    cwd_error = _validate_cwd(cwd)
    if cwd_error:
        return 1, cwd_error

    effective_timeout = timeout if timeout and timeout > 0 else COMMAND_TIMEOUT

    try:
        ps_exe = _resolve_powershell_executable()
    except RuntimeError as e:
        return 1, str(e)

    wrapped = _build_powershell_wrapped_command(command)
    argv = [
        ps_exe,
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        wrapped,
    ]

    if verbose:
        print("Using run_powershell_impl:", command)
        print("PowerShell exe:", ps_exe)

    try:
        return _run_subprocess_core(
            popen_args=argv,
            shell=False,
            cwd=cwd,
            timeout=effective_timeout,
            encoding="utf-8",
            verbose=verbose,
        )
    except OSError as e:
        return 1, f"Error occurred while running PowerShell command '{command}': {e}"


def run_cmd_subprocess(command, verbose=False, cwd=None, encoding=sys.stdout.encoding, timeout=None):
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

        return _run_subprocess_core(
            popen_args=command,
            shell=isinstance(command, str),
            cwd=cwd,
            timeout=timeout if timeout and timeout > 0 else COMMAND_TIMEOUT,
            encoding=encoding,
            verbose=verbose,
        )
    except Exception as e:
        return 1, str(e)


def _poll_stdin_with_timeout_check(is_timed_out, poll_interval=0.5):
    """
    Non-blocking stdin reader that periodically checks a timeout condition
    AND the global _cancel_event.
    
    Instead of blocking forever on sys.stdin.readline(), this function uses
    select.select() to poll stdin with a short timeout. Between polls, it
    checks both the is_timed_out callable and _cancel_event. If either
    condition is met, it returns None immediately.
    
    The _cancel_event is critical for cross-thread cancellation: when the
    main thread catches KeyboardInterrupt (Ctrl+C), it sets _cancel_event
    to unblock this function running in the dedicated loop thread.
    
    This is used in ACP mode where the frontend sends input via stdin pipe.
    The input follows the SIADA_MSG_START/SIADA_MSG_END protocol.
    
    Args:
        is_timed_out: A callable that returns True if timeout has occurred.
        poll_interval: How long to wait on each select() call (seconds).
    
    Returns:
        str: The user input (stripped of protocol markers), or None if timed out/cancelled.
    """
    import sys
    
    def _should_stop():
        """Check if we should stop waiting (timeout or cancelled)."""
        return is_timed_out() or _cancel_event.is_set()
    
    while True:
        if _should_stop():
            logger.debug("[_poll_stdin] Stopping: timed_out=%s, cancelled=%s",
                        is_timed_out(), _cancel_event.is_set())
            return None
        
        try:
            # Poll stdin with a short timeout
            ready, _, _ = _select.select([sys.stdin], [], [], poll_interval)
            if not ready:
                # No data available, loop back to check timeout/cancel
                continue
            
            line = sys.stdin.readline()
            if not line:
                # EOF - check conditions and retry
                if _should_stop():
                    return None
                import time
                time.sleep(0.1)
                continue
            
            # Check for SIADA message protocol markers
            if line.strip() == '<<<SIADA_MSG_START>>>':
                # Read the complete multiline message
                message_lines = []
                while True:
                    if _should_stop():
                        return None
                    
                    content_line = sys.stdin.readline()
                    if not content_line:
                        if _should_stop():
                            return None
                        import time
                        time.sleep(0.1)
                        continue
                    
                    if content_line.strip() == '<<<SIADA_MSG_END>>>':
                        break
                    message_lines.append(content_line.rstrip('\n'))
                
                return '\n'.join(message_lines)
            else:
                # Single line input (no protocol markers)
                return line.rstrip('\n')
                
        except (IOError, OSError):
            if _should_stop():
                return None
            import time
            time.sleep(0.1)
            continue


def run_cmd_pexpect_acp(command, verbose=False, cwd=None, timeout=None):
    """
    Run a shell command using pexpect in ACP mode (non-TTY environment).
    
    This function is designed for the new UI mode where stdin is a pipe.
    Instead of using interact() which requires a TTY, it uses expect/sendline
    pattern to handle interactive prompts (like password input).
    
    The function:
    1. Spawns the command in a PTY (pseudo-terminal)
    2. Monitors output for interactive prompts (password, yes/no, etc.)
    3. When a prompt is detected, requests input from user via IO module
    4. Sends the user input to the child process
    
    :param command: The command to run as a string.
    :param verbose: If True, print output in real-time.
    :param cwd: Working directory for the command.
    :param timeout: Timeout in seconds. Defaults to COMMAND_TIMEOUT.
    :return: A tuple containing (exit_status, output)
    """
    if verbose:
        logger.info(f"Using run_cmd_pexpect_acp: {command}")

    output_chunks = []
    child = None
    timer = None
    timed_out = False
    interrupted = False  # Track if user pressed Ctrl+C
    output_truncated = False
    effective_timeout = timeout if timeout and timeout > 0 else COMMAND_TIMEOUT

    def timeout_callback():
        nonlocal timed_out
        # Don't proceed if already interrupted by Ctrl+C
        if interrupted:
            return
            
        timed_out = True
        logger.warning(f"Command timed out after {effective_timeout} seconds, killing process...")
        
        # Send interactive_input_cancel to frontend to dismiss any active input prompt
        # This must happen BEFORE killing the child process, so the frontend knows
        # to close the password/input dialog
        try:
            from siada.io.io import InputOutput
            io = InputOutput.get_instance()
            if io and io.acp_enabled and io.acp_adapter:
                logger.info("Sending interactive_input_cancel via ACP (timeout)")
                io.acp_adapter.interactive_input_cancel(reason="timeout")
        except Exception as e:
            logger.error(f"Error sending interactive_input_cancel: {e}")
        
        if child and child.isalive():
            try:
                # Use process tree killer to ensure all child processes are terminated
                if hasattr(child, 'pid') and child.pid:
                    kill_process_tree(child.pid)
                else:
                    child.kill(9)
            except:
                pass

    # Common patterns that indicate the command is waiting for user input
    # These patterns are used to detect when we need to prompt the user
    INTERACTIVE_PATTERNS = [
        r'[Pp]assword[:\s]*$',           # Password prompts
        r'[Pp]assphrase[:\s]*$',         # SSH passphrase
        r'\[sudo\].*password.*:',        # sudo password
        r'Enter passphrase.*:',          # GPG/SSH passphrase
        r'\(yes/no\)\??\s*$',            # yes/no confirmation
        r'\(y/n\)\??\s*$',               # y/n confirmation
        r'\[Y/n\]\s*$',                  # Y/n confirmation
        r'\[y/N\]\s*$',                  # y/N confirmation
        r'Are you sure.*\?',             # General confirmation
        r'Continue\?',                   # Continue prompt
        r'Proceed\?',                    # Proceed prompt
        r'Press.*to continue',           # Press key to continue
        r'Enter.*:',                     # Generic enter prompt
        r'Username[:\s]*$',              # Username prompt
        r'Login[:\s]*$',                 # Login prompt
    ]

    try:
        # Reset the cancel event at the start of each command execution.
        # This ensures a previous Ctrl+C doesn't affect the new command.
        _cancel_event.clear()
        
        # Start timeout timer
        timer = threading.Timer(effective_timeout, timeout_callback)
        timer.start()

        # Use the SHELL environment variable
        shell = os.environ.get("SHELL", "/bin/sh")
        if verbose:
            logger.debug(f"With shell: {shell}")

        # Spawn the command
        no_pager_env = _make_no_pager_env()
        if os.path.exists(shell):
            child = pexpect.spawn(shell, args=["-c", command], encoding="utf-8", cwd=cwd, timeout=1, env=no_pager_env)
        else:
            child = pexpect.spawn(command, encoding="utf-8", cwd=cwd, timeout=1, env=no_pager_env)
        
        child.delaybeforesend = None
        
        # Register the child process globally so cancel_current_command() can kill it
        global _current_child_process
        with _current_child_lock:
            _current_child_process = child

        # Compile patterns for matching
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INTERACTIVE_PATTERNS]
        
        # Track whether we already handled an interactive prompt for the current output
        # to avoid re-detecting the same prompt repeatedly
        last_prompt_handled_at = 0  # length of output_chunks when last prompt was handled
        
        # Main loop: read output and handle interactive prompts
        while child.isalive() or child.buffer:
            if timed_out or _cancel_event.is_set():
                if _cancel_event.is_set():
                    logger.info("[run_cmd_pexpect_acp] Cancel event detected, breaking main loop")
                    interrupted = True
                break
            
            try:
                # Use expect with EOF and TIMEOUT to read available data
                # NOTE: When TIMEOUT is in the expect list, it returns index=1 on timeout
                # instead of raising pexpect.TIMEOUT exception
                index = child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=0.5)
                
                # Get any output that was read
                if child.before:
                    chunk = child.before
                    if not output_truncated:
                        output_truncated, should_add = _check_and_truncate_output(
                            output_chunks, chunk, output_truncated
                        )
                        if should_add:
                            output_chunks.append(chunk)
                
                if index == 0:  # EOF - process finished
                    break
                
                if index == 1:  # TIMEOUT - process still running, check for interactive prompts
                    # Check if the output matches any interactive pattern
                    current_chunks_len = len(output_chunks)
                    if current_chunks_len > last_prompt_handled_at and output_chunks:
                        current_output = "".join(output_chunks)

                        # A real interactive prompt (e.g. "Password: ") leaves the
                        # cursor on the same line without a trailing newline, since
                        # the child process is blocked waiting for input right after
                        # printing the prompt. Ordinary output (e.g. log lines from
                        # `grep`/`cat`) is always newline-terminated once flushed.
                        # If the buffer currently ends with a newline, there is no
                        # "dangling" line waiting for input, so skip the check to
                        # avoid false positives from log content that happens to
                        # match one of the broad patterns below.
                        ends_with_newline = current_output.endswith(('\n', '\r'))

                        # Only inspect the actual last (possibly incomplete) line,
                        # not a block of the last few lines - matching against a
                        # multi-line block can trigger on a line that isn't the one
                        # the cursor is actually sitting on.
                        last_lines = re.split(r'[\r\n]+', current_output)
                        last_text = last_lines[-1] if last_lines else ''

                        if ends_with_newline or not last_text.strip():
                            last_prompt_handled_at = current_chunks_len
                            continue

                        for pattern in compiled_patterns:
                            if pattern.search(last_text):
                                # Interactive prompt detected! Get user input
                                logger.info(f"Interactive prompt detected: {last_text[-200:]}")
                                last_prompt_handled_at = current_chunks_len
                                
                                # Determine if this is a password prompt
                                is_password = bool(re.search(r'[Pp]ass(word|phrase)', last_text))
                                
                                try:
                                    from siada.io.io import InputOutput
                                    io = InputOutput.get_instance()
                                    if io:
                                        # In ACP mode, send interactive_input_request message
                                        # This notifies the frontend to display the prompt and wait for input
                                        if io.acp_enabled and io.acp_adapter:
                                            logger.info("Sending interactive_input_request via ACP")
                                            io.acp_adapter.interactive_input_request(
                                                prompt=last_text,
                                                input_type="password" if is_password else "text",
                                                is_password=is_password
                                            )
                                        else:
                                            # Non-ACP mode: display the prompt directly
                                            io.tool_output(f"\n[Interactive input required]\n{last_text}\n")
                                        
                                        # Get input from user
                                        # In ACP mode, use non-blocking polling so we can
                                        # detect timeout and break out instead of blocking
                                        # forever on sys.stdin.readline()
                                        user_input = None
                                        if io.acp_enabled:
                                            user_input = _poll_stdin_with_timeout_check(
                                                lambda: timed_out
                                            )
                                        else:
                                            user_input = io.get_input(display_rule=False)
                                        
                                        if timed_out:
                                            # Timeout occurred while waiting for input,
                                            # break out of the pattern loop; the outer
                                            # while-loop will also exit via timed_out check
                                            logger.info("Timed out while waiting for interactive input")
                                            break
                                        
                                        if user_input is not None:
                                            # Send input to child process
                                            child.sendline(user_input)
                                            logger.info("User input sent to child process")
                                        else:
                                            # User cancelled, send empty line
                                            child.sendline("")
                                except KeyboardInterrupt:
                                    # User pressed Ctrl+C during interactive input (e.g., password prompt)
                                    # Mark as interrupted and send cancel message with proper reason
                                    # (no 'nonlocal' needed - we're in the same function scope)
                                    interrupted = True
                                    
                                    logger.info("KeyboardInterrupt during interactive input, killing child process")
                                    
                                    # Send interactive_input_cancel with 'interrupted' reason
                                    try:
                                        from siada.io.io import InputOutput
                                        io = InputOutput.get_instance()
                                        if io and io.acp_enabled and io.acp_adapter:
                                            logger.info("Sending interactive_input_cancel via ACP (interrupted)")
                                            io.acp_adapter.interactive_input_cancel(reason="interrupted")
                                    except Exception as e:
                                        logger.error(f"Error sending interactive_input_cancel: {e}")
                                    
                                    # Kill the child process and all its children
                                    try:
                                        if child and child.isalive():
                                            if hasattr(child, 'pid') and child.pid:
                                                kill_process_tree(child.pid)
                                            else:
                                                child.kill(9)
                                    except:
                                        pass
                                    raise
                                except Exception as e:
                                    logger.error(f"Error getting user input: {e}")
                                    # Send empty line to avoid hanging
                                    child.sendline("")
                                
                                break  # Exit pattern check loop
                    
            except pexpect.EOF:
                # Process finished
                if child.before:
                    chunk = child.before
                    if not output_truncated:
                        output_truncated, should_add = _check_and_truncate_output(
                            output_chunks, chunk, output_truncated
                        )
                        if should_add:
                            output_chunks.append(chunk)
                break
            except KeyboardInterrupt:
                # KeyboardInterrupt during pexpect loop (e.g., during interactive input)
                # Mark as interrupted, send cancel message, kill child process and re-raise
                interrupted = True
                logger.info("KeyboardInterrupt in pexpect loop, killing child process")
                
                # Send interactive_input_cancel with 'interrupted' reason
                try:
                    from siada.io.io import InputOutput
                    io = InputOutput.get_instance()
                    if io and io.acp_enabled and io.acp_adapter:
                        logger.info("Sending interactive_input_cancel via ACP (interrupted)")
                        io.acp_adapter.interactive_input_cancel(reason="interrupted")
                except Exception as e:
                    logger.error(f"Error sending interactive_input_cancel: {e}")
                
                try:
                    if child and child.isalive():
                        if hasattr(child, 'pid') and child.pid:
                            kill_process_tree(child.pid)
                        else:
                            child.kill(9)
                except:
                    pass
                raise
            except Exception as e:
                logger.error(f"Error in pexpect loop: {e}")
                break

        # Wait for process to finish
        try:
            child.close()
        except Exception:
            pass
        
        if timed_out:
            return 1, f"Command timed out after {effective_timeout} seconds"
        
        if interrupted or _cancel_event.is_set():
            return 1, "Command interrupted by user (Ctrl+C)"
        
        exit_status = child.exitstatus if child.exitstatus is not None else 1
        return exit_status, "".join(output_chunks)

    except KeyboardInterrupt:
        # User interrupted (Ctrl+C) - ensure child process is cleaned up
        interrupted = True
        logger.info("KeyboardInterrupt in run_cmd_pexpect_acp, cleaning up child process")
        
        # Send interactive_input_cancel with 'interrupted' reason if not already sent
        try:
            from siada.io.io import InputOutput
            io = InputOutput.get_instance()
            if io and io.acp_enabled and io.acp_adapter:
                logger.info("Sending interactive_input_cancel via ACP (interrupted)")
                io.acp_adapter.interactive_input_cancel(reason="interrupted")
        except Exception as e:
            logger.error(f"Error sending interactive_input_cancel: {e}")
        
        try:
            if child and child.isalive():
                if hasattr(child, 'pid') and child.pid:
                    kill_process_tree(child.pid)
                else:
                    child.kill(9)
                child.close()
        except:
            pass
        raise  # Re-raise to let conversation_turn handle it
    except (pexpect.ExceptionPexpect, TypeError, ValueError) as e:
        if timed_out:
            return 1, f"Command timed out after {effective_timeout} seconds"
        error_msg = f"Error running command {command}: {e}"
        logger.error(error_msg)
        return 1, error_msg
    finally:
        # Clean up global child process reference
        with _current_child_lock:
            _current_child_process = None
        if timer:
            timer.cancel()


def run_cmd_pexpect(command, verbose=False, cwd=None, timeout=None):
    """
    Run a shell command interactively using pexpect, capturing all output.
    
    This is the traditional mode that uses interact() for full TTY interactivity.
    Only works when stdin is a TTY.

    :param command: The command to run as a string.
    :param verbose: If True, print output in real-time.
    :return: A tuple containing (exit_status, output)
    """
    if verbose:
        print("Using run_cmd_pexpect:", command)

    output = BytesIO()
    child = None
    timer = None
    timed_out = False  # Flag to track if command timed out
    output_truncated = False  # Flag to track if output was truncated
    effective_timeout = timeout if timeout and timeout > 0 else COMMAND_TIMEOUT

    def output_callback(b):
        nonlocal output_truncated
        current_size = output.tell()
        
        if current_size < MAX_OUTPUT_LENGTH:
            # Check if adding this chunk would exceed the limit
            if current_size + len(b) > MAX_OUTPUT_LENGTH:
                # Write only the portion that fits
                remaining_space = MAX_OUTPUT_LENGTH - current_size
                if remaining_space > 0:
                    output.write(b[:remaining_space])
                # Add truncation message
                truncation_msg = b"\n... [Output truncated, exceeded " + str(MAX_OUTPUT_LENGTH).encode() + b" character limit] ..."
                output.write(truncation_msg)
                output_truncated = True
            else:
                output.write(b)
        # If already truncated, don't write anything more
        
        return b

    def timeout_callback():
        nonlocal timed_out
        timed_out = True
        if child and child.isalive():
            if verbose:
                print(f"\nCommand timed out after {effective_timeout} seconds, killing process...")
            try:
                child.kill(9)  # Force kill the process
            except:
                pass  # Process might already be dead

    try:
        # Start timeout timer
        timer = threading.Timer(effective_timeout, timeout_callback)
        timer.start()

        # Use the SHELL environment variable, falling back to /bin/sh if not set
        shell = os.environ.get("SHELL", "/bin/sh")
        if verbose:
            print("With shell:", shell)

        # Determine if command needs interactive shell environment
        # Extract first word of command
        first_word = command.strip().split()[0] if command.strip() else ""
        
        # Standard commands that DON'T need -i (interactive mode)
        standard_commands = {
            'ls', 'cd', 'pwd', 'mkdir', 'rm', 'cp', 'mv', 'touch', 'cat', 'grep',
            'find', 'sed', 'awk', 'echo', 'git', 'docker', 'make', 'curl', 'wget',
              'vim', 'nano', 'tar', 'zip', 'unzip'
        }
        
        needs_interactive = False
        
        # Check for version manager keywords
        if re.search(r'\b(nvm|pyenv|rvm|rbenv|conda)\b', command):
            needs_interactive = True
        elif first_word and first_word not in standard_commands:
            needs_interactive = True
        no_pager_env = _make_no_pager_env()
        if os.path.exists(shell):
            # Use the shell from SHELL environment variable
            if needs_interactive:
                # Use -i for aliases, functions, and version managers (slower but necessary)
                if verbose:
                    print("Running pexpect.spawn with interactive shell (-i):", shell)
                child = pexpect.spawn(shell, args=["-i", "-c", command], encoding="utf-8", cwd=cwd, env=no_pager_env)
            else:
                if verbose:
                    print("Running pexpect.spawn with non-interactive shell (-c):", shell)
                child = pexpect.spawn(shell, args=["-c", command], encoding="utf-8", cwd=cwd, env=no_pager_env)
        else:
            # Fall back to spawning the command directly
            if verbose:
                print("Running pexpect.spawn without shell.")
            child = pexpect.spawn(command, encoding="utf-8", cwd=cwd, env=no_pager_env)
        child.delaybeforesend = None

        # Transfer control to the user, capturing output
        child.interact(output_filter=output_callback)

        # Wait for the command to finish and get the exit status
        child.close()
        
        # Check if command was terminated due to timeout
        if timed_out:
            return 1, f"Command timed out after {effective_timeout} seconds"
        
        return child.exitstatus, output.getvalue().decode("utf-8", errors="replace")

    except (pexpect.ExceptionPexpect, TypeError, ValueError) as e:
        if timed_out:
            return 1, f"Command timed out after {effective_timeout} seconds"
        error_msg = f"Error running command {command}: {e}"
        return 1, error_msg
    finally:
        # Ensure timer is cancelled
        if timer:
            timer.cancel()
