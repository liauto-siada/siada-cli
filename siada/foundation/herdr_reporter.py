"""Report agent lifecycle state to a hosting Herdr pane.

Herdr is a terminal runtime that tracks the state of the coding agents running
inside its panes. A process Herdr hosts inherits ``HERDR_ENV=1``,
``HERDR_PANE_ID`` and ``HERDR_BIN_PATH``, and reports semantic state with
``herdr pane report-agent`` (``idle`` / ``working`` / ``blocked``) plus
``herdr pane release-agent`` to hand back the lifecycle authority when the
agent exits.

This module is deliberately self-contained and defensive:

* Every entry point is a no-op unless the process actually runs inside Herdr,
  so nothing changes for normal CLI, ACP or IM runs.
* Reports never block the agent. They are handed to a background worker thread
  and the herdr CLI call is bounded by a short timeout.
* No failure may reach the agent. Any error (missing binary, herdr gone,
  timeout) is swallowed and only logged at debug level.
"""

from __future__ import annotations

import atexit
import logging
import os
import queue
import subprocess
import threading
import time
from typing import Callable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# `--source` must stay stable and unique to this integration: Herdr keys the
# pane's lifecycle authority by (source, agent) and ignores reports from a
# source that is not the current authority.
SOURCE = "custom:siada"
AGENT_LABEL = "siada"

STATE_IDLE = "idle"
STATE_WORKING = "working"
STATE_BLOCKED = "blocked"
STATE_UNKNOWN = "unknown"
VALID_STATES = frozenset({STATE_IDLE, STATE_WORKING, STATE_BLOCKED, STATE_UNKNOWN})

HERDR_ENV_VAR = "HERDR_ENV"
HERDR_PANE_ID_ENV_VAR = "HERDR_PANE_ID"
HERDR_BIN_PATH_ENV_VAR = "HERDR_BIN_PATH"
DEFAULT_HERDR_BIN = "herdr"

# A report is a local socket round-trip through the herdr CLI. Anything slower
# than this means herdr is wedged, and a stale report is worth less than the
# worker thread staying responsive.
COMMAND_TIMEOUT_SECONDS = 5.0

# Shutdown must stay quick: queued reports and the final release get a much
# shorter budget than a normal report.
EXIT_TIMEOUT_SECONDS = 1.0


def build_report_argv(
    *,
    state: str,
    pane_id: str,
    bin_path: str,
    seq: int,
    message: Optional[str] = None,
    session_id: Optional[str] = None,
) -> List[str]:
    """Build the ``herdr pane report-agent`` command line."""
    argv = [
        bin_path,
        "pane",
        "report-agent",
        pane_id,
        "--source",
        SOURCE,
        "--agent",
        AGENT_LABEL,
        "--state",
        state,
        "--seq",
        str(seq),
    ]
    if message:
        argv.extend(["--message", message])
    if session_id:
        argv.extend(["--agent-session-id", session_id])
    return argv


def build_release_argv(*, pane_id: str, bin_path: str, seq: int) -> List[str]:
    """Build the ``herdr pane release-agent`` command line."""
    return [
        bin_path,
        "pane",
        "release-agent",
        pane_id,
        "--source",
        SOURCE,
        "--agent",
        AGENT_LABEL,
        "--seq",
        str(seq),
    ]


def _run_command(
    argv: Sequence[str], timeout: float = COMMAND_TIMEOUT_SECONDS
) -> None:
    """Run one herdr CLI call, swallowing every failure."""
    try:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": timeout,
            "check": False,
        }
        if os.name == "nt":
            # Keep the report from flashing a console window on Windows.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(list(argv), **kwargs)
    except Exception:
        logger.debug("herdr reporter command failed: %s", argv, exc_info=True)


_pending: "queue.Queue[Optional[Sequence[str]]]" = queue.Queue()
_worker_lock = threading.Lock()
_worker_started = False
# Serializes the actual CLI calls. Reports are asynchronous, but their order
# matters: the release issued at process exit must never overtake a report
# that is still queued or in flight, or herdr would end up with a stale state
# re-established after the release.
_dispatch_lock = threading.Lock()


def _worker_loop() -> None:
    while True:
        argv = _pending.get()
        if argv is None:
            return
        with _dispatch_lock:
            _run_command(argv)


def _flush_pending() -> None:
    """Run every queued report, in order. Caller holds `_dispatch_lock`."""
    while True:
        try:
            argv = _pending.get_nowait()
        except queue.Empty:
            return
        if argv is not None:
            _run_command(argv, timeout=EXIT_TIMEOUT_SECONDS)


def _submit_async(argv: Sequence[str]) -> None:
    """Queue a report for the background worker, starting it on first use."""
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            threading.Thread(
                target=_worker_loop, name="herdr-reporter", daemon=True
            ).start()
            _worker_started = True
    _pending.put(argv)


class HerdrReporter:
    """Builds and dispatches herdr reports for the current process.

    Args:
        env: Environment mapping to read the Herdr variables from. Defaults to
            ``os.environ``.
        runner: Callable that executes one argv. Defaults to the module-level
            background queue; tests inject a recording callable.
    """

    def __init__(
        self,
        env: Optional[Mapping[str, str]] = None,
        runner: Optional[Callable[[Sequence[str]], None]] = None,
    ) -> None:
        self._env = os.environ if env is None else env
        self._runner = _submit_async if runner is None else runner
        self._lock = threading.Lock()
        self._last_seq = 0
        self._reported = False

    def pane_id(self) -> Optional[str]:
        """Return the hosting pane id, or None when not running inside Herdr."""
        if self._env.get(HERDR_ENV_VAR) != "1":
            return None
        pane_id = (self._env.get(HERDR_PANE_ID_ENV_VAR) or "").strip()
        return pane_id or None

    def bin_path(self) -> str:
        return (self._env.get(HERDR_BIN_PATH_ENV_VAR) or "").strip() or DEFAULT_HERDR_BIN

    def available(self) -> bool:
        return self.pane_id() is not None

    def has_reported(self) -> bool:
        return self._reported

    def _next_seq(self) -> int:
        """Return a strictly increasing sequence number.

        Herdr drops reports that are not newer than the last one it accepted
        from the same source, so a report that races with a newer one must not
        be able to overwrite it.
        """
        with self._lock:
            seq = time.time_ns()
            if seq <= self._last_seq:
                seq = self._last_seq + 1
            self._last_seq = seq
            return seq

    def report_state(
        self,
        state: str,
        message: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Report ``idle`` / ``working`` / ``blocked`` for this pane."""
        pane_id = self.pane_id()
        if pane_id is None:
            return
        if state not in VALID_STATES:
            logger.debug("ignoring invalid herdr state: %r", state)
            return
        self._dispatch(
            build_report_argv(
                state=state,
                pane_id=pane_id,
                bin_path=self.bin_path(),
                seq=self._next_seq(),
                message=message,
                session_id=session_id,
            )
        )

    def release(self) -> None:
        """Release this source's lifecycle authority for the pane."""
        pane_id = self.pane_id()
        if pane_id is None:
            return
        self._dispatch(
            build_release_argv(
                pane_id=pane_id, bin_path=self.bin_path(), seq=self._next_seq()
            )
        )

    def _dispatch(self, argv: Sequence[str]) -> None:
        self._reported = True
        try:
            self._runner(argv)
        except Exception:
            logger.debug("herdr reporter dispatch failed", exc_info=True)


reporter = HerdrReporter()


def available() -> bool:
    """True when this process runs inside a Herdr pane."""
    return reporter.available()


def report_state(
    state: str, message: Optional[str] = None, session_id: Optional[str] = None
) -> None:
    """Report agent state to the hosting Herdr pane (no-op outside Herdr)."""
    reporter.report_state(state, message=message, session_id=session_id)


def release() -> None:
    """Release the pane's lifecycle authority (no-op outside Herdr)."""
    reporter.release()


def _release_at_exit() -> None:
    """Hand the pane back to Herdr when the agent process exits.

    Without this, a pane whose agent was killed would keep the last reported
    state (`working` in the worst case) until Herdr noticed the process died.

    Runs synchronously: the background worker is a daemon thread that may
    already be shutting down, so the queue is flushed here first and the
    release is sent last.
    """
    if not reporter.has_reported():
        return
    pane_id = reporter.pane_id()
    if pane_id is None:
        return
    with _dispatch_lock:
        _flush_pending()
        _run_command(
            build_release_argv(
                pane_id=pane_id,
                bin_path=reporter.bin_path(),
                seq=reporter._next_seq(),
            ),
            timeout=EXIT_TIMEOUT_SECONDS,
        )


atexit.register(_release_at_exit)
