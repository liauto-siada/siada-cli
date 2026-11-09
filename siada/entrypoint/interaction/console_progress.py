"""Present compatibility progress messages outside tracing callbacks."""

from collections.abc import Callable
from threading import Thread

from siada.foundation.execution_progress import ExecutionProgressChannel
from siada.foundation.logging import logger


def _write_progress(message: str) -> None:
    """Keep progress visible when stdout is redirected to a file or pipe."""
    print(message, flush=True)


class ConsoleProgressPresenter:
    """Own terminal writes for one noninteractive execution.

    A consumer thread keeps progress visible even while the SDK awaits a model
    or a tool without emitting stream events. Closing joins the consumer after
    execution cleanup, so no worker or queued output survives the run.
    """

    def __init__(self, writer: Callable[[str], None] | None = None) -> None:
        self.channel = ExecutionProgressChannel()
        self._writer = writer if writer is not None else _write_progress
        self._thread = Thread(
            target=self._consume, name="siada-console-progress", daemon=True,
        )

    def _consume(self) -> None:
        for message in self.channel.messages():
            try:
                self._writer(message)
            except Exception:
                logger.warning("Failed to write execution progress", exc_info=True)

    def __enter__(self) -> "ConsoleProgressPresenter":
        self._thread.start()
        return self

    def flush(self) -> None:
        self.channel.flush()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.channel.close()
        self._thread.join()