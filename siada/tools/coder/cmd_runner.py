import os
import platform
import re
import select as _select
import subprocess
import sys
import threading
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


def run_cmd_impl(command, verbose=False, cwd=None, error_print=None):
    # import time
    # start_time = time.time()
    
    # Validate cwd exists if provided
    cwd_error = _validate_cwd(cwd)
    if cwd_error:
        _report_error(cwd_error, error_print)
        return 1, cwd_error
    
    try:
        # Determine which execution method to use
        if platform.system() == "Windows":
            # Windows doesn't support pexpect well
            result = run_cmd_subprocess(command, verbose, cwd)
        elif sys.stdin.isatty() and hasattr(pexpect, "spawn"):
            # Traditional TTY mode - use interact() for full interactivity
            result = run_cmd_pexpect(command, verbose, cwd)
        elif is_acp_mode() and hasattr(pexpect, "spawn"):
            # ACP mode (new UI) - use pexpect with expect/sendline pattern
            # This allows interactive commands to work even without TTY
            result = run_cmd_pexpect_acp(command, verbose, cwd)
        else:
            # Fallback to subprocess (no interactivity)
            result = run_cmd_subprocess(command, verbose, cwd)
        
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
        output_truncated = False
        
        try:
            while True:
                # Check for timeout
                if time.time() - start_time > COMMAND_TIMEOUT:
                    print("run_cmd_subprocess timed out, killing process...")  
                    # Add IO to print errors for sending ACP messages
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error("run_cmd_subprocess timed out, killing process...")
                    except:
                        pass
                    process.kill()
                    process.wait()
                    print("run_cmd_subprocess timed out, killing process success.")  
                    # Add IO to print errors for sending ACP messages
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error("run_cmd_subprocess timed out, killing process success.")
                    except:
                        pass
                    return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
                
                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining output
                    remaining = process.stdout.read()
                    if remaining:
                        output_truncated, should_add = _check_and_truncate_output(output, remaining, output_truncated)
                        if should_add:
                            output.append(remaining)
                        # print(remaining, end="", flush=True) # for real-time printing, disable to avoid duplicate prints
                    break
                
                # Use select with timeout to avoid blocking read(1) which would
                # prevent the timeout check at the top of the loop from executing.
                # Without this, read(1) blocks indefinitely when the subprocess
                # produces no output, making the COMMAND_TIMEOUT ineffective.
                try:
                    ready, _, _ = _select.select([process.stdout], [], [], 0.5)
                    if ready:
                        chunk = process.stdout.read(1)
                        if chunk:
                            output_truncated, should_add = _check_and_truncate_output(output, chunk, output_truncated)
                            if should_add:
                                output.append(chunk)
                            # print(chunk, end="", flush=True)  # for real-time printing , disable to avoid duplicate prints
                        else:
                            # EOF - process closed stdout
                            time.sleep(0.01)
                    # else: select timed out, loop back to check COMMAND_TIMEOUT
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


def run_cmd_pexpect_acp(command, verbose=False, cwd=None):
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

    def timeout_callback():
        nonlocal timed_out
        # Don't proceed if already interrupted by Ctrl+C
        if interrupted:
            return
            
        timed_out = True
        logger.warning(f"Command timed out after {COMMAND_TIMEOUT} seconds, killing process...")
        
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
        timer = threading.Timer(COMMAND_TIMEOUT, timeout_callback)
        timer.start()

        # Use the SHELL environment variable
        shell = os.environ.get("SHELL", "/bin/sh")
        if verbose:
            logger.debug(f"With shell: {shell}")

        # Spawn the command
        if os.path.exists(shell):
            child = pexpect.spawn(shell, args=["-c", command], encoding="utf-8", cwd=cwd, timeout=1)
        else:
            child = pexpect.spawn(command, encoding="utf-8", cwd=cwd, timeout=1)
        
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
                        # Check last few lines for interactive prompts
                        # Use \r\n and \n as line separators (pexpect may use \r\n)
                        last_lines = re.split(r'[\r\n]+', current_output)[-5:]
                        last_text = '\n'.join(line for line in last_lines if line.strip())
                        
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
            return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
        
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
            return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
        error_msg = f"Error running command {command}: {e}"
        logger.error(error_msg)
        return 1, error_msg
    finally:
        # Clean up global child process reference
        with _current_child_lock:
            _current_child_process = None
        if timer:
            timer.cancel()


def run_cmd_pexpect(command, verbose=False, cwd=None):
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
                print(f"\nCommand timed out after {COMMAND_TIMEOUT} seconds, killing process...")
            try:
                child.kill(9)  # Force kill the process
            except:
                pass  # Process might already be dead

    try:
        # Start timeout timer
        timer = threading.Timer(COMMAND_TIMEOUT, timeout_callback)
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
        if os.path.exists(shell):
            # Use the shell from SHELL environment variable
            if needs_interactive:
                # Use -i for aliases, functions, and version managers (slower but necessary)
                if verbose:
                    print("Running pexpect.spawn with interactive shell (-i):", shell)
                child = pexpect.spawn(shell, args=["-i", "-c", command], encoding="utf-8", cwd=cwd)
            else:
                if verbose:
                    print("Running pexpect.spawn with non-interactive shell (-c):", shell)
                child = pexpect.spawn(shell, args=["-c", command], encoding="utf-8", cwd=cwd)
        else:
            # Fall back to spawning the command directly
            if verbose:
                print("Running pexpect.spawn without shell.")
            child = pexpect.spawn(command, encoding="utf-8", cwd=cwd)
        child.delaybeforesend = None

        # Transfer control to the user, capturing output
        child.interact(output_filter=output_callback)

        # Wait for the command to finish and get the exit status
        child.close()
        
        # Check if command was terminated due to timeout
        if timed_out:
            return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
        
        return child.exitstatus, output.getvalue().decode("utf-8", errors="replace")

    except (pexpect.ExceptionPexpect, TypeError, ValueError) as e:
        if timed_out:
            return 1, f"Command timed out after {COMMAND_TIMEOUT} seconds"
        error_msg = f"Error running command {command}: {e}"
        return 1, error_msg
    finally:
        # Ensure timer is cancelled
        if timer:
            timer.cancel()
