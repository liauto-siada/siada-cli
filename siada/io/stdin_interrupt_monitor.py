"""
Stdin Interrupt Monitor for ACP Mode

In ACP mode, the Node.js frontend communicates with the Python backend via
piped stdin/stdout.  This module provides a background thread that:

1. Reads ALL data from stdin **byte-by-byte** (not line-buffered)
2. Detects \\x03 (ETX) bytes immediately and delivers a **real** SIGINT to
   the main thread – capable of interrupting C extensions (HTTP clients, etc.)
3. Reconstructs lines and forwards them to a thread-safe queue for get_input()

Platform-specific interrupt delivery:
  - Unix/macOS:  ``os.kill(os.getpid(), signal.SIGINT)`` – sends a genuine
    POSIX signal that interrupts blocking system calls (select, recv …)
    with EINTR, then the custom SIGINT handler raises KeyboardInterrupt.
  - Windows:  ``_thread.interrupt_main()`` – triggers Python's signal
    mechanism without broadcasting CTRL_C_EVENT to the console group
    (which would also kill the Node.js parent).

A custom SIGINT handler with a 0.5 s debounce window is installed so that
duplicate interrupts (e.g. the frontend sends *both* ETX and
``process.kill('SIGINT')`` on macOS) result in only **one**
KeyboardInterrupt.
"""

import logging
import os
import queue
import signal
import sys
import threading
import time

logger = logging.getLogger(__name__)

# Singleton instance
_monitor = None
_monitor_lock = threading.Lock()


class StdinInterruptMonitor:
    """Background stdin reader that intercepts ETX (\\x03) for interrupt delivery."""

    def __init__(self):
        self._queue = queue.Queue()
        self._thread = None
        self._running = False
        self._main_thread_id = threading.main_thread().ident
        self._last_interrupt_time = 0.0
        # Debounce interval: ignore duplicate interrupts within this window (seconds).
        # Prevents double-interrupt when BOTH the OS SIGINT (e.g. adapter's
        # process.kill('SIGINT') on macOS) AND the ETX byte arrive for the
        # same user keypress.
        self._debounce_interval = 0.5

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the background stdin reader thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="stdin-interrupt-monitor",
        )
        self._thread.start()
        logger.info("[StdinInterruptMonitor] Started background stdin reader (byte-level)")

    def stop(self):
        """Signal the reader thread to stop (best-effort; thread is daemon)."""
        self._running = False

    # ------------------------------------------------------------------
    # Public API – replaces sys.stdin.readline() in io.py
    # ------------------------------------------------------------------

    def readline(self, timeout: float = 0.1) -> str:
        """Return the next line from stdin (blocking, with timeout).

        Returns an empty string on timeout (caller should retry).
        Raises EOFError when the real stdin has been closed.
        """
        try:
            item = self._queue.get(timeout=timeout)
            if item is None:
                # Sentinel value indicating EOF on the real stdin
                raise EOFError("EOF on stdin")
            return item
        except queue.Empty:
            return ""

    # ------------------------------------------------------------------
    # Background thread – byte-level reading
    # ------------------------------------------------------------------

    def _reader_loop(self):
        """Continuously read bytes from stdin, detect ETX immediately, reconstruct lines.

        Unlike readline(), reading byte-by-byte ensures that a bare \\x03
        (without a trailing newline) is detected instantly.
        """
        line_buf = bytearray()
        # Use the raw binary buffer to avoid text-mode line buffering
        raw = sys.stdin.buffer

        while self._running:
            try:
                byte = raw.read(1)
                if not byte:
                    # EOF – enqueue any partial line, then push sentinel
                    if line_buf:
                        self._queue.put(line_buf.decode("utf-8", errors="replace"))
                        line_buf.clear()
                    self._queue.put(None)
                    # Pause briefly before retrying (stdin might reopen)
                    time.sleep(0.05)
                    continue

                b = byte[0]  # int value of the byte

                if b == 0x03:  # ETX
                    logger.debug("[StdinInterruptMonitor] ETX (0x03) detected")
                    self._inject_interrupt()
                    # Don't append to line buffer – the ETX is consumed
                    continue

                line_buf.extend(byte)

                if b == 0x0A:  # newline (\n) – line complete
                    line_str = line_buf.decode("utf-8", errors="replace")
                    self._queue.put(line_str)
                    line_buf.clear()

            except Exception:
                if not self._running:
                    break
                logger.debug("[StdinInterruptMonitor] Read error in reader loop", exc_info=True)
                time.sleep(0.05)

    # ------------------------------------------------------------------
    # Interrupt delivery
    # ------------------------------------------------------------------

    def _inject_interrupt(self):
        """Deliver a REAL interrupt to the main thread (can interrupt C extensions).

        On Unix/macOS:
            ``os.kill(os.getpid(), signal.SIGINT)`` sends a genuine POSIX
            signal.  This interrupts blocking system calls (``select``,
            ``recv``, ``poll``, …) with ``EINTR``, allowing the custom
            SIGINT handler to fire and raise ``KeyboardInterrupt`` even
            when the main thread is deep inside a C extension (e.g. an
            HTTP client waiting for an LLM API response).

        On Windows:
            ``_thread.interrupt_main()`` triggers Python's internal signal
            mechanism.  This avoids ``os.kill()`` which on Windows maps to
            ``GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)`` – a broadcast
            that would also kill the Node.js parent process.

        Debounce:
            The ``_last_interrupt_time`` is updated by the **SIGINT handler**
            (not here), so a rapid ETX + real-SIGINT from the same keypress
            is collapsed into one ``KeyboardInterrupt``.  This method only
            checks the timestamp to avoid sending redundant signals.
        """
        now = time.monotonic()
        if now - self._last_interrupt_time < self._debounce_interval:
            logger.debug("[StdinInterruptMonitor] Debounced duplicate ETX (within %.2fs)",
                         now - self._last_interrupt_time)
            return

        try:
            if sys.platform == "win32":
                import _thread
                _thread.interrupt_main()
            else:
                os.kill(os.getpid(), signal.SIGINT)
        except Exception as exc:
            logger.error("[StdinInterruptMonitor] Failed to deliver interrupt: %s", exc)


# --------------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------------

def get_stdin_monitor() -> StdinInterruptMonitor:
    """Return the singleton StdinInterruptMonitor, creating it if needed."""
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = StdinInterruptMonitor()
    return _monitor


def start_stdin_monitor():
    """Create and start the singleton monitor."""
    mon = get_stdin_monitor()
    mon.start()
    return mon


def is_monitor_active() -> bool:
    """Return True if the monitor has been started."""
    return _monitor is not None and _monitor._running


def install_sigint_handler():
    """Replace the default SIGINT handler with a debounced version.

    In ACP mode, multiple interrupt sources can fire for a single Ctrl+C:

    1. The frontend writes ETX (``\\x03``) to stdin → the monitor calls
       ``os.kill(SIGINT)`` → this handler fires.
    2. On macOS, the frontend *also* calls ``process.kill('SIGINT')`` →
       this handler fires **again**.

    Without debounce the controller would see two ``KeyboardInterrupt``
    exceptions in quick succession and interpret them as a "double-tap
    exit" request.

    This handler uses the monitor's ``_last_interrupt_time`` as a shared
    debounce timestamp.  Only the **first** SIGINT within the 0.5 s
    window raises ``KeyboardInterrupt``; subsequent duplicates are
    silently ignored.
    """

    def _acp_sigint_handler(signum, frame):
        mon = get_stdin_monitor()
        now = time.monotonic()
        elapsed = now - mon._last_interrupt_time
        if elapsed < mon._debounce_interval:
            logger.debug("[SIGINT handler] Debounced duplicate SIGINT (%.3fs since last)", elapsed)
            return
        # Update timestamp BEFORE raising so that any duplicate arriving
        # while the KeyboardInterrupt propagates is correctly debounced.
        mon._last_interrupt_time = now
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _acp_sigint_handler)
    logger.info("[StdinInterruptMonitor] Custom debounced SIGINT handler installed")
