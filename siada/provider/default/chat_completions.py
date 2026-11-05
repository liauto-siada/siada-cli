"""Default-provider transport for OpenAI Chat Completions-compatible APIs."""

from __future__ import annotations

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
from siada.provider.request_config import get_default_credentials, has_request_credentials


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


class DefaultChatClientFactory:
    """Reuse default-provider clients until BASE_URL/API_KEY changes."""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._client_key: tuple[str | None, str | None] | None = None
        self._retired_clients: list[AsyncOpenAI] = []
        self._request_clients: dict[tuple[str | None, str | None], AsyncOpenAI] = {}
        self._lock = threading.Lock()
        self._loop_ownership = EventLoopOwnership()
        self._closed = False

    def get_client(self) -> AsyncOpenAI:
        base_url, api_key = get_default_credentials()
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
            if has_request_credentials():
                client = self._request_clients.get(key)
                if client is None:
                    client = AsyncOpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=LLM_API_POST_TIMEOUT,
                        max_retries=0,
                    )
                    self._request_clients[key] = client
                return client
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
        with self._lock:
            if self._closed:
                return
            self._loop_ownership.check()
            self._closed = True
            clients = [*self._retired_clients, *self._request_clients.values()]
            self._retired_clients.clear()
            self._request_clients.clear()
            if self._client is not None:
                clients.append(self._client)
                self._client = None
                self._client_key = None
        errors: list[Exception] = []
        for client in clients:
            try:
                await client.close()
            except Exception as exc:
                errors.append(exc)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("Failed to close one or more default Chat clients", errors)