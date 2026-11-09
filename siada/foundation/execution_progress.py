"""Run-local progress messages with no dependency on terminal presentation."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from queue import Queue
from threading import Lock


class ExecutionProgressChannel:
    """Keep immutable messages FIFO across an execution's tasks and threads.

    The presentation owner closes the channel after execution cleanup. Tasks
    retaining an inherited context cannot publish into a later run or keep a
    closed channel growing. The queue is intentionally lossless while active.
    """

    def __init__(self) -> None:
        self._messages: Queue[str | None] = Queue()
        self._lock = Lock()
        self._closed = False

    def publish(self, message: str) -> None:
        with self._lock:
            if not self._closed:
                self._messages.put(message)

    def messages(self) -> Iterator[str]:
        while True:
            message = self._messages.get()
            try:
                if message is None:
                    return
                yield message
            finally:
                self._messages.task_done()

    def flush(self) -> None:
        """Wait until the presentation consumer has written queued messages."""
        self._messages.join()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._messages.put(None)


_CURRENT_CHANNEL: ContextVar[ExecutionProgressChannel | None] = ContextVar(
    "execution_progress_channel", default=None,
)


def publish_execution_progress(message: str) -> None:
    """Publish data only; unowned executions have no console side effects."""
    channel = _CURRENT_CHANNEL.get()
    if channel is not None:
        channel.publish(message)


@contextmanager
def execution_progress_scope(channel: ExecutionProgressChannel | None) -> Iterator[None]:
    """Propagate the owner's channel into streamed and nested SDK tasks."""
    token = _CURRENT_CHANNEL.set(channel)
    try:
        yield
    finally:
        _CURRENT_CHANNEL.reset(token)