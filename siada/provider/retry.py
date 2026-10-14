"""Bounded transport retries around model calls and stream consumption."""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
from agents.exceptions import ModelBehaviorError
from openai import APIConnectionError

from siada.foundation.logging import logger

_MAX_RETRIES = 2
_LIFECYCLE_EVENTS = frozenset({"response.created", "response.in_progress"})
_Result = TypeVar("_Result")


class MissingFinalResponseError(ModelBehaviorError):
    """A model stream reached EOF without a terminal response event."""

    def __init__(
        self,
        *,
        model: str | None,
        response_id: str | None,
        last_event: str | None,
        output_exposed: bool,
    ) -> None:
        super().__init__("Model response stream ended without a final response.")
        self.model = model
        self.response_id = response_id
        self.last_event = last_event
        self.output_exposed = output_exposed


def is_retryable_model_error(error: Exception) -> bool:
    """Recognize missing completion before output and typed transport failures."""
    if isinstance(error, MissingFinalResponseError):
        return not error.output_exposed
    return is_retryable_transport_error(error)


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
    *,
    model_name: str | None = None,
) -> AsyncIterator[_Result]:
    """Retry creation/iteration until the first non-lifecycle event is exposed.

    Buffer lifecycle events so failed attempts cannot leak response IDs. Once
    output/tool events are exposed, replay could duplicate content or actions.
    """
    for attempt in range(_MAX_RETRIES + 1):
        stream = None
        pending: list[_Result] = []
        committed = False
        terminal_seen = False
        response_id = None
        last_event = None
        retry_error: Exception | None = None
        try:
            stream = create_stream()
            async for event in stream:
                event_type = (
                    event.get("type") if isinstance(event, dict)
                    else getattr(event, "type", None)
                )
                last_event = event_type
                response = (
                    event.get("response") if isinstance(event, dict)
                    else getattr(event, "response", None)
                )
                response_id = (
                    response.get("id") if isinstance(response, dict)
                    else getattr(response, "id", None)
                ) or response_id
                # Explicit failures retain their own SDK error handling.
                if event_type in {"response.completed", "response.incomplete", "response.failed"}:
                    terminal_seen = True
                if not committed and event_type in _LIFECYCLE_EVENTS:
                    pending.append(event)
                    continue
                committed = True
                for lifecycle_event in pending:
                    yield lifecycle_event
                pending.clear()
                yield event
            if not terminal_seen:
                logger.error(
                    "Model stream ended without a final response: model=%s "
                    "response_id=%s last_event=%s output_exposed=%s",
                    model_name, response_id, last_event, committed,
                )
                raise MissingFinalResponseError(
                    model=model_name, response_id=response_id,
                    last_event=last_event, output_exposed=committed,
                )
            return
        except Exception as error:
            if committed or attempt == _MAX_RETRIES or not is_retryable_model_error(error):
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