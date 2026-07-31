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

import collections
import json
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

# ---------------------------------------------------------------------------
# Pending user-input injection queue
#
# When the agent is mid-turn (running LLM + tool loops), messages arriving
# from the frontend are diverted here instead of _queue.  The
# PendingUserInputInjector filter drains this deque before every LLM call
# and injects the messages into the model input + FileSession.
# If the turn ends before they are consumed, set_agent_running(False) flushes
# them back to _queue so Controller.run() picks them up as a new turn.
# ---------------------------------------------------------------------------
_pending_injections: collections.deque = collections.deque()
_pending_injections_lock = threading.Lock()
_agent_running: bool = False

# Upper bound for the pending-injection deque. A runaway frontend (e.g. a send
# loop) could otherwise grow this unbounded. When full we drop the OLDEST item
# and emit a warning rather than silently relying on deque(maxlen=...), so the
# loss is observable in logs.
_PENDING_MAX = 100


# ACP notification callback registered by Controller.
# Signature: callback(method: str, params: dict) -> None
_acp_notify_callback = None


def register_acp_notify(callback) -> None:
    """Register a callback for sending ACP notifications.

    Called by Controller during startup when ACP mode is active.
    Signature: callback(method: str, params: dict) -> None
    """
    global _acp_notify_callback
    _acp_notify_callback = callback


def _send_queue_notification(reason: str, metadata: dict) -> None:
    """Send a queue-related ACP notification via the registered callback.

    Wraps with error handling so notification failures never crash
    the reader loop or filter pipeline.
    """
    if _acp_notify_callback is None:
        return
    try:
        _acp_notify_callback(
            "session/update",
            {"reason": reason, "content": "", "metadata": metadata},
        )
    except Exception as exc:
        logger.warning("[StdinInterruptMonitor] Failed to send queue notification: %s", exc)


def _merge_flushed_prompts(contents: list) -> str:
    """Merge multiple flushed prompts into a SINGLE turn body.

    Flushed prompts are messages the user queued WHILE the previous turn was
    still running but which the mid-turn injector never consumed. The agent
    runs one user turn at a time, so we combine them into one message.

    - A single prompt is returned verbatim (no wrapper) so the common case is
      indistinguishable from a normal message.
    - Multiple prompts get a short, neutral note saying they were queued while
      the previous response was running, plus an index per message so a bare
      newline between two independent messages is not misread as one. We
      deliberately avoid prescribing HOW the model should handle them (e.g.
      "address all of them") — that over-constrains behaviour and does not
      match how a normal user message would be treated.
    """
    if len(contents) == 1:
        return contents[0]

    numbered = "\n\n".join(
        f"[{i + 1}] {c}" for i, c in enumerate(contents)
    )
    header = (
        "The following messages were queued while you were working on the "
        "previous response, listed in the order they were sent:"
    )
    return f"{header}\n\n{numbered}"


def set_agent_running(running: bool) -> None:

    """Called by Controller to mark whether an agent turn is in progress."""

    global _agent_running

    # The flag write and the deque snapshot/clear MUST happen in the same
    # critical section as the reader thread's "check flag + append"
    # (see _dispatch_or_enqueue). Otherwise a TOCTOU gap exists: the reader
    # could observe _agent_running==True, then this function flips it to False
    # and flushes the deque, and only afterwards the reader appends — leaving a
    # stale item behind that leaks into the next turn.
    #
    # Track (id, content) pairs so the consume notification can carry the
    # original prompt text; the frontend uses it as a fallback to render the
    # user bubble even if its local preview queue was already cleared.
    flushed_items: list = []
    contents: list = []
    with _pending_injections_lock:
        _agent_running = running
        if not running:
            while _pending_injections:
                _id, content, _image_paths = _pending_injections.popleft()
                if content:
                    contents.append(content)
                if _id:
                    flushed_items.append((_id, content))

    if running:
        return

    # Everything below runs OUTSIDE the lock to avoid holding it during I/O
    # (queue puts + ACP notifications). The snapshot above is already complete
    # and consistent, so no further synchronization is required here.
    #
    # Flush any un-injected messages back to _queue for normal processing.
    # These items were queued late in the turn (after the last LLM call) so the
    # injector never consumed them; they will now be picked up by
    # Controller.run() as a fresh turn. Notify the frontend for each so it
    # renders the prompt into the main conversation (the same "consumed"
    # treatment as a mid-turn injection) and removes it from the preview.
    monitor = get_stdin_monitor()
    if monitor is not None and contents:
        # Merge all flushed prompts into a SINGLE new turn so the agent runs
        # them together in one pass. When there are multiple, _merge_flushed_prompts
        # prefixes an explicit header explaining that these are user messages that
        # were queued while the previous turn was running, and lists them in
        # arrival order — so the model treats them as separate requests rather
        # than misreading several instructions glued together as one.
        #
        # IMPORTANT: frame the merged prompt with the SIADA_MSG_START/END markers
        # exactly like a normal ACP message. IO.get_input() in ACP mode DISCARDS
        # any queue line that does not begin with the SIADA_MSG_START marker, so
        # an unframed raw string would silently be dropped and the agent would
        # never run the flushed prompt.
        merged = _merge_flushed_prompts(contents)
        monitor._queue.put("<<<SIADA_MSG_START>>>\n")
        monitor._queue.put(merged + "\n")
        monitor._queue.put("<<<SIADA_MSG_END>>>\n")
    for _id, content in flushed_items:


        _send_queue_notification(
            "queue_item_consumed", {"id": _id, "content": content}
        )





def drain_pending_injections() -> list:
    """Drain all pending injection items.

    Returns list of (id, content, image_paths) tuples.
    ``id`` may be None when the item was enqueued by an older frontend
    that does not send queue_id.
    """
    with _pending_injections_lock:
        items = list(_pending_injections)
        _pending_injections.clear()
    return items


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
        # Optional callback for /btw interception during agent turns.
        # Signature: handler(question: str) -> None  (called in a new daemon thread)
        self._btw_handler = None

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

    def set_btw_handler(self, handler) -> None:
        """Register a callback invoked when a /btw message is intercepted.

        handler(question: str) -> None — called in a new daemon thread so
        the reader loop is never blocked.  Pass None to disable.
        """
        self._btw_handler = handler

    def _handle_cancel_pending(self) -> None:
        """Drain _pending_injections without processing them.

        Called when the frontend sends queue/cancelPending (typically just
        before ETX / Ctrl+C) to prevent flushed items from being picked up
        as a new agent turn after the current turn is interrupted.
        """
        with _pending_injections_lock:
            count = len(_pending_injections)
            _pending_injections.clear()
        logger.info(
            "[StdinInterruptMonitor] queue/cancelPending: cleared %d pending injection(s)",
            count,
        )

    @staticmethod
    def _extract_message_body(msg_lines: list) -> str:
        """Return the JSON/text body sitting between the START/END marker lines."""
        return "".join(l.rstrip("\n") for l in msg_lines[1:-1])

    @staticmethod
    def _parse_control_notification(body: str):
        """Parse ``body`` as JSON and return it only if it is a *control*
        JSON-RPC notification — i.e. it has a ``method`` key, no ``id`` key
        (JSON-RPC notifications never carry an id), and carries NO usable
        prompt text in ``params.prompt`` / top-level ``prompt``.

        Returns the parsed dict for a genuine control notification (e.g.
        ``session/pullHistory``, ``session/pullHistoryDone`` echoes, future
        control signals, ...), or ``None`` if ``body`` is not JSON, is not a
        notification, or does carry a real prompt (in which case it must be
        handled as a normal / /btw prompt by the caller, not dropped here).
        """
        body_stripped = body.strip()
        if not body_stripped.startswith("{"):
            return None
        try:
            parsed = json.loads(body)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        if "method" not in parsed or "id" in parsed:
            return None
        params = parsed.get("params", {})
        has_prompt = bool(
            (isinstance(params, dict) and params.get("prompt"))
            or parsed.get("prompt")
        )
        if has_prompt:
            return None
        return parsed

    def _dispatch_or_enqueue(self, msg_lines: list) -> None:
        """Route a complete ACP message.

        If the message is a /btw prompt and a btw_handler is registered,
        dispatch to the handler in a new thread (without enqueuing).
        Otherwise put all lines into _queue for get_input() to consume.
        """
        # Handle queue/cancelPending before any other routing.
        if len(msg_lines) >= 3:
            body = self._extract_message_body(msg_lines)
            body_stripped = body.strip()
            if body_stripped.startswith("{"):
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and parsed.get("method") == "queue/cancelPending":
                        self._handle_cancel_pending()
                        return
                except Exception:
                    pass

        # BUGFIX: drop control JSON-RPC *notifications* (e.g. session/pullHistory)
        # before they can ever be mistaken for prompt text.
        #
        # The Node.js adapter frames BOTH real prompts and lightweight control
        # signals (session/pullHistory, ...) identically: `<<<SIADA_MSG_START>>>`
        # + a JSON-RPC body + `<<<SIADA_MSG_END>>>`. A JSON-RPC *notification*
        # (has "method", no "id") that carries no "prompt" field — such as
        # `{"jsonrpc":"2.0","method":"session/pullHistory","params":{}}` — used
        # to fall through both the /btw-detection block below AND the mid-turn
        # prompt_text extraction block, because both of them fell back to
        # `body_stripped` (i.e. the RAW JSON TEXT) whenever no "prompt" field was
        # found. That raw JSON was then treated as if the user had typed it:
        # either injected mid-turn via _pending_injections, or queued as a brand
        # new turn — visibly leaking `{"jsonrpc":"2.0","method":"session/..."}`
        # into the conversation and confusing the model.
        #
        # Such notifications are fire-and-forget signals for the frontend (it
        # already has its own timeout fallback, e.g. pullHistoryDone), so the
        # safe and correct behaviour is to simply drop them here — never enqueue
        # them, never inject them, never treat them as a /btw question.
        if len(msg_lines) >= 3:
            body = self._extract_message_body(msg_lines)
            control = self._parse_control_notification(body)
            if control is not None:
                logger.info(
                    "[StdinInterruptMonitor] Dropping control notification "
                    "(method=%r) — not a prompt, never enqueued/injected",
                    control.get("method"),
                )
                return

        if self._btw_handler and len(msg_lines) >= 3:
            # Content sits between the START and END marker lines
            body = self._extract_message_body(msg_lines)
            body_stripped = body.strip()

            # Two payload shapes are written from the Node.js adapter:
            #   1. JSON envelope (e.g. { "params": { "prompt": "/btw ..." } })
            #      — used when image_paths or other structured fields exist.
            #   2. Raw prompt text — the default for a plain text message.
            # We must intercept /btw in BOTH shapes; otherwise the prompt
            # falls through to the main controller and triggers
            # `processing_started` (the main thinking spinner), which is
            # exactly what /btw is supposed to avoid.
            #
            # NOTE: control notifications (no "prompt" field) are already
            # filtered out above, so a JSON envelope reaching this point either
            # carries a real "prompt" or this is a plain-text (non-JSON)
            # payload — never a raw control-notification body.
            intercepted_prompt = None

            if body_stripped.startswith("{"):
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        params = parsed.get("params", {})
                        if isinstance(params, dict):
                            intercepted_prompt = params.get("prompt", "") or ""
                        # Some adapter versions stringify {prompt, image_paths}
                        # at the top level rather than under params.
                        if not intercepted_prompt:
                            intercepted_prompt = parsed.get("prompt", "") or ""
                except Exception:
                    intercepted_prompt = None  # JSON parse error — try raw

            if not intercepted_prompt:
                # Raw text payload (no JSON wrapper).
                intercepted_prompt = body_stripped

            trimmed_prompt = (intercepted_prompt or "").strip()
            if trimmed_prompt == "/btw" or trimmed_prompt.startswith("/btw "):
                question = trimmed_prompt[4:].strip()
                logger.info(
                    "[StdinInterruptMonitor] Intercepted /btw: %r",
                    question[:80],
                )
                handler = self._btw_handler
                threading.Thread(
                    target=handler,
                    args=(question,),
                    daemon=True,
                    name="btw-interceptor",
                ).start()
                return  # consumed — do not enqueue

        # When the agent is mid-turn, divert non-/btw messages to the
        # injection queue so PendingUserInputInjector can inject them before
        # the next LLM call, rather than queuing them for a new turn.
        #
        # Parse the prompt OUTSIDE the lock first (JSON parsing can be slow);
        # we only need the cleaned text/fields when diverting to the injection
        # queue. The actual "check flag + append" decision then happens inside
        # a single critical section so it is atomic w.r.t. set_agent_running()'s
        # flag write + flush. Reading _agent_running outside the lock and
        # appending later would reintroduce the TOCTOU gap where a late append
        # survives the end-of-turn flush and leaks into the next turn.
        #
        # NOTE: control notifications without a "prompt" field are already
        # filtered out above, so — same as the /btw block — a JSON envelope
        # reaching this point is either a real prompt-carrying JSON envelope or
        # a plain-text payload, never a raw control-notification body.
        prompt_text = None
        image_paths = None
        queue_id = None
        if len(msg_lines) >= 3:
            body = self._extract_message_body(msg_lines)
            body_stripped = body.strip()
            if body_stripped.startswith("{"):
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        params = parsed.get("params", {})
                        prompt_text = (
                            (params.get("prompt") if isinstance(params, dict) else None)
                            or parsed.get("prompt")
                            or ""
                        )
                        image_paths = (
                            (params.get("image_paths") if isinstance(params, dict) else None)
                            or parsed.get("image_paths")
                        )
                        queue_id = (
                            (params.get("queue_id") if isinstance(params, dict) else None)
                            or parsed.get("queue_id")
                        )
                except Exception:
                    prompt_text = body_stripped
            if not prompt_text:
                prompt_text = body_stripped

        if prompt_text:
            with _pending_injections_lock:
                if _agent_running:
                    # Bound the deque so a runaway frontend cannot grow it
                    # without limit; drop the oldest item (with a log) when full.
                    if len(_pending_injections) >= _PENDING_MAX:
                        logger.warning(
                            "[StdinInterruptMonitor] pending injections full (%d), dropping oldest",
                            _PENDING_MAX,
                        )
                        _pending_injections.popleft()
                    _pending_injections.append((queue_id, prompt_text, image_paths))
                    logger.info(
                        "[StdinInterruptMonitor] Queued mid-turn injection: %r (queue_id=%r)",
                        prompt_text[:80],
                        queue_id,
                    )
                    return  # consumed inside the lock — no TOCTOU gap

        # Normal message: put all lines back for get_input() to assemble
        for line in msg_lines:
            self._queue.put(line)



    # ------------------------------------------------------------------
    # Background thread – byte-level reading
    # ------------------------------------------------------------------

    def _reader_loop(self):
        """Continuously read bytes from stdin, detect ETX immediately, reconstruct lines.

        Unlike readline(), reading byte-by-byte ensures that a bare \\x03
        (without a trailing newline) is detected instantly.

        ACP messages are framed with <<<SIADA_MSG_START>>> / <<<SIADA_MSG_END>>>
        markers.  Complete messages are passed to _dispatch_or_enqueue() which
        either intercepts /btw commands (calling the registered handler) or puts
        all lines back into _queue for get_input() to consume as normal.
        """
        line_buf = bytearray()
        # Use the raw binary buffer to avoid text-mode line buffering
        raw = sys.stdin.buffer

        # ACP message assembly state
        _in_msg = False
        _msg_lines = []  # accumulated raw lines (including \n) within START/END

        while self._running:
            try:
                byte = raw.read(1)
                if not byte:
                    # EOF – flush any partial line, then push sentinel
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
                    # ETX is consumed; abandon any partial message assembly
                    if _in_msg:
                        _in_msg = False
                        _msg_lines = []
                    continue

                line_buf.extend(byte)

                if b == 0x0A:  # newline (\n) – line complete
                    line_str = line_buf.decode("utf-8", errors="replace")
                    line_buf.clear()

                    stripped = line_str.strip()
                    if stripped == "<<<SIADA_MSG_START>>>":
                        # Start of a framed ACP message
                        _in_msg = True
                        _msg_lines = [line_str]
                    elif _in_msg:
                        _msg_lines.append(line_str)
                        if stripped == "<<<SIADA_MSG_END>>>":
                            # Complete message assembled — route it
                            _in_msg = False
                            self._dispatch_or_enqueue(_msg_lines)
                            _msg_lines = []
                    else:
                        # Bare line outside START/END (e.g. non-ACP plain input)
                        self._queue.put(line_str)

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
