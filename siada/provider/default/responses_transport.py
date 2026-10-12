"""Default (open-source) transport for the OpenAI Responses API.

Plain OpenAI-compatible endpoint configured via environment variables:
- ``BASE_URL``: API base URL (optional; SDK default is api.openai.com)
- ``API_KEY``: API key for authentication

Used by ``DefaultProvider`` for Responses-only models (GPT-5.x family),
replacing the previous LiteLLM ``openai/responses/...`` bridge path.
"""
from __future__ import annotations

import os
import threading
from typing import Any, AsyncIterator, Dict

from openai import AsyncOpenAI
from openai.types.responses import Response

from siada.foundation.logging import logger
from siada.provider.responses.transport import ResponsesTransport

# LiteLLM bridge prefixes that must not be sent to a native Responses endpoint.
_BRIDGE_PREFIXES = ("openai/responses/", "responses/")


class DefaultResponsesTransport(ResponsesTransport):
    """Responses API transport for the open-source default provider."""

    def __init__(self):
        # NOTE: credentials may be (re)configured at runtime by login flows,
        # so the AsyncOpenAI client is built lazily and rebuilt when the
        # resolved (base_url, api_key) pair changes.
        self._client: AsyncOpenAI | None = None
        self._client_key: tuple[str | None, str | None] | None = None
        self._retired_clients: list[AsyncOpenAI] = []
        self._lock = threading.Lock()
        self._closed = False

    def convert_model_name(self, model: str) -> str:
        """Strip LiteLLM responses-bridge prefixes; send the real model name."""
        if not model:
            return model
        for prefix in _BRIDGE_PREFIXES:
            if model.startswith(prefix):
                return model.removeprefix(prefix)
        return model

    def _get_client(self) -> AsyncOpenAI:
        with self._lock:
            if self._closed:
                raise RuntimeError("DefaultResponsesTransport is closed")

            base_url = os.getenv("BASE_URL") or None
            api_key = os.getenv("API_KEY") or None
            if not api_key:
                raise ValueError(
                    "API_KEY is required for Responses-API-only models (e.g. gpt-5.x) "
                    "on the default provider. Set API_KEY (and optionally BASE_URL)."
                )

            key = (base_url, api_key)
            if self._client is None or self._client_key != key:
                if self._client is not None:
                    self._retired_clients.append(self._client)
                self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                self._client_key = key
            return self._client

    async def aclose(self) -> None:
        """Close every client this transport owns, including retired ones.

        Failures never stop the remaining clients from closing; a single error
        is re-raised as-is and several are aggregated into an ExceptionGroup.

        ``_closed`` still marks the transport as shutting down (no new client is
        built afterwards), but ownership follows the stricter rule: a cancelled
        ``aclose`` (``asyncio.CancelledError`` is a ``BaseException``, so it is
        not an ordinary close failure) propagates unchanged and re-owns the
        clients whose close it did not confirm — including the interrupted one —
        so a later ``aclose()`` still closes them instead of returning early and
        leaking them.
        """
        with self._lock:
            if self._closed and self._client is None and not self._retired_clients:
                return
            self._closed = True

            clients = list(self._retired_clients)
            self._retired_clients.clear()
            if self._client is not None:
                clients.append(self._client)
                self._client = None
                self._client_key = None

        errors: list[Exception] = []
        for index, client in enumerate(clients):
            try:
                await client.close()
            except Exception as exc:
                errors.append(exc)
            except BaseException:
                # Cancellation must reach the caller, but the clients this call
                # has not closed yet must not be detached with it.
                self._restore_clients(clients[index:])
                raise

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup(
                "Failed to close one or more default Responses clients",
                errors,
            )

    def _restore_clients(self, clients: list[AsyncOpenAI]) -> None:
        """Return unconfirmed clients to the retired list, oldest first.

        Restored clients never become the active one again (a closed transport
        builds no new client), so re-owning them only means that a later
        ``aclose()`` still sees them.
        """
        if not clients:
            return
        with self._lock:
            self._retired_clients = [*clients, *self._retired_clients]

    def _prepare_params(self, caller: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str] | None]:
        params.pop("max_tokens", None)
        params["model"] = self.convert_model_name(params.get("model", ""))
        caller_extra_headers = params.pop("extra_headers", None)
        logger.info(f"DefaultResponsesTransport: {caller} called, model={params['model']}")
        return params, caller_extra_headers

    async def create(self, **params) -> tuple[Response, Dict[str, Any]]:
        request_params, extra_headers = self._prepare_params("create", params)
        client = self._get_client()
        try:
            response = await client.responses.create(**request_params, extra_headers=extra_headers)
            return response, request_params
        except Exception as e:
            logger.error(f"DefaultResponsesTransport error: {e}")
            raise

    async def create_stream(self, **params) -> tuple[AsyncIterator[Any], Dict[str, Any]]:
        request_params, extra_headers = self._prepare_params("create_stream", params)
        request_params["stream"] = True
        client = self._get_client()
        try:
            stream = await client.responses.create(**request_params, extra_headers=extra_headers)
            return stream, request_params
        except Exception as e:
            logger.error(f"DefaultResponsesTransport streaming error: {e}")
            raise
