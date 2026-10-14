"""Task-local endpoint credentials for standalone default-provider requests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_REQUEST_CREDENTIALS: ContextVar[tuple[str | None, str | None] | None] = ContextVar(
    "siada_request_credentials", default=None
)


def get_default_credentials() -> tuple[str | None, str | None]:
    """Resolve request overrides without changing process-wide credentials."""
    base_url = os.getenv("BASE_URL") or None
    api_key = os.getenv("API_KEY") or None
    override = _REQUEST_CREDENTIALS.get()
    if override is not None:
        base_url = override[0] if override[0] is not None else base_url
        api_key = override[1] if override[1] is not None else api_key
    return base_url, api_key


def has_request_credentials() -> bool:
    """Distinguish independent endpoints from normal runtime reconfiguration."""
    return _REQUEST_CREDENTIALS.get() is not None


@contextmanager
def default_credentials_scope(
    *, base_url: str | None = None, api_key: str | None = None
) -> Iterator[None]:
    """Borrow provider-owned clients for one task's independent endpoint."""
    token = _REQUEST_CREDENTIALS.set((base_url, api_key))
    try:
        yield
    finally:
        _REQUEST_CREDENTIALS.reset(token)