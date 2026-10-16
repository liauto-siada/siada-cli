"""Default-provider transport for OpenAI Chat Completions-compatible APIs."""

from __future__ import annotations

import os
import threading
from typing import Any

from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from siada.foundation.constants import LLM_API_POST_TIMEOUT
from siada.provider.chat_completions import (
    KimiToolOrderingMixin,
    RefreshingOpenAIClientMixin,
)
from siada.provider.default.coverter import covert_to_litellm_model_name
from siada.provider.lifecycle import EventLoopOwnership


_LITELLM_ROUTING_PREFIXES = frozenset(
    {"openai", "deepseek", "moonshot", "moonshotai", "moonshotai-cn", "minimax"}
)
_NATIVE_ONLY_PREFIXES = frozenset(
    {"anthropic", "gemini", "vertex_ai", "bedrock", "azure", "cohere"}
)


def get_default_chat_wire_model(model_name: str, base_url: str | None) -> str:
    """Resolve a configured/default model name to the endpoint's model ID."""
    converted = covert_to_litellm_model_name(model_name)

    if "openrouter.ai" in (base_url or ""):
        if converted.startswith("openrouter/"):
            converted = converted.removeprefix("openrouter/")
        return converted

    if converted.startswith("openrouter/"):
        raise ValueError(
            "An openrouter/ model requires BASE_URL to point to an OpenRouter "
            "OpenAI-compatible Chat Completions endpoint."
        )

    if converted.startswith("openai/responses/") or converted.startswith("responses/"):
        raise ValueError(
            f"Model {model_name!r} is configured for the Responses protocol and "
            "cannot be sent through the Chat Completions transport."
        )

    prefix, separator, model_id = converted.partition("/")
    if separator and prefix in _NATIVE_ONLY_PREFIXES:
        raise ValueError(
            f"Model {model_name!r} uses the {prefix!r} native protocol, which is "
            "not supported by the default Chat Completions transport. Configure "
            "an OpenAI-compatible Chat Completions endpoint/model instead."
        )
    if separator and prefix in _LITELLM_ROUTING_PREFIXES:
        if prefix != "openai" and not base_url:
            raise ValueError(
                f"BASE_URL is required for the {prefix!r} model route. Configure an "
                "endpoint that supports OpenAI Chat Completions for this model."
            )
        return model_id
    if separator:
        raise ValueError(
            f"Model {model_name!r} uses the {prefix!r} LiteLLM routing namespace, "
            "which is not sufficient to identify an OpenAI Chat Completions "
            "wire model. Configure a Chat-compatible model ID (or use OpenRouter "
            "with its matching BASE_URL)."
        )
    return converted


class DefaultOpenAIChatCompletionsModel(
    RefreshingOpenAIClientMixin,
    KimiToolOrderingMixin,
    OpenAIChatCompletionsModel,
):
    """Official Agents SDK Chat Completions model with Kimi input ordering."""

    def __init__(
        self,
        model: str,
        client_factory: DefaultChatClientFactory,
        should_replay_reasoning_content: Any,
    ) -> None:
        self._client_factory = client_factory
        super().__init__(
            model=model,
            openai_client=client_factory.get_client(),
            should_replay_reasoning_content=should_replay_reasoning_content,
        )

    @property
    def base_url(self) -> str | None:
        """Endpoint the underlying client sends to (read-only)."""
        base_url = self._client.base_url
        return str(base_url) if base_url is not None else None

    @property
    def api_key(self) -> str | None:
        """API key the underlying client authenticates with (read-only)."""
        return getattr(self._client, "api_key", None)


class DefaultChatClientFactory:
    """Reuse default-provider clients until BASE_URL/API_KEY changes.

    Without explicit credentials the pair is re-read from the environment on
    every ``get_client()`` call, so login / reconfigure flows are picked up by
    the models built from this factory. Passing ``base_url`` / ``api_key`` pins
    the factory to those values instead, which is how a per-model override
    (``fast_llm_config``) keeps its endpoint and key off the process
    environment.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._pinned_base_url = base_url
        self._pinned_api_key = api_key
        self._client: AsyncOpenAI | None = None
        self._client_key: tuple[str | None, str | None] | None = None
        self._retired_clients: list[AsyncOpenAI] = []
        self._lock = threading.Lock()
        self._loop_ownership = EventLoopOwnership()
        self._closed = False

    def get_client(self) -> AsyncOpenAI:
        if self._pinned_api_key is not None:
            base_url = self._pinned_base_url or None
            api_key = self._pinned_api_key
        else:
            base_url = os.getenv("BASE_URL") or None
            api_key = os.getenv("API_KEY") or None
        if not api_key:
            raise ValueError(
                "API_KEY is required for the default OpenAI Chat Completions "
                "provider. Set API_KEY and optionally BASE_URL to an "
                "OpenAI-compatible Chat Completions endpoint."
            )

        key = (base_url, api_key)
        with self._lock:
            if self._closed:
                raise RuntimeError("DefaultChatClientFactory is closed")
            self._loop_ownership.check()
            if self._client is None or self._client_key != key:
                if self._client is not None:
                    self._retired_clients.append(self._client)
                self._client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=LLM_API_POST_TIMEOUT,
                    max_retries=0,
                )
                self._client_key = key
            return self._client

    async def aclose(self) -> None:
        """Close every client this factory owns, including retired ones.

        Must run on the event loop that owns the clients (see
        ``EventLoopOwnership``): a native HTTP pool cannot be released from a
        foreign loop.

        Failures never stop the remaining clients from closing; a single error
        is re-raised as-is and several are aggregated into an ExceptionGroup.

        Ownership is released one client at a time, and only through those two
        outcomes. A cancelled ``aclose`` (``asyncio.CancelledError`` is a
        ``BaseException``, so it is not an ordinary close failure) propagates
        unchanged and re-owns the clients whose close it did not confirm —
        including the interrupted one — so a later ``aclose()`` still closes
        them instead of them being dropped beyond reach.
        """
        with self._lock:
            if self._closed and self._client is None and not self._retired_clients:
                return
            self._loop_ownership.check()
            self._closed = True
            clients = [*self._retired_clients]
            self._retired_clients.clear()
            if self._client is not None:
                clients.append(self._client)
                self._client = None
                self._client_key = None
        errors: list[Exception] = []
        for index, client in enumerate(clients):
            try:
                await client.close()
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(exc)
            except BaseException:
                # Cancellation must reach the caller, but the clients this call
                # has not closed yet must not be detached with it.
                self._restore_clients(clients[index:])
                raise

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("errors closing default chat clients", errors)

    def _restore_clients(self, clients: list[AsyncOpenAI]) -> None:
        """Return unconfirmed clients to the retired list, oldest first.

        Restored clients are never handed out again (``get_client`` only ever
        returns ``_client``), so re-owning them only means that a later
        ``aclose()`` still sees them.
        """
        if not clients:
            return
        with self._lock:
            self._retired_clients = [*clients, *self._retired_clients]