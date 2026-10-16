"""Event-loop ownership checks for asynchronous model connection pools."""

import asyncio
import weakref


class EventLoopOwnership:
    """Bind on first loop access; callers serialize checks with their cache lock."""

    def __init__(self) -> None:
        self._owner: weakref.ReferenceType | None = None

    def check(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if self._owner is not None:
                raise RuntimeError("Model client must be used on its owning event loop")
            # Model construction may occur in synchronous configuration code.
            return
        if self._owner is None:
            self._owner = weakref.ref(loop)
        elif self._owner() is not loop:
            raise RuntimeError("Model client belongs to a different event loop")
