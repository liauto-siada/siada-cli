"""Bounded retries for transport and transient API failures."""

from __future__ import annotations

import asyncio
import random
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

import httpx
from agents.exceptions import ModelBehaviorError
from openai import APIConnectionError, APIError, APIStatusError

from siada.foundation.logging import logger

_MAX_RETRIES = 2
_REQUEST_MAX_RETRIES: ContextVar[int | None] = ContextVar("siada_request_max_retries", default=None)
_LIFECYCLE_EVENTS = frozenset({"response.created", "response.in_progress"})
_REASONING_EVENTS = frozenset({
    "response.reasoning_summary_text.delta", "response.reasoning_summary_text.done",
    "response.reasoning_text.delta", "response.reasoning_text.done",
    "response.reasoning_summary_part.added", "response.reasoning_summary_part.done",
})
_MAX_PENDING_EVENTS = 64
_Result = TypeVar("_Result")
_TRANSIENT_API_ERRORS = frozenset({
    "server_error", "internal_server_error", "server_is_overloaded",
    "overloaded_error", "service_unavailable", "rate_limit_exceeded",
    "rate_limit_error", "timeout", "request_timeout",
})
_UPSTREAM_AUTH_ERROR = "gateway cannot authenticate upstream services."


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
    if isinstance(error, APIError):
        # This specific gateway failure concerns upstream credentials and can
        # arrive as an authentication error, including an HTTP 401 response.
        body = error.body
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            body = body["error"]
        message = body.get("message") if isinstance(body, dict) else body
        if not isinstance(message, str):
            message = error.message
        if message.strip().casefold().startswith(_UPSTREAM_AUTH_ERROR):
            return True
    if isinstance(error, APIStatusError):
        return error.status_code in {403, 408, 409, 429} or error.status_code >= 500
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


def _retry_limit() -> int:
    requested = _REQUEST_MAX_RETRIES.get()
    return _MAX_RETRIES if requested is None else min(requested, _MAX_RETRIES)


@contextmanager
def model_retry_scope(num_retries: int | None) -> Iterator[None]:
    """Let durable workflows own retries without forwarding options to the SDK."""
    if num_retries is not None and (type(num_retries) is not int or num_retries < 0):
        raise ValueError("num_retries must be a non-negative integer")
    token = _REQUEST_MAX_RETRIES.set(num_retries)
    try:
        yield
    finally:
        _REQUEST_MAX_RETRIES.reset(token)


async def _backoff(retry_index: int, error: Exception) -> None:
    delay = 2**retry_index + random.uniform(0, 1)
    logger.warning(
        "Model request retry %s/%s after %s; delay=%.2fs; details=%r",
        retry_index + 1, _retry_limit(), type(error).__name__, delay,
        api_error_details(error),
    )
    await asyncio.sleep(delay)


async def retry_model_call(
    call: Callable[..., Awaitable[_Result]], **kwargs: Any
) -> _Result:
    """Retry only the provider call; admission and input processing stay outside."""
    max_retries = _retry_limit()
    for attempt in range(max_retries + 1):
        try:
            return await call(**kwargs)
        except Exception as error:
            if attempt == max_retries or not is_retryable_model_error(error):
                raise
            await _backoff(attempt, error)
    raise AssertionError("Unreachable retry state")


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _is_empty_stream_start(event: Any) -> bool:
    """Buffer only known empty scaffolding; tool and unknown events commit."""
    event_type = _field(event, "type")
    if event_type in _LIFECYCLE_EVENTS:
        return True
    if event_type == "response.output_item.added":
        item = _field(event, "item")
        if _field(item, "type") == "message":
            return (
                _field(item, "role") == "assistant"
                and _field(item, "status") == "in_progress"
                and _field(item, "content") == []
            )
        if _field(item, "type") == "reasoning":
            return (
                _field(item, "summary") == []
                and _field(item, "content") in (None, [])
                and not _field(item, "encrypted_content")
            )
    if event_type == "response.content_part.added":
        part = _field(event, "part")
        return (
            _field(part, "type") == "output_text"
            and _field(part, "text") == ""
            and _field(part, "annotations") == []
        )
    if event_type == "response.reasoning_summary_part.added":
        part = _field(event, "part")
        return _field(part, "type") == "summary_text" and _field(part, "text") == ""
    return False


def is_replay_safe_stream_event(event: Any) -> bool:
    """Allow retries after thinking, but never after answer or tool output.

    Reasoning remains visible while streaming and may repeat across attempts.
    Each new provider iterator owns fresh response assembly state.
    """
    event_type = _field(event, "type")
    if event_type in _REASONING_EVENTS:
        return True
    if event_type in {"response.output_item.added", "response.output_item.done"}:
        if _field(_field(event, "item"), "type") == "reasoning":
            return True
    if event_type in {"response.content_part.added", "response.content_part.done"}:
        if _field(_field(event, "part"), "type") == "reasoning_text":
            return True
    return _is_empty_stream_start(event)


async def retry_model_stream(
    create_stream: Callable[[], AsyncIterator[_Result]],
    *,
    model_name: str | None = None,
) -> AsyncIterator[_Result]:
    """Retry creation/iteration until answer, tool, or unknown events are exposed.

    Buffer empty start events until the first nonempty event or the buffer limit.
    Thinking streams immediately without committing the attempt; a later retry
    emits its own lifecycle events and may display new thinking.
    Hold completed reasoning items until commitment so Runner's empty-output
    fallback cannot persist items belonging to a failed attempt.
    """
    max_retries = _retry_limit()
    for attempt in range(max_retries + 1):
        stream = None
        pending: list[_Result] = []
        pending_reasoning_items: list[_Result] = []
        committed = False
        prefix_exposed = False
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
                if (
                    not committed
                    and event_type == "response.output_item.done"
                    and _field(_field(event, "item"), "type") == "reasoning"
                ):
                    pending_reasoning_items.append(event)
                    continue
                if (
                    not prefix_exposed
                    and len(pending) < _MAX_PENDING_EVENTS
                    and _is_empty_stream_start(event)
                ):
                    pending.append(event)
                    continue
                committed = committed or not is_replay_safe_stream_event(event)
                prefix_exposed = True
                for lifecycle_event in pending:
                    yield lifecycle_event
                pending.clear()
                if committed:
                    for reasoning_item in pending_reasoning_items:
                        yield reasoning_item
                    pending_reasoning_items.clear()
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
            if committed or attempt == max_retries or not is_retryable_model_error(error):
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