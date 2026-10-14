"""Bounded retries for transport and transient API failures."""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
from agents.exceptions import ModelBehaviorError
from openai import APIConnectionError, APIError, APIStatusError

from siada.foundation.logging import logger

_MAX_RETRIES = 2
_LIFECYCLE_EVENTS = frozenset({"response.created", "response.in_progress"})
_Result = TypeVar("_Result")
_TRANSIENT_API_ERRORS = frozenset({
    "server_error", "internal_server_error", "server_is_overloaded",
    "overloaded_error", "service_unavailable", "rate_limit_exceeded",
    "rate_limit_error", "timeout", "request_timeout",
})


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


def api_error_details(error: Exception) -> dict[str, Any]:
    """Extract bounded diagnostic fields without logging requests or full bodies."""
    body = getattr(error, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    details: dict[str, Any] = {"exception": type(error).__name__}
    for key in ("message", "code", "type", "param"):
        value = body.get(key) if isinstance(body, dict) else None
        if value is None and not (
            key == "message" and isinstance(error, APIError) and body is not None
        ):
            value = getattr(error, key, None)
        if isinstance(value, (str, int, float, bool)):
            details[key] = value[:512] if isinstance(value, str) else value
    details.setdefault(
        "message",
        "API error without a structured message"
        if isinstance(error, APIError) and body is not None else str(error)[:512],
    )
    response = getattr(error, "response", None)
    request = error.request if isinstance(error, APIError) else None
    details["status_code"] = getattr(error, "status_code", None)
    details["request_id"] = (
        getattr(error, "request_id", None)
        or (response.headers.get("x-request-id") if response is not None else None)
    )
    details["trace_id"] = (
        request.headers.get("siada-trace-id") or request.headers.get("uuid")
        if request is not None else None
    )
    return details


def is_retryable_model_error(error: Exception) -> bool:
    """Retry transient API failures as well as typed transport failures."""
    if isinstance(error, MissingFinalResponseError):
        return not error.output_exposed
    if is_retryable_transport_error(error):
        return True
    if isinstance(error, APIStatusError):
        return error.status_code in {408, 409, 429} or error.status_code >= 500
    if not isinstance(error, APIError):
        return False
    details = api_error_details(error)
    code = details.get("code")
    error_type = details.get("type")
    # Explicit codes take precedence, so quota/parameter errors cannot be
    # retried merely because a gateway also labels them as server errors.
    if code:
        return code in _TRANSIENT_API_ERRORS
    if error_type:
        return error_type in _TRANSIENT_API_ERRORS
    return str(error).strip().casefold() == "unknown stream error"


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
        "Model request retry %s/%s after %s; delay=%.2fs; details=%r",
        retry_index + 1, _MAX_RETRIES, type(error).__name__, delay,
        api_error_details(error),
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
            if attempt == _MAX_RETRIES or not is_retryable_model_error(error):
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