"""Transport abstraction for the OpenAI Responses API protocol layer.

``ResponsesModel`` (protocol layer) builds Responses API request params;
a ``ResponsesTransport`` decides how to authenticate and where to send them:

- ``LiProxyResponsesTransport`` (internal build): Li ID auth, X-Siada-*
  tracing headers, sticky-node routing through the Li proxy cluster.
- ``DefaultResponsesTransport`` (open-source default provider): plain
  OpenAI-compatible endpoint configured via ``BASE_URL`` / ``API_KEY``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from openai.types.responses import Response


class ResponsesTransport(ABC):
    """Environment-specific transport for the Responses API."""

    @abstractmethod
    def convert_model_name(self, model: str) -> str:
        """Convert the user-facing model name for this transport's upstream.

        Called at the transport boundary on every request, so environment-
        specific naming rules (e.g. Li proxy's ``covert_to_li_model_name``)
        stay out of the protocol layer.
        """

    @abstractmethod
    async def create(self, **params) -> tuple[Response, dict[str, Any]]:
        """Non-streaming ``responses.create``.

        Args:
            params: Responses API request params built by the protocol layer.

        Returns:
            ``(response, request_body)`` — the request body actually sent,
            for error logging / diagnostics.
        """

    @abstractmethod
    async def create_stream(self, **params) -> tuple[AsyncIterator[Any], dict[str, Any]]:
        """Streaming ``responses.create``.

        Returns:
            ``(event_stream, request_body)`` — native Responses API events.
        """
