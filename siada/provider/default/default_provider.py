from __future__ import annotations
import os
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from agents import Model, ModelProvider

from siada.provider.default.chat_completions import (
    DefaultChatClientFactory,
    DefaultOpenAIChatCompletionsModel,
    get_default_chat_wire_model,
)
from siada.provider.default.coverter import covert_to_litellm_model_name
from siada.provider.default.kimi_tool_ordering import (
    get_kimi_tool_ordering_litellm_model_cls,
)
from siada.provider.llm_client import LLMClient
from siada.provider.reasoning_replay import should_replay_reasoning_content
from siada.provider.request_config import (
    default_credentials_scope,
    get_default_credentials,
    has_request_credentials,
)
from siada.provider.token_counting import TokenCountingInfo

if TYPE_CHECKING:
    from litellm.types.utils import ModelResponse as LitellmModelResponse


def _register_custom_claude_model(model_name: str):
    """Register custom model names in litellm so supports_reasoning() returns True,
    allowing 'thinking' (Claude) and 'reasoning_effort' (Gemini) params to pass through.
    """
    import litellm
    if model_name in litellm.model_cost:
        return

    lower_name = model_name.lower()
    if "claude" in lower_name or "gemini" in lower_name:
        litellm.register_model({model_name: {"supports_reasoning": True}})


class DefaultProvider(ModelProvider):
    """Provider for OpenAI Chat Completions and retained Claude/Gemini routes.

    OpenAI Chat-compatible endpoints use ``BASE_URL`` and ``API_KEY``. Claude
    uses LiteLLM; Gemini uses the official Google Gen AI SDK.
    """

    def __init__(self):
        # NOTE:
        # Provider instances are created eagerly by provider_factory at import time.
        # API key login, however, may update BASE_URL/API_KEY later at runtime.
        # So we must not cache credentials only once in __init__.
        self.base_url = None
        self.api_key = None
        self._chat_client_factory = DefaultChatClientFactory()
        from siada.provider.default.responses_transport import (
            DefaultResponsesTransport,
        )

        self._responses_transport = DefaultResponsesTransport()
        self._gemini_transport = None
        self._gemini_closed = False
        self._pinned_chat_client_factories = {}
        self._pinned_gemini_transports = {}
        self._closed = False

    def _refresh_credentials(self):
        """Refresh credentials from environment for runtime login / reconfigure flows."""
        self.base_url = os.getenv("BASE_URL", None)
        self.api_key = os.getenv("API_KEY", None)

    def request_scope(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> AbstractContextManager[None]:
        """Use isolated endpoint credentials while retaining runtime ownership."""
        return default_credentials_scope(base_url=base_url, api_key=api_key)

    def _apply_provider_specific_env(self, effective_model_name: str):
        """Populate provider-specific env vars required by some LiteLLM backends."""
        if not self.api_key or has_request_credentials():
            return

        if "deepseek" in effective_model_name:
            os.environ["DEEPSEEK_API_KEY"] = self.api_key

        if "moonshot/" in effective_model_name or effective_model_name.startswith("kimi-"):
            os.environ["MOONSHOT_API_KEY"] = self.api_key

    def _ensure_openrouter_prefix(
        self, model_name: str, *, base_url: str | None = None
    ) -> str:
        """Route model ids through litellm's openrouter provider when BASE_URL is OpenRouter.

        OpenRouter catalog ids look like ``vendor/model`` (e.g.
        ``anthropic/claude-3.7-sonnet``) — exactly the shape litellm uses for
        provider routing, so a bare id would be routed as a DIRECT call to
        that vendor with the wrong protocol/URL (e.g. ``anthropic/...`` lands
        on ``/v1/v1/messages``, ``google/...`` needs GEMINI credentials).
        Prefixing with ``openrouter/`` makes litellm use its openrouter
        provider instead: openai-protocol ``/chat/completions`` against the
        configured BASE_URL, with the model id passed through verbatim.
        """
        effective_base_url = self.base_url if base_url is None else base_url
        if "openrouter.ai" not in (effective_base_url or ""):
            return model_name
        if model_name.startswith("openrouter/"):
            return model_name
        return f"openrouter/{model_name}"

    def _resolve_model_route(self, raw_model_name: str, base_url: str | None) -> tuple[str, TokenCountingInfo]:
        """Share pure routing between token estimation and model construction."""
        from siada.provider.responses import is_responses_only_model

        if is_responses_only_model(raw_model_name):
            return "responses", TokenCountingInfo(raw_model_name, "responses", "siada_responses")
        from siada.provider.gemini.routing import is_gemini_model, wire_model_name

        if is_gemini_model(raw_model_name) and "openrouter.ai" not in (base_url or ""):
            return "gemini", TokenCountingInfo(wire_model_name(raw_model_name), "gemini", "siada_gemini", replay_domain="default:gemini_api")
        lower_model_name = raw_model_name.lower()
        effective_model_name = covert_to_litellm_model_name(raw_model_name)
        uses_responses_bridge = effective_model_name.startswith(("openai/responses/", "responses/"))
        if (
            "claude" not in lower_model_name
            and "anthropic" not in lower_model_name
            and "gemini" not in lower_model_name
            and not uses_responses_bridge
        ):
            return "chat", TokenCountingInfo(get_default_chat_wire_model(raw_model_name, base_url))
        effective_model_name = self._ensure_openrouter_prefix(effective_model_name, base_url=base_url or "")
        return "litellm", TokenCountingInfo(effective_model_name)

    def get_token_counting_info(self, model_name: str | None) -> TokenCountingInfo:
        """Describe the configured route without creating a model or HTTP client."""
        base_url, _ = get_default_credentials()
        _, info = self._resolve_model_route(model_name or os.getenv("MODEL_NAME") or "", base_url)
        return info

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get. If None, uses MODEL_NAME from environment.

        Returns:
            The model.
        """
        self._refresh_credentials()
        base_url, api_key = get_default_credentials()
        return self._build_model(model_name, base_url=base_url, api_key=api_key, pinned=False)

    def get_model_with_credentials(
        self, model_name: str | None, *, base_url: str | None = None, api_key: str | None = None
    ) -> Model:
        """Pin explicit credentials without modifying process-global state."""
        active_base_url, active_api_key = get_default_credentials()
        return self._build_model(
            model_name, base_url=base_url if base_url is not None else active_base_url,
            api_key=api_key if api_key is not None else active_api_key, pinned=True,
        )

    def _build_model(self, model_name: str | None, *, base_url: str | None, api_key: str | None, pinned: bool) -> Model:
        """Keep native routing while binding persistent fast models to credentials."""
        if self._closed:
            raise RuntimeError("DefaultProvider is closed")
        # Responses-API-only models (GPT-5.x family) go through the native
        # Responses protocol layer instead of LiteLLM's responses bridge.
        raw_model_name = model_name or os.getenv("MODEL_NAME") or ""
        route, info = self._resolve_model_route(raw_model_name, base_url)
        effective_model_name = info.model_name
        from siada.provider.responses import ResponsesModel
        if route == "gemini":
            if self._gemini_closed:
                raise RuntimeError("Default Gemini provider resources are closed.")
            from siada.provider.gemini import GeminiModel
            from siada.provider.default.gemini_transport import DefaultGeminiTransport

            if self._gemini_transport is None:
                self._gemini_transport = DefaultGeminiTransport()
            if pinned:
                from siada.provider.default.gemini_transport import PinnedDefaultGeminiTransport

                credentials = (base_url, api_key)
                transport = self._pinned_gemini_transports.get(credentials)
                if transport is None:
                    transport = PinnedDefaultGeminiTransport(base_url, api_key)
                    self._pinned_gemini_transports[credentials] = transport
                return GeminiModel(model=effective_model_name, transport=transport)
            return GeminiModel(model=effective_model_name, transport=self._gemini_transport)
        if route == "responses":
            if pinned and (base_url, api_key) != get_default_credentials():
                raise ValueError(
                    "fast_llm_config credentials cannot be applied to a bare "
                    "Responses-API-only model. Use fast_completion() for isolated "
                    "Responses requests, or a chat-completions model."
                )
            return ResponsesModel(
                model=raw_model_name,
                transport=self._responses_transport,
            )

        if route == "chat":
            client_factory = self._chat_client_factory
            if pinned:
                credentials = (base_url, api_key)
                client_factory = self._pinned_chat_client_factories.get(credentials)
                if client_factory is None:
                    client_factory = DefaultChatClientFactory(base_url=base_url, api_key=api_key)
                    self._pinned_chat_client_factories[credentials] = client_factory
            return DefaultOpenAIChatCompletionsModel(
                model=effective_model_name,
                client_factory=client_factory,
                should_replay_reasoning_content=should_replay_reasoning_content,
            )

        from siada.entrypoint import _configure_litellm
        _configure_litellm()

        # Register custom aws-claude-* models so litellm recognizes their capabilities
        _register_custom_claude_model(effective_model_name)

        # Keep the legacy LiteLLM model for Claude/Gemini and Responses bridge
        # aliases. The shared Kimi ordering mixin remains available for callers
        # that still use this legacy transport.
        return get_kimi_tool_ordering_litellm_model_cls()(
            model=effective_model_name,
            base_url=base_url,
            api_key=api_key,
            should_replay_reasoning_content=should_replay_reasoning_content,
        )

    async def aclose(self) -> None:
        """Close all model clients owned by this provider."""
        if self._gemini_transport is not None:
            self._gemini_transport._loop.check(bind=False)
        for transport in self._pinned_gemini_transports.values():
            transport._loop.check(bind=False)
        self._closed = True
        self._gemini_closed = True
        errors: list[Exception] = []
        for close in (
            self._chat_client_factory.aclose,
            self._responses_transport.aclose,
            *((self._gemini_transport.aclose,) if self._gemini_transport is not None else ()),
            *(factory.aclose for factory in self._pinned_chat_client_factories.values()),
            *(transport.aclose for transport in self._pinned_gemini_transports.values()),
        ):
            try:
                await close()
            except Exception as exc:
                errors.append(exc)
        self._pinned_chat_client_factories.clear()
        self._pinned_gemini_transports.clear()

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup(
                "Failed to close one or more default provider resources",
                errors,
            )


class DefaultClient(LLMClient):
    """Client for custom LLM API using litellm
    
    Supports any model compatible with litellm by configuring:
    - BASE_URL: The API base URL
    - API_KEY: The API key for authentication
    - MODEL_NAME: The model name to use
    """

    def __init__(self):
        self.base_url = None
        self.api_key = None

    def _refresh_credentials(self):
        self.base_url = os.getenv("BASE_URL")
        self.api_key = os.getenv("API_KEY")

    async def completion(self, **kwargs) -> LitellmModelResponse:
        """Call LLM API for completion.
        
        Args:
            **kwargs: Arguments to pass to litellm.acompletion
                     Can include 'model' to override the default model
            
        Returns:
            LitellmModelResponse: The completion response
        """
        base_url, api_key = get_default_credentials()
        if base_url and not kwargs.get("api_base"):
            kwargs["api_base"] = base_url
        if api_key and not kwargs.get("api_key"):
            kwargs["api_key"] = api_key
        model_name = kwargs.get("model")
        if isinstance(model_name, str) and not kwargs.get("custom_llm_provider"):
            model_name = covert_to_litellm_model_name(model_name)
            if "openrouter.ai" in (kwargs.get("api_base") or ""):
                if not model_name.startswith("openrouter/"):
                    model_name = f"openrouter/{model_name}"
            elif "/" not in model_name:
                kwargs["custom_llm_provider"] = "openai"
            kwargs["model"] = model_name

        import litellm
        # Use litellm's native async method for better performance
        return await litellm.acompletion(**kwargs)
