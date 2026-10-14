"""Bounded transport retries around model calls and stream consumption."""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
from openai import APIConnectionError

from siada.foundation.logging import logger

_MAX_RETRIES = 2
_LIFECYCLE_EVENTS = frozenset({"response.created", "response.in_progress"})
_Result = TypeVar("_Result")


def is_retryable_transport_error(error: Exception) -> bool:
    """Recognize typed transport failures without retrying arbitrary parser bugs."""
    if isinstance(error, (
        TimeoutError, APIConnectionError, httpx.TimeoutException,
        httpx.NetworkError, httpx.RemoteProtocolError,
    )):
        return True
    # An existing LiteLLM exception implies its module has already been loaded.
    # This also recognizes provider-defined subclasses without a heavy import.
    exceptions = sys.modules.get("litellm.exceptions")
    if exceptions is not None:
        return isinstance(error, (
            exceptions.APIConnectionError, exceptions.MidStreamFallbackError,
            exceptions.Timeout,
        ))
    return False


async def _backoff(retry_index: int, error: Exception) -> None:
    delay = 2**retry_index + random.uniform(0, 1)
    logger.warning(
        "Model transport retry %s/%s after %s; delay=%.2fs",
        retry_index + 1, _MAX_RETRIES, type(error).__name__, delay,
    )
    await asyncio.sleep(delay)


async def retry_model_call(
    call: Callable[..., Awaitable[_Result]], **kwargs: Any
) -> _Result:
    """Retry only the provider call; admission and input processing stay outside."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await call(**kwargs)
        except Exception as error:
            if attempt == _MAX_RETRIES or not is_retryable_transport_error(error):
                raise
            await _backoff(attempt, error)
    raise AssertionError("Unreachable retry state")


async def retry_model_stream(
    create_stream: Callable[[], AsyncIterator[_Result]],
) -> AsyncIterator[_Result]:
    """Retry creation/iteration until the first non-lifecycle event is exposed.

    Buffer lifecycle events so failed attempts cannot leak response IDs. Once
    output/tool events are exposed, replay could duplicate content or actions.
    """
    for attempt in range(_MAX_RETRIES + 1):
        stream = None
        pending: list[_Result] = []
        committed = False
        retry_error: Exception | None = None
        try:
            stream = create_stream()
            async for event in stream:
                event_type = (
                    event.get("type") if isinstance(event, dict)
                    else getattr(event, "type", None)
                )
                if not committed and event_type in _LIFECYCLE_EVENTS:
                    pending.append(event)
                    continue
                committed = True
                for lifecycle_event in pending:
                    yield lifecycle_event
                pending.clear()
                yield event
            for lifecycle_event in pending:
                yield lifecycle_event
            return
        except Exception as error:
            if committed or attempt == _MAX_RETRIES or not is_retryable_transport_error(error):
                raise
            retry_error = error
        finally:
            close = getattr(stream, "aclose", None)
            if close is None:
                close = getattr(stream, "close", None)
            if callable(close):
                await close()
        # Close the failed stream before waiting or opening another request.
        assert retry_error is not None
        await _backoff(attempt, retry_error)