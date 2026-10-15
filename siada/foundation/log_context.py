"""Log attribution scoped to tasks; child tasks inherit their owner's context."""

from contextlib import contextmanager
from functools import wraps
import inspect
from typing import Any, Callable, Iterator
from uuid import uuid4

from siada.foundation.context import (
    AGENT_NAME, SESSION_ID, context_dict_var, get_context_var,
)

REQUEST_ID = "request_id"
AGENT_RUN_ID = "agent_run_id"


def log_fields() -> dict[str, str]:
    """Return stable correlation fields without including conversation content."""
    return {
        "sessionId": str(get_context_var(SESSION_ID) or "-"),
        "requestId": str(get_context_var(REQUEST_ID) or "-"),
        "agent": str(get_context_var(AGENT_NAME) or "-"),
        "agentRunId": str(get_context_var(AGENT_RUN_ID) or "-"),
    }


@contextmanager
def log_scope(
    *, session_id: str | None = None, request_id: str | None = None,
    agent: str | None = None, agent_run_id: str | None = None,
) -> Iterator[None]:
    # A fresh dictionary prevents in-place SDK hook updates affecting siblings.
    values = dict(context_dict_var.get())
    for key, value in (
        (SESSION_ID, session_id), (REQUEST_ID, request_id),
        (AGENT_NAME, agent), (AGENT_RUN_ID, agent_run_id),
    ):
        if value is not None:
            values[key] = str(value)
    token = context_dict_var.set(values)
    try:
        yield
    finally:
        context_dict_var.reset(token)


def logged_request(func: Callable[..., Any]) -> Callable[..., Any]:
    """Scope a request entry point, including exceptions and background tasks."""
    signature = inspect.signature(func)

    @wraps(func)
    async def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        session = bound.arguments.get("session")
        session_id = bound.arguments.get("session_id") or getattr(session, "session_id", None)
        extra = bound.arguments.get("_", {})
        meta = extra.get("_meta") or extra.get("meta") or {}
        logging_meta = meta.get("siadaLog", {}) if isinstance(meta, dict) else {}
        if not isinstance(logging_meta, dict):
            logging_meta = {}
        request_id = logging_meta.get("requestId") or get_context_var(REQUEST_ID) or uuid4().hex
        owner = bound.arguments.get("self")
        agent = bound.arguments.get("agent_name") or getattr(
            getattr(owner, "_turn_runner", None), "_agent_name", None,
        )
        with log_scope(session_id=session_id, request_id=request_id,
                       agent=agent):
            return await func(*args, **kwargs)
    return wrapped


def logged_agent(agent_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Attribute setup, SDK work and cleanup of a background agent pipeline."""
    def decorate(func):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            with log_scope(agent=agent_name,
                           request_id=get_context_var(REQUEST_ID) or uuid4().hex,
                           agent_run_id=uuid4().hex):
                return await func(*args, **kwargs)
        return wrapped
    return decorate